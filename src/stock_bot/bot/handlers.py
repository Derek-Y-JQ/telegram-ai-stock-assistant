"""Telegram command, callback query, and natural language handlers."""

from __future__ import annotations

import logging
import re
from typing import Literal

from telegram import InputMediaPhoto, Update
from telegram.constants import ChatAction, ParseMode
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from stock_bot.agent.financial_agent import FinancialAgent
from stock_bot.bot.formatters import (
    esc,
    format_finance,
    format_market_overview,
    format_news,
    format_stock_quote,
    format_technical_report,
    format_watchlist,
    markdown_to_telegram_html,
    split_message,
)
from stock_bot.bot.keyboards import (
    candidates_keyboard,
    kline_switcher_keyboard,
    market_overview_keyboard,
    stock_actions_keyboard,
    watchlist_keyboard,
)
from stock_bot.services.chart import ChartService
from stock_bot.services.market_data import MarketDataService, normalize_stock_code
from stock_bot.services.technical import TechnicalAnalyzer
from stock_bot.storage.database import Database

logger = logging.getLogger(__name__)

DIRECT_CODE_RE = re.compile(r"^(?:sh|sz|bj)?\d{6}(?:\.(?:SH|SZ|BJ))?$", re.IGNORECASE)


class BotHandlers:
    """Routes Telegram updates to MarketDataService, ChartService, TechnicalAnalyzer, and FinancialAgent."""

    def __init__(
        self,
        market_data: MarketDataService,
        charts: ChartService,
        agent: FinancialAgent,
        database: Database,
    ) -> None:
        self.market_data = market_data
        self.charts = charts
        self.agent = agent
        self.database = database

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        await update.message.chat.send_action(ChatAction.TYPING)
        try:
            indices = await self.market_data.get_market_overview()
            overview = format_market_overview(indices)
        except Exception as exc:
            logger.warning("Failed to fetch market overview on /start: %s", exc)
            overview = "📊 欢迎使用 <b>A 股智能投研助理 v2.0</b>！"

        welcome = (
            f"👋 你好！欢迎使用 <b>A 股智能投研助理</b>\n\n"
            f"{overview}\n\n"
            "✨ <b>快捷用法：</b>\n"
            "• 直接发代码：<code>600519</code> 或 <code>/stock 茅台</code>\n"
            "• 直接提问：<i>「帮我分析一下宁德时代最近的技术面和新闻」</i>\n"
            "• <code>/market</code> 大盘概览 · <code>/watch</code> 我的自选 · <code>/clear</code> 清空对话记忆"
        )
        await update.message.reply_text(
            welcome,
            parse_mode=ParseMode.HTML,
            reply_markup=market_overview_keyboard(),
        )

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        text = (
            "📖 <b>使用指南</b>\n\n"
            "<b>1. 快速查股卡片</b>\n"
            "• 直接发送 6 位代码（如 <code>600519</code>、<code>300750</code>）\n"
            "• 或使用 <code>/stock 名称或代码</code>（支持中文模糊搜索）\n"
            "• 卡片下方按钮支持一键查看 <b>日/周/月 K 线、量化技术诊断、财务体检、最新舆情、AI 深度研报</b>。\n\n"
            "<b>2. 自然语言 AI 投研对话</b>\n"
            "• 直接发消息即可对话，AI 会自主调用行情/财报/新闻/技术指标工具：\n"
            "  - <i>「贵州茅台和五粮液谁的盈利能力更强？」</i>\n"
            "  - <i>「比亚迪最近有什么利好利空消息？」</i>\n"
            "  - <i>「今天大盘走势怎么样？」</i>\n\n"
            "<b>3. 常用命令</b>\n"
            "• <code>/market</code> — 查看 A 股核心大盘指数\n"
            "• <code>/stock &lt;关键词&gt;</code> — 搜索并打开股票卡片\n"
            "• <code>/watch</code> — 查看与管理自选股\n"
            "• <code>/clear</code> — 清空当前聊天上下文记忆"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def market_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        await update.message.chat.send_action(ChatAction.TYPING)
        indices = await self.market_data.get_market_overview()
        await update.message.reply_text(
            format_market_overview(indices),
            parse_mode=ParseMode.HTML,
            reply_markup=market_overview_keyboard(),
        )

    async def stock_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        query = " ".join(context.args).strip() if context.args else ""
        if not query:
            await update.message.reply_text(
                "请提供股票代码或名称，例如：<code>/stock 600519</code> 或 <code>/stock 茅台</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        await update.message.chat.send_action(ChatAction.TYPING)
        candidates = await self.market_data.search_stocks(query, limit=5)
        if not candidates:
            await update.message.reply_text(f"未找到与「{esc(query)}」匹配的 A 股标的。", parse_mode=ParseMode.HTML)
            return

        if len(candidates) == 1 or candidates[0].name == query or candidates[0].code == query:
            await self._send_quote_card(update, candidates[0].code)
            return

        await update.message.reply_text(
            f"🔍 找到多个与「<b>{esc(query)}</b>」匹配的标的，请选择：",
            parse_mode=ParseMode.HTML,
            reply_markup=candidates_keyboard(candidates),
        )

    async def watch_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        items = await self.database.get_watchlist(update.effective_user.id)
        await update.message.reply_text(
            format_watchlist(items),
            parse_mode=ParseMode.HTML,
            reply_markup=watchlist_keyboard(items) if items else market_overview_keyboard(),
        )

    async def clear_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_chat:
            return
        await self.database.clear_history(update.effective_chat.id)
        await update.message.reply_text("🧹 已清空当前会话的 AI 对话记忆。")

    # ------------------------------------------------------------------
    # Natural language text handler
    # ------------------------------------------------------------------

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text or not update.effective_chat:
            return
        text = update.message.text.strip()
        if not text:
            return

        # Fast path: direct 6-digit stock code opens the interactive stock card immediately
        if DIRECT_CODE_RE.match(text):
            try:
                code, _, _ = normalize_stock_code(text)
                await update.message.chat.send_action(ChatAction.TYPING)
                await self._send_quote_card(update, code)
                return
            except Exception as exc:
                await update.message.reply_text(f"⚠️ 查询失败：{esc(exc)}", parse_mode=ParseMode.HTML)
                return

        # Natural language -> Financial AI Agent
        await update.message.chat.send_action(ChatAction.TYPING)
        thinking_msg = await update.message.reply_text("🤔 正在调取实时数据并分析，请稍候...")
        try:
            reply = await self.agent.chat(update.effective_chat.id, text)
            html_reply = markdown_to_telegram_html(reply)
            chunks = split_message(html_reply)
            await thinking_msg.edit_text(chunks[0], parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            for chunk in chunks[1:]:
                await update.message.reply_text(chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception as exc:
            logger.exception("Agent chat error: %s", exc)
            await thinking_msg.edit_text(f"⚠️ 分析过程中发生错误，请稍后重试。\n({exc})")

    # ------------------------------------------------------------------
    # InlineKeyboard callbacks
    # ------------------------------------------------------------------

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data or not query.message or not update.effective_user:
            return
        await query.answer()

        parts = query.data.split(":")
        action = parts[0]
        user_id = update.effective_user.id

        try:
            if action == "market":
                indices = await self.market_data.get_market_overview()
                await self._safe_edit_text(
                    query,
                    format_market_overview(indices),
                    reply_markup=market_overview_keyboard(),
                )
            elif action == "watchlist":
                items = await self.database.get_watchlist(user_id)
                await query.message.reply_text(
                    format_watchlist(items),
                    parse_mode=ParseMode.HTML,
                    reply_markup=watchlist_keyboard(items) if items else market_overview_keyboard(),
                )
            elif action == "quote" and len(parts) >= 2:
                code = parts[1]
                quote = await self.market_data.get_quote(code)
                in_watch = await self.database.is_in_watchlist(user_id, quote.code)
                await query.message.reply_text(
                    format_stock_quote(quote),
                    parse_mode=ParseMode.HTML,
                    reply_markup=stock_actions_keyboard(quote.code, in_watchlist=in_watch),
                )
            elif action in ("kline", "kline_edit") and len(parts) >= 3:
                code = parts[1]
                period: Literal["daily", "weekly", "monthly"] = (
                    parts[2] if parts[2] in ("daily", "weekly", "monthly") else "daily"
                )
                await query.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
                candidate, df = await self.market_data.get_kline(code, period=period)
                png_bytes = await self.charts.render_kline(df, candidate.code, candidate.name, period=period)
                period_cn = {"daily": "日K", "weekly": "周K", "monthly": "月K"}[period]
                caption = f"📊 <b>{esc(candidate.name)}</b> (<code>{esc(candidate.code)}</code>) · {period_cn} (MA5/10/20/60 + 量能 + MACD)"
                kb = kline_switcher_keyboard(candidate.code, active_period=period)

                if action == "kline_edit":
                    await query.edit_message_media(
                        media=InputMediaPhoto(media=png_bytes, caption=caption, parse_mode=ParseMode.HTML),
                        reply_markup=kb,
                    )
                else:
                    await query.message.reply_photo(
                        photo=png_bytes,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=kb,
                    )
            elif action == "tech" and len(parts) >= 2:
                code = parts[1]
                await query.message.chat.send_action(ChatAction.TYPING)
                candidate, df = await self.market_data.get_kline(code, period="daily", days=180)
                report = TechnicalAnalyzer.analyze(candidate.code, candidate.name, df)
                in_watch = await self.database.is_in_watchlist(user_id, candidate.code)
                await query.message.reply_text(
                    format_technical_report(report),
                    parse_mode=ParseMode.HTML,
                    reply_markup=stock_actions_keyboard(candidate.code, in_watchlist=in_watch),
                )
            elif action == "finance" and len(parts) >= 2:
                code = parts[1]
                await query.message.chat.send_action(ChatAction.TYPING)
                fin = await self.market_data.get_finance(code)
                in_watch = await self.database.is_in_watchlist(user_id, fin.code)
                await query.message.reply_text(
                    format_finance(fin),
                    parse_mode=ParseMode.HTML,
                    reply_markup=stock_actions_keyboard(fin.code, in_watchlist=in_watch),
                )
            elif action == "news" and len(parts) >= 2:
                code = parts[1]
                await query.message.chat.send_action(ChatAction.TYPING)
                candidate, items = await self.market_data.get_news(code, limit=6)
                in_watch = await self.database.is_in_watchlist(user_id, candidate.code)
                await query.message.reply_text(
                    format_news(candidate, items),
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=True,
                    reply_markup=stock_actions_keyboard(candidate.code, in_watchlist=in_watch),
                )
            elif action == "report" and len(parts) >= 2:
                code = parts[1]
                await query.message.chat.send_action(ChatAction.TYPING)
                status_msg = await query.message.reply_text("🤖 正在并行汇总行情、财报、技术指标与最新舆情，生成 AI 深度研报...")
                report_text = await self.agent.generate_deep_report(code)
                chunks = split_message(markdown_to_telegram_html(report_text))
                await status_msg.edit_text(chunks[0], parse_mode=ParseMode.HTML, disable_web_page_preview=True)
                for chunk in chunks[1:]:
                    await query.message.reply_text(chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            elif action == "watch" and len(parts) >= 2:
                code = parts[1]
                candidate = await self.market_data.resolve_stock(code)
                if await self.database.is_in_watchlist(user_id, candidate.code):
                    await self.database.remove_watchlist(user_id, candidate.code)
                    in_watch = False
                    notice = f"已将 {candidate.name}({candidate.code}) 移出自选"
                else:
                    await self.database.add_watchlist(user_id, candidate.code, candidate.name)
                    in_watch = True
                    notice = f"已将 {candidate.name}({candidate.code}) 加入自选"
                await query.edit_message_reply_markup(
                    reply_markup=stock_actions_keyboard(candidate.code, in_watchlist=in_watch)
                )
                await query.answer(notice, show_alert=False)
        except Exception as exc:
            logger.exception("Callback %s failed: %s", query.data, exc)
            await query.message.reply_text(f"⚠️ 操作失败：{esc(exc)}", parse_mode=ParseMode.HTML)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _send_quote_card(self, update: Update, code: str) -> None:
        if not update.message or not update.effective_user:
            return
        quote = await self.market_data.get_quote(code)
        in_watch = await self.database.is_in_watchlist(update.effective_user.id, quote.code)
        await update.message.reply_text(
            format_stock_quote(quote),
            parse_mode=ParseMode.HTML,
            reply_markup=stock_actions_keyboard(quote.code, in_watchlist=in_watch),
        )

    @staticmethod
    async def _safe_edit_text(query, text: str, reply_markup=None) -> None:
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        except BadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise
