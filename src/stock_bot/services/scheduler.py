"""Scheduled morning/evening briefings and periodic price alert monitoring (bilingual EN/ZH)."""

from __future__ import annotations

import logging
from typing import Literal
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from telegram import Bot
from telegram.constants import ParseMode

from stock_bot.agent.financial_agent import FinancialAgent
from stock_bot.bot.formatters import (
    esc,
    format_market_overview,
    markdown_to_telegram_html,
    split_message,
)
from stock_bot.config import Settings
from stock_bot.services.market_data import MarketDataService
from stock_bot.storage.database import Database

logger = logging.getLogger(__name__)


def _parse_hhmm(value: str, default_hour: int, default_minute: int) -> tuple[int, int]:
    try:
        parts = value.strip().split(":")
        return int(parts[0]), int(parts[1])
    except Exception:
        return default_hour, default_minute


class BriefingScheduler:
    """Runs cron briefings (morning/evening) and periodic price alerts."""

    def __init__(
        self,
        settings: Settings,
        bot: Bot,
        market_data: MarketDataService,
        agent: FinancialAgent,
        database: Database,
    ) -> None:
        self.settings = settings
        self.bot = bot
        self.market_data = market_data
        self.agent = agent
        self.database = database
        self.scheduler = AsyncIOScheduler(timezone=ZoneInfo(settings.timezone))

    def start(self) -> None:
        m_hour, m_min = _parse_hhmm(self.settings.morning_brief_time, 9, 0)
        e_hour, e_min = _parse_hhmm(self.settings.evening_brief_time, 15, 30)

        self.scheduler.add_job(
            self.dispatch_briefings,
            CronTrigger(day_of_week="mon-fri", hour=m_hour, minute=m_min),
            args=["morning"],
            id="morning_brief",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.dispatch_briefings,
            CronTrigger(day_of_week="mon-fri", hour=e_hour, minute=e_min),
            args=["evening"],
            id="evening_brief",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self.check_price_alerts,
            IntervalTrigger(seconds=self.settings.alert_poll_seconds),
            id="price_alerts",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info(
            "Scheduler started (tz=%s, morning=%02d:%02d, evening=%02d:%02d, alert_poll=%ds).",
            self.settings.timezone,
            m_hour,
            m_min,
            e_hour,
            e_min,
            self.settings.alert_poll_seconds,
        )

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def build_briefing_text(self, kind: Literal["morning", "evening"], user_id: int) -> str:
        lang = await self.database.get_user_lang(user_id)
        en = lang == "en"
        if en:
            title = "☀️ <b>Daily Morning Brief</b>" if kind == "morning" else "🌙 <b>Daily Evening Recap</b>"
        else:
            title = "☀️ <b>每日盘前早报</b>" if kind == "morning" else "🌙 <b>每日盘后晚报</b>"

        indices = await self.market_data.get_market_overview()
        watchlist = await self.database.get_watchlist(user_id)

        watch_quotes: list[dict[str, object]] = []
        watch_lines: list[str] = []
        for item in watchlist[:8]:
            try:
                q = await self.market_data.get_quote(item.code)
                if en:
                    icon = "🟢" if q.change_pct > 0 else ("🔴" if q.change_pct < 0 else "⚪")
                else:
                    icon = "🔴" if q.change_pct > 0 else ("🟢" if q.change_pct < 0 else "⚪")
                sign = "+" if q.change_pct > 0 else ""
                watch_lines.append(
                    f"• <b>{esc(q.name)}</b> (<code>{esc(q.ts_code)}</code>)  <code>{q.close:.2f} {esc(q.currency)}</code>  {icon} {sign}{q.change_pct:.2f}%"
                )
                watch_quotes.append(
                    {"code": q.ts_code, "name": q.name, "close": q.close, "change_pct": q.change_pct}
                )
            except Exception as exc:
                logger.debug("Briefing watchlist quote failed for %s: %s", item.code, exc)

        sections = [title, "", format_market_overview(indices, lang=lang, include_tip=False)]

        if watch_lines:
            sections.extend(["", "⭐ <b>Watchlist Movers</b>" if en else "⭐ <b>自选股动态</b>", *watch_lines])

        try:
            ai_comment = await self.agent.summarize_briefing(
                kind,
                {
                    "indices": [i.model_dump() for i in indices],
                    "watchlist": watch_quotes,
                },
                lang=lang,
            )
            if ai_comment:
                sections.extend(
                    ["", "🤖 <b>AI Commentary</b>" if en else "🤖 <b>AI 简评</b>", markdown_to_telegram_html(ai_comment)]
                )
        except Exception as exc:
            logger.warning("AI briefing summary failed: %s", exc)

        return "\n".join(sections)

    async def dispatch_briefings(self, kind: Literal["morning", "evening"]) -> None:
        subscribers = await self.database.list_brief_subscribers(kind)
        if not subscribers:
            return
        logger.info("Dispatching %s briefing to %d subscribers.", kind, len(subscribers))
        for sub in subscribers:
            try:
                text = await self.build_briefing_text(kind, sub.user_id)
                for chunk in split_message(text):
                    await self.bot.send_message(
                        chat_id=sub.chat_id,
                        text=chunk,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
            except Exception as exc:
                logger.warning("Failed to send %s briefing to chat %s: %s", kind, sub.chat_id, exc)

    async def check_price_alerts(self) -> None:
        alerts = await self.database.get_active_alerts()
        if not alerts:
            return

        quote_cache: dict[str, tuple[float, str]] = {}
        for alert in alerts:
            try:
                if alert.code not in quote_cache:
                    q = await self.market_data.get_quote(alert.code)
                    quote_cache[alert.code] = (q.close, q.currency)
                price, currency = quote_cache[alert.code]
                hit = (
                    (alert.direction == "above" and price >= alert.target_price)
                    or (alert.direction == "below" and price <= alert.target_price)
                )
                if hit:
                    await self.database.mark_alert_triggered(alert.id)
                    lang = await self.database.get_user_lang(alert.user_id)
                    if lang == "en":
                        cond = "Reached / Above (≥)" if alert.direction == "above" else "Dropped / Below (≤)"
                        msg = (
                            f"🔔 <b>Price Alert Triggered!</b>\n\n"
                            f"Ticker: <b>{esc(alert.name)}</b> (<code>{esc(alert.code)}</code>)\n"
                            f"Condition: {cond} <code>{alert.target_price:.2f} {esc(currency)}</code>\n"
                            f"Current Price: <b><code>{price:.2f} {esc(currency)}</code></b>"
                        )
                    else:
                        cond = "突破（≥）" if alert.direction == "above" else "跌破（≤）"
                        msg = (
                            f"🔔 <b>价格预警触发！</b>\n\n"
                            f"标的：<b>{esc(alert.name)}</b> (<code>{esc(alert.code)}</code>)\n"
                            f"条件：{cond} <code>{alert.target_price:.2f} {esc(currency)}</code>\n"
                            f"当前价：<b><code>{price:.2f} {esc(currency)}</code></b>"
                        )
                    await self.bot.send_message(chat_id=alert.chat_id, text=msg, parse_mode=ParseMode.HTML)
            except Exception as exc:
                logger.debug("Price alert check failed for alert %s (%s): %s", alert.id, alert.code, exc)
