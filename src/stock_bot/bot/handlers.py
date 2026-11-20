"""Telegram command, callback query, and natural language handlers with live interactive feedback."""

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
    format_alerts,
    format_brief_status,
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
    alerts_keyboard,
    brief_keyboard,
    candidates_keyboard,
    kline_switcher_keyboard,
    market_overview_keyboard,
    stock_actions_keyboard,
    watchlist_keyboard,
)
from stock_bot.config import Settings
from stock_bot.services.chart import ChartService
from stock_bot.services.market_data import MarketDataService, parse_stock_symbol
from stock_bot.services.scheduler import BriefingScheduler
from stock_bot.services.technical import TechnicalAnalyzer
from stock_bot.storage.database import Database

logger = logging.getLogger(__name__)

ALERT_CMD_RE = re.compile(r"^(\S+)\s*(>|>=|<|<=|above|below|高于|低于)\s*(\d+(?:\.\d+)?)$", re.IGNORECASE)


class BotHandlers:
    """Routes Telegram updates with immediate loading indicators and streaming AI thinking feedback."""

    def __init__(
        self,
        settings: Settings,
        market_data: MarketDataService,
        charts: ChartService,
        agent: FinancialAgent,
        database: Database,
        scheduler: BriefingScheduler | None = None,
    ) -> None:
        self.settings = settings
        self.market_data = market_data
        self.charts = charts
        self.agent = agent
        self.database = database
        self.scheduler = scheduler

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        loading = await update.message.reply_text("⏳ 正在拉取全球核心大盘数据（A股 / 港股 / 美股）...")
        try:
            indices = await self.market_data.get_market_overview()
            overview = format_market_overview(indices)
        except Exception as exc:
            logger.warning("Failed to fetch market overview on /start: %s", exc)
            overview = "🌍 欢迎使用 <b>全球股市智能投研助理 v2.5</b>！"

        welcome = (
            f"👋 你好！欢迎使用 <b>全球股市智能投研助理</b>（A股 · 港股 · 美股）\n\n"
            f"{overview}\n\n"
            "✨ <b>快捷用法：</b>\n"
            "• 直接发代码：<code>600519</code> · <code>00700</code> · <code>NVDA</code>\n"
            "• 中文搜索：<code>/stock 茅台</code> · <code>/stock 腾讯</code> · <code>/stock 英伟达</code>\n"
            "• 自然语言对话：<i>「对比一下英伟达和苹果的财务与近期技术面」</i>\n"
            "• <code>/market</code> 全球大盘 · <code>/watch</code> 自选 · <code>/brief</code> 早晚报 · <code>/alert</code> 价格预警"
        )
        await self._safe_edit_msg(
            loading,
            welcome,
            reply_markup=market_overview_keyboard(self.settings.webapp_url, update.effective_user.id),
        )

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message:
            return
        text = (
            "📖 <b>使用指南（v2.5 全球版）</b>\n\n"
            "<b>1. 快速查股卡片（支持 A股 / 港股 / 美股）</b>\n"
            "• 直接发送代码：<code>600519</code>（A股）、<code>00700</code>（港股）、<code>AAPL</code>（美股）\n"
            "• 或使用 <code>/stock 名称或代码</code>（支持中文模糊搜索，如 <code>/stock 英伟达</code>）\n"
            "• 卡片按钮支持 <b>日/周/月 K 线、量化技术诊断、财务体检、最新舆情、AI 深度研报、交互式看板</b>。\n\n"
            "<b>2. 自然语言 AI 投研对话（带思考进度）</b>\n"
            "• 直接发消息即可对话，AI 会实时展示工具调取与思考进度：\n"
            "  - <i>「贵州茅台和五粮液谁的盈利能力更强？」</i>\n"
            "  - <i>「腾讯和阿里巴巴最近有什么利好利空？」</i>\n\n"
            "<b>3. 主动服务与常用命令</b>\n"
            "• <code>/market</code> — 全球大盘指数（A股 + 港股 + 美股）\n"
            "• <code>/watch</code> — 查看与管理我的自选股\n"
            "• <code>/brief</code> — 订阅/预览每日盘前早报与盘后晚报\n"
            "• <code>/alert 600519 &gt; 1600</code> — 设置价格突破/跌破预警\n"
            "• <code>/clear</code> — 清空当前 AI 对话记忆"
        )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def market_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        loading = await update.message.reply_text("🌍 正在获取全球大盘指数（A股 / 港股 / 美股）...")
        indices = await self.market_data.get_market_overview()
        await self._safe_edit_msg(
            loading,
            format_market_overview(indices),
            reply_markup=market_overview_keyboard(self.settings.webapp_url, update.effective_user.id),
        )

    async def stock_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        query = " ".join(context.args).strip() if context.args else ""
        if not query:
            await update.message.reply_text(
                "请提供股票代码或名称，例如：<code>/stock 600519</code>、<code>/stock 腾讯</code> 或 <code>/stock NVDA</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        loading = await update.message.reply_text(f"🔍 正在检索「{esc(query)}」...", parse_mode=ParseMode.HTML)
        try:
            candidates = await self.market_data.search_stocks(query, limit=6)
            if not candidates:
                await loading.edit_text(f"未找到与「{esc(query)}」匹配的 A 股 / 港股 / 美股标的。", parse_mode=ParseMode.HTML)
                return

            if len(candidates) == 1 or candidates[0].name == query or candidates[0].code.upper() == query.upper():
                await self._render_quote_into(loading, update.effective_user.id, candidates[0].code)
                return

            await loading.edit_text(
                f"🔍 找到多个与「<b>{esc(query)}</b>」匹配的标的，请选择：",
                parse_mode=ParseMode.HTML,
                reply_markup=candidates_keyboard(candidates),
            )
        except Exception as exc:
            await loading.edit_text(f"⚠️ 查询失败：{esc(exc)}", parse_mode=ParseMode.HTML)

    async def watch_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        items = await self.database.get_watchlist(update.effective_user.id)
        kb = (
            watchlist_keyboard(items, self.settings.webapp_url, update.effective_user.id)
            if items
            else market_overview_keyboard(self.settings.webapp_url, update.effective_user.id)
        )
        await update.message.reply_text(format_watchlist(items), parse_mode=ParseMode.HTML, reply_markup=kb)

    async def brief_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user or not update.effective_chat:
            return
        sub = await self.database.get_brief_subscription(update.effective_chat.id, update.effective_user.id)
        await update.message.reply_text(
            format_brief_status(sub, self.settings.morning_brief_time, self.settings.evening_brief_time),
            parse_mode=ParseMode.HTML,
            reply_markup=brief_keyboard(sub),
        )

    async def alert_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user or not update.effective_chat:
            return
        args_text = " ".join(context.args).strip() if context.args else ""
        user_id = update.effective_user.id

        if not args_text or args_text.lower() == "list":
            alerts = await self.database.get_active_alerts(user_id)
            await update.message.reply_text(
                format_alerts(alerts),
                parse_mode=ParseMode.HTML,
                reply_markup=alerts_keyboard(alerts) if alerts else None,
            )
            return

        if args_text.lower().startswith("del "):
            raw_id = args_text.split(maxsplit=1)[1].strip().lstrip("#")
            if raw_id.isdigit() and await self.database.delete_price_alert(user_id, int(raw_id)):
                await update.message.reply_text(f"🗑 已删除预警 #{raw_id}。")
            else:
                await update.message.reply_text("未找到对应编号的预警。")
            return

        match = ALERT_CMD_RE.match(args_text)
        if not match:
            await update.message.reply_text(
                "格式示例：\n• <code>/alert 600519 &gt; 1600</code>\n• <code>/alert NVDA &lt; 120</code>\n• <code>/alert list</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        raw_symbol, op, raw_price = match.groups()
        direction: Literal["above", "below"] = (
            "above" if op.lower() in (">", ">=", "above", "高于") else "below"
        )
        target_price = float(raw_price)

        loading = await update.message.reply_text(f"⏳ 正在校验标的 {esc(raw_symbol)} 并创建预警...", parse_mode=ParseMode.HTML)
        try:
            quote = await self.market_data.get_quote(raw_symbol)
            alert = await self.database.add_price_alert(
                chat_id=update.effective_chat.id,
                user_id=user_id,
                code=quote.code,
                name=quote.name,
                market_type=quote.market_type,
                direction=direction,
                target_price=target_price,
            )
            sym = "≥" if direction == "above" else "≤"
            await loading.edit_text(
                f"✅ <b>价格预警已创建</b>（<code>#{alert.id}</code>）\n\n"
                f"标的：<b>{esc(quote.name)}</b> (<code>{esc(quote.ts_code)}</code>)\n"
                f"当前价：<code>{quote.close:.2f} {esc(quote.currency)}</code>\n"
                f"触发条件：{sym} <code>{target_price:.2f} {esc(quote.currency)}</code>",
                parse_mode=ParseMode.HTML,
            )
        except Exception as exc:
            await loading.edit_text(f"⚠️ 创建预警失败：{esc(exc)}", parse_mode=ParseMode.HTML)

    async def clear_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_chat:
            return
        await self.database.clear_history(update.effective_chat.id)
        await update.message.reply_text("🧹 已清空当前会话的 AI 对话记忆。")

    # ------------------------------------------------------------------
    # Natural language text handler
    # ------------------------------------------------------------------

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text or not update.effective_chat or not update.effective_user:
            return
        text = update.message.text.strip()
        if not text:
            return

        # Fast path: direct CN / HK / US symbol opens the interactive quote card with loading state
        parsed = parse_stock_symbol(text)
        if parsed is not None:
            loading = await update.message.reply_text(
                f"⏳ 正在获取 <code>{esc(parsed.ts_code)}</code> 实时行情...",
                parse_mode=ParseMode.HTML,
            )
            await self._render_quote_into(loading, update.effective_user.id, parsed.code)
            return

        # Natural language -> Financial AI Agent with live thinking/tool progress
        await update.message.chat.send_action(ChatAction.TYPING)
        status_msg = await update.message.reply_text("🧠 正在思考并准备调取实时市场数据...")

        async def _on_progress(progress_text: str) -> None:
            await self._safe_edit_msg(status_msg, markdown_to_telegram_html(progress_text))

        try:
            reply = await self.agent.chat(
                update.effective_chat.id,
                text,
                on_progress=_on_progress,
            )
            html_reply = markdown_to_telegram_html(reply)
            chunks = split_message(html_reply)
            await self._safe_edit_msg(status_msg, chunks[0])
            for chunk in chunks[1:]:
                await update.message.reply_text(chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception as exc:
            logger.exception("Agent chat error: %s", exc)
            await status_msg.edit_text(f"⚠️ 分析过程中发生错误，请稍后重试。\n({exc})")

    # ------------------------------------------------------------------
    # InlineKeyboard callbacks
    # ------------------------------------------------------------------

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if not query or not query.data or not query.message or not update.effective_user or not update.effective_chat:
            return

        parts = query.data.split(":")
        action = parts[0]
        user_id = update.effective_user.id
        chat_id = update.effective_chat.id

        # Give instant tactile feedback on the button tap
        toast_map = {
            "market": "正在刷新全球大盘...",
            "quote": "正在拉取最新行情...",
            "kline": "正在绘制专业 K 线图...",
            "kline_edit": "正在切换 K 线周期...",
            "tech": "正在计算量化技术指标...",
            "finance": "正在获取财报数据...",
            "news": "正在抓取最新舆情...",
            "report": "正在启动 AI 深度研报...",
        }
        if action != "watch":
            await query.answer(toast_map.get(action, "处理中..."))

        try:
            if action == "market":
                indices = await self.market_data.get_market_overview()
                await self._safe_edit_msg(
                    query.message,
                    format_market_overview(indices),
                    reply_markup=market_overview_keyboard(self.settings.webapp_url, user_id),
                )
            elif action == "watchlist":
                items = await self.database.get_watchlist(user_id)
                kb = (
                    watchlist_keyboard(items, self.settings.webapp_url, user_id)
                    if items
                    else market_overview_keyboard(self.settings.webapp_url, user_id)
                )
                await query.message.reply_text(format_watchlist(items), parse_mode=ParseMode.HTML, reply_markup=kb)
            elif action == "quote" and len(parts) >= 2:
                code = parts[1]
                loading = await query.message.reply_text(f"⏳ 正在获取 <code>{esc(code)}</code> 最新行情...", parse_mode=ParseMode.HTML)
                await self._render_quote_into(loading, user_id, code)
            elif action in ("kline", "kline_edit") and len(parts) >= 3:
                code = parts[1]
                period: Literal["daily", "weekly", "monthly"] = (
                    parts[2] if parts[2] in ("daily", "weekly", "monthly") else "daily"
                )
                period_cn = {"daily": "日K", "weekly": "周K", "monthly": "月K"}[period]
                loading = None
                if action == "kline":
                    loading = await query.message.reply_text(
                        f"📊 正在绘制 <code>{esc(code)}</code> {period_cn}线图（MA + 成交量 + MACD）...",
                        parse_mode=ParseMode.HTML,
                    )
                await query.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
                candidate, df = await self.market_data.get_kline(code, period=period)
                png_bytes = await self.charts.render_kline(df, candidate.code, candidate.name, period=period)
                caption = f"📊 <b>{esc(candidate.name)}</b> (<code>{esc(candidate.ts_code)}</code>) · {period_cn} (MA5/10/20/60 + 量能 + MACD)"
                kb = kline_switcher_keyboard(
                    candidate.code,
                    active_period=period,
                    webapp_url=self.settings.webapp_url,
                    user_id=user_id,
                )

                if action == "kline_edit":
                    await query.edit_message_media(
                        media=InputMediaPhoto(media=png_bytes, caption=caption, parse_mode=ParseMode.HTML),
                        reply_markup=kb,
                    )
                else:
                    if loading:
                        await loading.delete()
                    await query.message.reply_photo(
                        photo=png_bytes,
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        reply_markup=kb,
                    )
            elif action == "tech" and len(parts) >= 2:
                code = parts[1]
                loading = await query.message.reply_text(f"📐 正在对 <code>{esc(code)}</code> 进行多指标量化技术诊断...", parse_mode=ParseMode.HTML)
                candidate, df = await self.market_data.get_kline(code, period="daily", days=180)
                report = TechnicalAnalyzer.analyze(candidate.code, candidate.name, df)
                in_watch = await self.database.is_in_watchlist(user_id, candidate.code)
                await self._safe_edit_msg(
                    loading,
                    format_technical_report(report),
                    reply_markup=stock_actions_keyboard(candidate.code, in_watch, self.settings.webapp_url, user_id),
                )
            elif action == "finance" and len(parts) >= 2:
                code = parts[1]
                loading = await query.message.reply_text(f"💰 正在获取 <code>{esc(code)}</code> 财务体检数据...", parse_mode=ParseMode.HTML)
                fin = await self.market_data.get_finance(code)
                in_watch = await self.database.is_in_watchlist(user_id, fin.code)
                await self._safe_edit_msg(
                    loading,
                    format_finance(fin),
                    reply_markup=stock_actions_keyboard(fin.code, in_watch, self.settings.webapp_url, user_id),
                )
            elif action == "news" and len(parts) >= 2:
                code = parts[1]
                loading = await query.message.reply_text(f"📰 正在抓取 <code>{esc(code)}</code> 最新舆情资讯...", parse_mode=ParseMode.HTML)
                candidate, items = await self.market_data.get_news(code, limit=6)
                in_watch = await self.database.is_in_watchlist(user_id, candidate.code)
                await self._safe_edit_msg(
                    loading,
                    format_news(candidate, items),
                    reply_markup=stock_actions_keyboard(candidate.code, in_watch, self.settings.webapp_url, user_id),
                )
            elif action == "report" and len(parts) >= 2:
                code = parts[1]
                await query.message.chat.send_action(ChatAction.TYPING)
                status_msg = await query.message.reply_text("🤖 正在启动四维数据采集与 AI 深度研报...")

                async def _on_report_progress(progress_text: str) -> None:
                    await self._safe_edit_msg(status_msg, markdown_to_telegram_html(progress_text))

                report_text = await self.agent.generate_deep_report(code, on_progress=_on_report_progress)
                chunks = split_message(markdown_to_telegram_html(report_text))
                await self._safe_edit_msg(status_msg, chunks[0])
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
                    await self.database.add_watchlist(user_id, candidate.code, candidate.name, candidate.market_type)
                    in_watch = True
                    notice = f"已将 {candidate.name}({candidate.code}) 加入自选"
                await query.edit_message_reply_markup(
                    reply_markup=stock_actions_keyboard(candidate.code, in_watch, self.settings.webapp_url, user_id)
                )
                await query.answer(notice, show_alert=False)
            elif action == "brief":
                sub_action = parts[1] if len(parts) >= 2 else "open"
                if sub_action == "open":
                    sub = await self.database.get_brief_subscription(chat_id, user_id)
                    await query.message.reply_text(
                        format_brief_status(sub, self.settings.morning_brief_time, self.settings.evening_brief_time),
                        parse_mode=ParseMode.HTML,
                        reply_markup=brief_keyboard(sub),
                    )
                elif sub_action == "toggle" and len(parts) >= 3:
                    kind = parts[2]
                    cur = await self.database.get_brief_subscription(chat_id, user_id)
                    sub = await self.database.set_brief_subscription(
                        chat_id,
                        user_id,
                        morning_enabled=(not cur.morning_enabled) if kind == "morning" else None,
                        evening_enabled=(not cur.evening_enabled) if kind == "evening" else None,
                    )
                    await self._safe_edit_msg(
                        query.message,
                        format_brief_status(sub, self.settings.morning_brief_time, self.settings.evening_brief_time),
                        reply_markup=brief_keyboard(sub),
                    )
                elif sub_action == "preview" and len(parts) >= 3 and self.scheduler:
                    kind_lit: Literal["morning", "evening"] = "morning" if parts[2] == "morning" else "evening"
                    loading = await query.message.reply_text("⏳ 正在生成实时简报预览（大盘 + 自选 + AI 简评）...")
                    text = await self.scheduler.build_briefing_text(kind_lit, user_id)
                    chunks = split_message(text)
                    await self._safe_edit_msg(loading, chunks[0])
                    for chunk in chunks[1:]:
                        await query.message.reply_text(chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
            elif action == "alert_del" and len(parts) >= 2:
                alert_id = int(parts[1])
                await self.database.delete_price_alert(user_id, alert_id)
                alerts = await self.database.get_active_alerts(user_id)
                await self._safe_edit_msg(
                    query.message,
                    format_alerts(alerts),
                    reply_markup=alerts_keyboard(alerts) if alerts else None,
                )
        except Exception as exc:
            logger.exception("Callback %s failed: %s", query.data, exc)
            await query.message.reply_text(f"⚠️ 操作失败：{esc(exc)}", parse_mode=ParseMode.HTML)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _render_quote_into(self, msg, user_id: int, code: str) -> None:
        try:
            quote = await self.market_data.get_quote(code)
            in_watch = await self.database.is_in_watchlist(user_id, quote.code)
            await self._safe_edit_msg(
                msg,
                format_stock_quote(quote),
                reply_markup=stock_actions_keyboard(quote.code, in_watch, self.settings.webapp_url, user_id),
            )
        except Exception as exc:
            await msg.edit_text(f"⚠️ 查询失败：{esc(exc)}", parse_mode=ParseMode.HTML)

    @staticmethod
    async def _safe_edit_msg(msg, text: str, reply_markup=None) -> None:
        try:
            await msg.edit_text(
                text,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        except BadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                raise
