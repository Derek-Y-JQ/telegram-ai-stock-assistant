"""Application entry point running Telegram Bot, APScheduler, and embedded FastAPI Mini App."""

from __future__ import annotations

import asyncio
import logging

import uvicorn
from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from stock_bot.agent.financial_agent import FinancialAgent
from stock_bot.bot.handlers import BotHandlers
from stock_bot.config import Settings
from stock_bot.services.chart import ChartService
from stock_bot.services.market_data import MarketDataService
from stock_bot.services.scheduler import BriefingScheduler
from stock_bot.storage.cache import AsyncTTLCache
from stock_bot.storage.database import Database
from stock_bot.webapp.server import create_webapp

logger = logging.getLogger(__name__)


async def _error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled exception while processing update %s", update, exc_info=context.error)


def build_application(settings: Settings) -> Application:
    cache = AsyncTTLCache(default_ttl=settings.cache_ttl_seconds)
    database = Database(settings.database_path)
    market_data = MarketDataService(cache=cache, tushare_token=settings.tushare_token)
    charts = ChartService()
    agent = FinancialAgent(settings=settings, market_data=market_data, database=database)
    handlers = BotHandlers(
        settings=settings,
        market_data=market_data,
        charts=charts,
        agent=agent,
        database=database,
    )

    state: dict[str, object] = {}

    async def _post_init(app: Application) -> None:
        await database.init()

        # Start scheduled briefings & price alert monitor
        scheduler = BriefingScheduler(
            settings=settings,
            bot=app.bot,
            market_data=market_data,
            agent=agent,
            database=database,
        )
        handlers.scheduler = scheduler
        scheduler.start()
        state["scheduler"] = scheduler

        # Start embedded FastAPI Mini App server in background on the same event loop
        if settings.webapp_enabled:
            fastapi_app = create_webapp(market_data=market_data, database=database)
            uv_config = uvicorn.Config(
                fastapi_app,
                host=settings.webapp_host,
                port=settings.webapp_port,
                log_level="warning",
            )
            server = uvicorn.Server(uv_config)
            server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
            state["uvicorn_server"] = server
            state["uvicorn_task"] = asyncio.create_task(server.serve())
            logger.info(
                "Interactive Mini App & health server listening on http://%s:%d",
                settings.webapp_host,
                settings.webapp_port,
            )

        await app.bot.set_my_commands(
            [
                BotCommand("start", "启动助理并查看全球大盘"),
                BotCommand("market", "全球核心大盘指数（A股/港股/美股）"),
                BotCommand("stock", "搜索股票卡片（如 /stock 茅台 或 /stock NVDA）"),
                BotCommand("watch", "查看与管理我的自选股"),
                BotCommand("brief", "订阅/预览每日盘前早报与盘后晚报"),
                BotCommand("alert", "设置价格预警（如 /alert NVDA > 150）"),
                BotCommand("clear", "清空当前 AI 对话记忆"),
                BotCommand("help", "查看使用指南"),
            ]
        )
        logger.info("Stock Bot v2.5 initialized successfully (model=%s).", settings.llm_model)

    async def _post_shutdown(app: Application) -> None:
        scheduler = state.get("scheduler")
        if isinstance(scheduler, BriefingScheduler):
            scheduler.shutdown()
        server = state.get("uvicorn_server")
        if isinstance(server, uvicorn.Server):
            server.should_exit = True
        task = state.get("uvicorn_task")
        if isinstance(task, asyncio.Task):
            try:
                await asyncio.wait_for(task, timeout=3.0)
            except Exception:
                task.cancel()

    builder = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
    )
    if settings.telegram_proxy:
        builder = builder.proxy(settings.telegram_proxy).get_updates_proxy(settings.telegram_proxy)
        logger.info("Configured Telegram-only proxy: %s", settings.telegram_proxy)
    app = builder.build()

    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("market", handlers.market_cmd))
    app.add_handler(CommandHandler("stock", handlers.stock_cmd))
    app.add_handler(CommandHandler("watch", handlers.watch_cmd))
    app.add_handler(CommandHandler("brief", handlers.brief_cmd))
    app.add_handler(CommandHandler("alert", handlers.alert_cmd))
    app.add_handler(CommandHandler("clear", handlers.clear_cmd))
    app.add_handler(CallbackQueryHandler(handlers.handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_text))
    app.add_error_handler(_error_handler)

    return app


def main() -> None:
    settings = Settings()
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
    )
    app = build_application(settings)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
