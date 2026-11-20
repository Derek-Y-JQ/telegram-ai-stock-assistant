"""Application entry point for Telegram A-Share AI Stock Assistant."""

from __future__ import annotations

import logging

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
from stock_bot.storage.cache import AsyncTTLCache
from stock_bot.storage.database import Database

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
        market_data=market_data,
        charts=charts,
        agent=agent,
        database=database,
    )

    async def _post_init(app: Application) -> None:
        await database.init()
        await app.bot.set_my_commands(
            [
                BotCommand("start", "启动助理并查看大盘概览"),
                BotCommand("market", "查看 A 股主要大盘指数"),
                BotCommand("stock", "搜索股票并打开交互卡片（如 /stock 茅台）"),
                BotCommand("watch", "查看与管理我的自选股"),
                BotCommand("clear", "清空当前 AI 对话记忆"),
                BotCommand("help", "查看使用指南"),
            ]
        )
        logger.info("Stock Bot initialized successfully (model=%s).", settings.llm_model)

    builder = Application.builder().token(settings.telegram_bot_token).post_init(_post_init)
    if settings.telegram_proxy:
        builder = builder.proxy(settings.telegram_proxy).get_updates_proxy(settings.telegram_proxy)
        logger.info("Configured Telegram-only proxy: %s", settings.telegram_proxy)
    app = builder.build()

    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("help", handlers.help_cmd))
    app.add_handler(CommandHandler("market", handlers.market_cmd))
    app.add_handler(CommandHandler("stock", handlers.stock_cmd))
    app.add_handler(CommandHandler("watch", handlers.watch_cmd))
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
