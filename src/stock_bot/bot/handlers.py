"""Bilingual (EN default / ZH) Telegram handlers with live interactive feedback and /lang switcher."""

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
    language_keyboard,
    market_overview_keyboard,
    stock_actions_keyboard,
    watchlist_keyboard,
)
from stock_bot.config import Settings
from stock_bot.models import Lang
from stock_bot.services.chart import ChartService
from stock_bot.services.market_data import MarketDataService, parse_stock_symbol
from stock_bot.services.scheduler import BriefingScheduler
from stock_bot.services.technical import TechnicalAnalyzer
from stock_bot.storage.database import Database

logger = logging.getLogger(__name__)

ALERT_CMD_RE = re.compile(r"^(\S+)\s*(>|>=|<|<=|above|below|高于|低于)\s*(\d+(?:\.\d+)?)$", re.IGNORECASE)


class BotHandlers:
    """Routes Telegram updates with immediate loading indicators, streaming AI thinking, and EN/ZH i18n."""

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

    async def _lang(self, user_id: int) -> Lang:
        return await self.database.get_user_lang(user_id)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        lang = await self._lang(user_id)
        en = lang == "en"

        loading = await update.message.reply_text(
            "⏳ Loading global market overview (US / SG / HK / CN)..."
            if en
            else "⏳ 正在拉取全球核心大盘数据（美股 / 新加坡 / 港股 / A股）..."
        )
        try:
            indices = await self.market_data.get_market_overview()
            overview = format_market_overview(indices, lang=lang)
        except Exception as exc:
            logger.warning("Failed to fetch market overview on /start: %s", exc)
            overview = "🌍 Welcome to <b>Global AI Stock Assistant</b>!" if en else "🌍 欢迎使用 <b>全球股市智能投研助理</b>！"

        if en:
            welcome = (
                f"👋 Welcome to <b>Global AI Stock Assistant</b> (US · SG · HK · CN)\n\n"
                f"{overview}\n\n"
                "✨ <b>Quick Tips:</b>\n"
                "• Send a ticker directly: <code>NVDA</code> · <code>D05.SI</code> · <code>00700</code> · <code>600519</code>\n"
                "• Search by name: <code>/stock DBS</code> · <code>/stock Nvidia</code> · <code>/stock Tencent</code>\n"
                "• Ask anything: <i>\"Compare DBS and OCBC fundamentals and technicals\"</i>\n"
                "• <code>/market</code> Markets · <code>/watch</code> Watchlist · <code>/brief</code> Briefings · <code>/alert</code> Alerts · <code>/lang</code> Language"
            )
        else:
            welcome = (
                f"👋 你好！欢迎使用 <b>全球股市智能投研助理</b>（美股 · 新加坡 · 港股 · A股）\n\n"
                f"{overview}\n\n"
                "✨ <b>快捷用法：</b>\n"
                "• 直接发代码：<code>NVDA</code> · <code>D05.SI</code> · <code>00700</code> · <code>600519</code>\n"
                "• 搜索标的：<code>/stock 星展</code> · <code>/stock 英伟达</code> · <code>/stock 茅台</code>\n"
                "• 自然语言对话：<i>「对比一下星展银行和华侨银行的财务与技术面」</i>\n"
                "• <code>/market</code> 全球大盘 · <code>/watch</code> 自选 · <code>/brief</code> 早晚报 · <code>/alert</code> 预警 · <code>/lang</code> 切换语言"
            )

        await self._safe_edit_msg(
            loading,
            welcome,
            reply_markup=market_overview_keyboard(self.settings.webapp_url, user_id, lang),
        )

    async def help_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        lang = await self._lang(update.effective_user.id)
        if lang == "en":
            text = (
                "📖 <b>User Guide</b>\n\n"
                "<b>1. Instant Stock Cards (US / SGX / HK / CN)</b>\n"
                "• Send any ticker: <code>AAPL</code> (US), <code>D05.SI</code> or <code>DBS</code> (SG), <code>00700</code> (HK), <code>600519</code> (CN)\n"
                "• Or search: <code>/stock keyword</code>\n"
                "• Tap inline buttons for <b>K-line charts, Technicals, Financials, News, AI Brief & Interactive Terminal</b>.\n\n"
                "<b>2. Natural Language AI Research</b>\n"
                "• Just chat naturally — AI calls live tools and streams progress:\n"
                "  - <i>\"Compare NVDA and AAPL valuation and momentum\"</i>\n"
                "  - <i>\"What's the latest news on DBS Group?\"</i>\n\n"
                "<b>3. Commands</b>\n"
                "• <code>/market</code> — Global indices (US / SG / HK / CN)\n"
                "• <code>/watch</code> — Manage watchlist\n"
                "• <code>/brief</code> — Subscribe/preview daily morning & evening briefings\n"
                "• <code>/alert NVDA &gt; 150</code> — Set price alerts\n"
                "• <code>/lang</code> — Switch between English & 中文\n"
                "• <code>/clear</code> — Clear AI chat memory"
            )
        else:
            text = (
                "📖 <b>使用指南（全球四市场版）</b>\n\n"
                "<b>1. 快速查股卡片（美股 / 新加坡 / 港股 / A股）</b>\n"
                "• 直接发送代码：<code>AAPL</code>（美股）、<code>D05.SI</code> / <code>DBS</code>（新加坡）、<code>00700</code>（港股）、<code>600519</code>（A股）\n"
                "• 或使用 <code>/stock 名称或代码</code> 模糊搜索\n"
                "• 卡片按钮支持 <b>日/周/月 K 线、量化技术诊断、财务体检、最新舆情、AI 深度研报、交互式看板</b>。\n\n"
                "<b>2. 自然语言 AI 投研对话（带思考进度）</b>\n"
                "• 直接发消息即可对话，AI 会实时展示工具调取与思考进度。\n\n"
                "<b>3. 常用命令</b>\n"
                "• <code>/market</code> — 全球大盘指数（美股/新加坡/港股/A股）\n"
                "• <code>/watch</code> — 查看与管理我的自选股\n"
                "• <code>/brief</code> — 订阅/预览每日盘前早报与盘后晚报\n"
                "• <code>/alert D05.SI &gt; 45</code> — 设置价格预警\n"
                "• <code>/lang</code> — 切换英文 / 中文（AI 回复同步切换）\n"
                "• <code>/clear</code> — 清空当前 AI 对话记忆"
            )
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    async def lang_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        if context.args:
            arg = context.args[0].strip().lower()
            if arg in ("en", "english"):
                await self.database.set_user_lang(user_id, "en")
                await update.message.reply_text("✅ Language switched to <b>English</b>. Bot UI & AI replies will now use English.", parse_mode=ParseMode.HTML)
                return
            if arg in ("zh", "cn", "chinese", "中文"):
                await self.database.set_user_lang(user_id, "zh")
                await update.message.reply_text("✅ 已切换为 <b>简体中文</b>，界面与 AI 回复都将使用中文。", parse_mode=ParseMode.HTML)
                return

        cur = await self._lang(user_id)
        prompt = (
            "🌐 <b>Language Settings</b>\n\nSelect your preferred language (applies to Bot UI, Mini App, and AI responses):"
            if cur == "en"
            else "🌐 <b>语言设置</b>\n\n选择你的偏好语言（将同时应用于机器人界面、交互看板与 AI 回复）："
        )
        await update.message.reply_text(prompt, parse_mode=ParseMode.HTML, reply_markup=language_keyboard(cur))

    async def market_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        lang = await self._lang(user_id)
        loading = await update.message.reply_text(
            "🌍 Fetching global indices (US / SG / HK / CN)..."
            if lang == "en"
            else "🌍 正在获取全球大盘指数（美股 / 新加坡 / 港股 / A股）..."
        )
        indices = await self.market_data.get_market_overview()
        await self._safe_edit_msg(
            loading,
            format_market_overview(indices, lang=lang),
            reply_markup=market_overview_keyboard(self.settings.webapp_url, user_id, lang),
        )

    async def stock_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        lang = await self._lang(user_id)
        en = lang == "en"
        query = " ".join(context.args).strip() if context.args else ""
        if not query:
            await update.message.reply_text(
                "Please provide a ticker or name, e.g. <code>/stock NVDA</code>, <code>/stock DBS</code>, or <code>/stock 600519</code>"
                if en
                else "请提供股票代码或名称，例如：<code>/stock NVDA</code>、<code>/stock 星展</code> 或 <code>/stock 600519</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        loading = await update.message.reply_text(
            f"🔍 Searching for <code>{esc(query)}</code>..." if en else f"🔍 正在检索「{esc(query)}」...",
            parse_mode=ParseMode.HTML,
        )
        try:
            candidates = await self.market_data.search_stocks(query, limit=6)
            if not candidates:
                await loading.edit_text(
                    f"No matching US / SG / HK / CN stock found for '{esc(query)}'."
                    if en
                    else f"未找到与「{esc(query)}」匹配的美股 / 新加坡 / 港股 / A股标的。",
                    parse_mode=ParseMode.HTML,
                )
                return

            if len(candidates) == 1 or candidates[0].name.lower() == query.lower() or candidates[0].code.upper() == query.upper():
                await self._render_quote_into(loading, user_id, candidates[0].code, lang)
                return

            await loading.edit_text(
                (f"🔍 Multiple matches for <b>{esc(query)}</b>, please select:")
                if en
                else (f"🔍 找到多个与「<b>{esc(query)}</b>」匹配的标的，请选择："),
                parse_mode=ParseMode.HTML,
                reply_markup=candidates_keyboard(candidates),
            )
        except Exception as exc:
            await loading.edit_text(f"⚠️ {esc(exc)}", parse_mode=ParseMode.HTML)

    async def watch_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        user_id = update.effective_user.id
        lang = await self._lang(user_id)
        items = await self.database.get_watchlist(user_id)
        kb = (
            watchlist_keyboard(items, self.settings.webapp_url, user_id, lang)
            if items
            else market_overview_keyboard(self.settings.webapp_url, user_id, lang)
        )
        await update.message.reply_text(format_watchlist(items, lang=lang), parse_mode=ParseMode.HTML, reply_markup=kb)

    async def brief_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user or not update.effective_chat:
            return
        user_id = update.effective_user.id
        lang = await self._lang(user_id)
        sub = await self.database.get_brief_subscription(update.effective_chat.id, user_id)
        await update.message.reply_text(
            format_brief_status(sub, self.settings.morning_brief_time, self.settings.evening_brief_time, lang),
            parse_mode=ParseMode.HTML,
            reply_markup=brief_keyboard(sub, lang),
        )

    async def alert_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user or not update.effective_chat:
            return
        user_id = update.effective_user.id
        lang = await self._lang(user_id)
        en = lang == "en"
        args_text = " ".join(context.args).strip() if context.args else ""

        if not args_text or args_text.lower() == "list":
            alerts = await self.database.get_active_alerts(user_id)
            await update.message.reply_text(
                format_alerts(alerts, lang=lang),
                parse_mode=ParseMode.HTML,
                reply_markup=alerts_keyboard(alerts, lang) if alerts else None,
            )
            return

        if args_text.lower().startswith("del "):
            raw_id = args_text.split(maxsplit=1)[1].strip().lstrip("#")
            if raw_id.isdigit() and await self.database.delete_price_alert(user_id, int(raw_id)):
                await update.message.reply_text(f"🗑 Deleted alert #{raw_id}." if en else f"🗑 已删除预警 #{raw_id}。")
            else:
                await update.message.reply_text("Alert ID not found." if en else "未找到对应编号的预警。")
            return

        match = ALERT_CMD_RE.match(args_text)
        if not match:
            await update.message.reply_text(
                "Examples:\n• <code>/alert NVDA &gt; 150</code>\n• <code>/alert D05.SI &lt; 40</code>\n• <code>/alert list</code>"
                if en
                else "格式示例：\n• <code>/alert NVDA &gt; 150</code>\n• <code>/alert D05.SI &lt; 40</code>\n• <code>/alert list</code>",
                parse_mode=ParseMode.HTML,
            )
            return

        raw_symbol, op, raw_price = match.groups()
        direction: Literal["above", "below"] = (
            "above" if op.lower() in (">", ">=", "above", "高于") else "below"
        )
        target_price = float(raw_price)

        loading = await update.message.reply_text(
            f"⏳ Verifying <code>{esc(raw_symbol)}</code> and creating alert..."
            if en
            else f"⏳ 正在校验标的 <code>{esc(raw_symbol)}</code> 并创建预警...",
            parse_mode=ParseMode.HTML,
        )
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
            if en:
                msg = (
                    f"✅ <b>Price Alert Created</b> (<code>#{alert.id}</code>)\n\n"
                    f"Ticker: <b>{esc(quote.name)}</b> (<code>{esc(quote.ts_code)}</code>)\n"
                    f"Current: <code>{quote.close:.2f} {esc(quote.currency)}</code>\n"
                    f"Trigger: {sym} <code>{target_price:.2f} {esc(quote.currency)}</code>"
                )
            else:
                msg = (
                    f"✅ <b>价格预警已创建</b>（<code>#{alert.id}</code>）\n\n"
                    f"标的：<b>{esc(quote.name)}</b> (<code>{esc(quote.ts_code)}</code>)\n"
                    f"当前价：<code>{quote.close:.2f} {esc(quote.currency)}</code>\n"
                    f"触发条件：{sym} <code>{target_price:.2f} {esc(quote.currency)}</code>"
                )
            await loading.edit_text(msg, parse_mode=ParseMode.HTML)
        except Exception as exc:
            await loading.edit_text(f"⚠️ {esc(exc)}", parse_mode=ParseMode.HTML)

    async def clear_cmd(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_chat or not update.effective_user:
            return
        lang = await self._lang(update.effective_user.id)
        await self.database.clear_history(update.effective_chat.id)
        await update.message.reply_text(
            "🧹 Conversation memory cleared." if lang == "en" else "🧹 已清空当前会话的 AI 对话记忆。"
        )

    # ------------------------------------------------------------------
    # Natural language text handler
    # ------------------------------------------------------------------

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text or not update.effective_chat or not update.effective_user:
            return
        text = update.message.text.strip()
        if not text:
            return

        user_id = update.effective_user.id
        lang = await self._lang(user_id)
        en = lang == "en"

        # Fast path: direct US / SG / HK / CN symbol
        parsed = parse_stock_symbol(text)
        if parsed is not None:
            loading = await update.message.reply_text(
                f"⏳ Fetching live quote for <code>{esc(parsed.ts_code)}</code>..."
                if en
                else f"⏳ 正在获取 <code>{esc(parsed.ts_code)}</code> 实时行情...",
                parse_mode=ParseMode.HTML,
            )
            await self._render_quote_into(loading, user_id, parsed.code, lang)
            return

        # Natural language -> Financial AI Agent with live thinking/tool progress
        await update.message.chat.send_action(ChatAction.TYPING)
        status_msg = await update.message.reply_text(
            "🧠 Thinking and preparing live market data lookups..."
            if en
            else "🧠 正在思考并准备调取实时市场数据..."
        )

        async def _on_progress(progress_text: str) -> None:
            await self._safe_edit_msg(status_msg, markdown_to_telegram_html(progress_text))

        try:
            reply = await self.agent.chat(
                update.effective_chat.id,
                text,
                lang=lang,
                on_progress=_on_progress,
            )
            html_reply = markdown_to_telegram_html(reply)
            chunks = split_message(html_reply)
            await self._safe_edit_msg(status_msg, chunks[0])
            for chunk in chunks[1:]:
                await update.message.reply_text(chunk, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception as exc:
            logger.exception("Agent chat error: %s", exc)
            await status_msg.edit_text(
                f"⚠️ An error occurred during analysis. Please try again.\n({exc})"
                if en
                else f"⚠️ 分析过程中发生错误，请稍后重试。\n({exc})"
            )

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
        lang = await self._lang(user_id)
        en = lang == "en"

        if action == "lang" and len(parts) >= 2 and parts[1] in ("en", "zh"):
            new_lang: Lang = "en" if parts[1] == "en" else "zh"
            await self.database.set_user_lang(user_id, new_lang)
            await query.answer("Switched to English" if new_lang == "en" else "已切换为中文")
            msg = (
                "✅ Language set to <b>English</b>. Bot UI, Mini App, and AI replies will now use English."
                if new_lang == "en"
                else "✅ 语言已切换为 <b>简体中文</b>，机器人界面、交互看板和 AI 回复均已同步切换。"
            )
            await self._safe_edit_msg(query.message, msg, reply_markup=language_keyboard(new_lang))
            return

        toast_map = (
            {
                "market": "Refreshing global indices...",
                "quote": "Fetching latest quote...",
                "kline": "Rendering K-line chart...",
                "kline_edit": "Switching timeframe...",
                "tech": "Running technical analysis...",
                "finance": "Loading financials...",
                "news": "Fetching latest news...",
                "report": "Starting AI research brief...",
            }
            if en
            else {
                "market": "正在刷新全球大盘...",
                "quote": "正在拉取最新行情...",
                "kline": "正在绘制专业 K 线图...",
                "kline_edit": "正在切换 K 线周期...",
                "tech": "正在计算量化技术指标...",
                "finance": "正在获取财报数据...",
                "news": "正在抓取最新舆情...",
                "report": "正在启动 AI 深度研报...",
            }
        )
        if action != "watch":
            await query.answer(toast_map.get(action, "Working..." if en else "处理中..."))

        try:
            if action == "market":
                indices = await self.market_data.get_market_overview()
                await self._safe_edit_msg(
                    query.message,
                    format_market_overview(indices, lang=lang),
                    reply_markup=market_overview_keyboard(self.settings.webapp_url, user_id, lang),
                )
            elif action == "watchlist":
                items = await self.database.get_watchlist(user_id)
                kb = (
                    watchlist_keyboard(items, self.settings.webapp_url, user_id, lang)
                    if items
                    else market_overview_keyboard(self.settings.webapp_url, user_id, lang)
                )
                await query.message.reply_text(format_watchlist(items, lang=lang), parse_mode=ParseMode.HTML, reply_markup=kb)
            elif action == "quote" and len(parts) >= 2:
                code = parts[1]
                loading = await query.message.reply_text(
                    f"⏳ Fetching quote for <code>{esc(code)}</code>..." if en else f"⏳ 正在获取 <code>{esc(code)}</code> 最新行情...",
                    parse_mode=ParseMode.HTML,
                )
                await self._render_quote_into(loading, user_id, code, lang)
            elif action in ("kline", "kline_edit") and len(parts) >= 3:
                code = parts[1]
                period: Literal["daily", "weekly", "monthly"] = (
                    parts[2] if parts[2] in ("daily", "weekly", "monthly") else "daily"
                )
                period_lbl = (
                    {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}[period]
                    if en
                    else {"daily": "日K", "weekly": "周K", "monthly": "月K"}[period]
                )
                loading = None
                if action == "kline":
                    loading = await query.message.reply_text(
                        f"📊 Rendering <code>{esc(code)}</code> {period_lbl} chart..."
                        if en
                        else f"📊 正在绘制 <code>{esc(code)}</code> {period_lbl}线图（MA + 成交量 + MACD）...",
                        parse_mode=ParseMode.HTML,
                    )
                await query.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
                candidate, df = await self.market_data.get_kline(code, period=period)
                png_bytes = await self.charts.render_kline(df, candidate.code, candidate.name, period=period)
                caption = (
                    f"📊 <b>{esc(candidate.name)}</b> (<code>{esc(candidate.ts_code)}</code>) · {period_lbl} (MA5/10/20/60 + Vol + MACD)"
                    if en
                    else f"📊 <b>{esc(candidate.name)}</b> (<code>{esc(candidate.ts_code)}</code>) · {period_lbl} (MA5/10/20/60 + 量能 + MACD)"
                )
                kb = kline_switcher_keyboard(
                    candidate.code,
                    active_period=period,
                    webapp_url=self.settings.webapp_url,
                    user_id=user_id,
                    lang=lang,
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
                loading = await query.message.reply_text(
                    f"📐 Running technical diagnosis for <code>{esc(code)}</code>..."
                    if en
                    else f"📐 正在对 <code>{esc(code)}</code> 进行多指标量化技术诊断...",
                    parse_mode=ParseMode.HTML,
                )
                candidate, df = await self.market_data.get_kline(code, period="daily", days=180)
                report = TechnicalAnalyzer.analyze(candidate.code, candidate.name, df, lang=lang)
                in_watch = await self.database.is_in_watchlist(user_id, candidate.code)
                await self._safe_edit_msg(
                    loading,
                    format_technical_report(report, lang=lang),
                    reply_markup=stock_actions_keyboard(candidate.code, in_watch, self.settings.webapp_url, user_id, lang),
                )
            elif action == "finance" and len(parts) >= 2:
                code = parts[1]
                loading = await query.message.reply_text(
                    f"💰 Loading financials for <code>{esc(code)}</code>..."
                    if en
                    else f"💰 正在获取 <code>{esc(code)}</code> 财务体检数据...",
                    parse_mode=ParseMode.HTML,
                )
                fin = await self.market_data.get_finance(code)
                in_watch = await self.database.is_in_watchlist(user_id, fin.code)
                await self._safe_edit_msg(
                    loading,
                    format_finance(fin, lang=lang),
                    reply_markup=stock_actions_keyboard(fin.code, in_watch, self.settings.webapp_url, user_id, lang),
                )
            elif action == "news" and len(parts) >= 2:
                code = parts[1]
                loading = await query.message.reply_text(
                    f"📰 Fetching latest news for <code>{esc(code)}</code>..."
                    if en
                    else f"📰 正在抓取 <code>{esc(code)}</code> 最新舆情资讯...",
                    parse_mode=ParseMode.HTML,
                )
                candidate, items = await self.market_data.get_news(code, limit=6)
                in_watch = await self.database.is_in_watchlist(user_id, candidate.code)
                await self._safe_edit_msg(
                    loading,
                    format_news(candidate, items, lang=lang),
                    reply_markup=stock_actions_keyboard(candidate.code, in_watch, self.settings.webapp_url, user_id, lang),
                )
            elif action == "report" and len(parts) >= 2:
                code = parts[1]
                await query.message.chat.send_action(ChatAction.TYPING)
                status_msg = await query.message.reply_text(
                    "🤖 Gathering multi-factor data & generating AI research brief..."
                    if en
                    else "🤖 正在启动四维数据采集与 AI 深度研报..."
                )

                async def _on_report_progress(progress_text: str) -> None:
                    await self._safe_edit_msg(status_msg, markdown_to_telegram_html(progress_text))

                report_text = await self.agent.generate_deep_report(code, lang=lang, on_progress=_on_report_progress)
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
                    notice = (
                        f"Removed {candidate.name} ({candidate.code}) from watchlist"
                        if en
                        else f"已将 {candidate.name}({candidate.code}) 移出自选"
                    )
                else:
                    await self.database.add_watchlist(user_id, candidate.code, candidate.name, candidate.market_type)
                    in_watch = True
                    notice = (
                        f"Added {candidate.name} ({candidate.code}) to watchlist"
                        if en
                        else f"已将 {candidate.name}({candidate.code}) 加入自选"
                    )
                await query.edit_message_reply_markup(
                    reply_markup=stock_actions_keyboard(candidate.code, in_watch, self.settings.webapp_url, user_id, lang)
                )
                await query.answer(notice, show_alert=False)
            elif action == "brief":
                sub_action = parts[1] if len(parts) >= 2 else "open"
                if sub_action == "open":
                    sub = await self.database.get_brief_subscription(chat_id, user_id)
                    await query.message.reply_text(
                        format_brief_status(sub, self.settings.morning_brief_time, self.settings.evening_brief_time, lang),
                        parse_mode=ParseMode.HTML,
                        reply_markup=brief_keyboard(sub, lang),
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
                        format_brief_status(sub, self.settings.morning_brief_time, self.settings.evening_brief_time, lang),
                        reply_markup=brief_keyboard(sub, lang),
                    )
                elif sub_action == "preview" and len(parts) >= 3 and self.scheduler:
                    kind_lit: Literal["morning", "evening"] = "morning" if parts[2] == "morning" else "evening"
                    loading = await query.message.reply_text(
                        "⏳ Generating live briefing preview (markets + watchlist + AI)..."
                        if en
                        else "⏳ 正在生成实时简报预览（大盘 + 自选 + AI 简评）..."
                    )
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
                    format_alerts(alerts, lang=lang),
                    reply_markup=alerts_keyboard(alerts, lang) if alerts else None,
                )
        except Exception as exc:
            logger.exception("Callback %s failed: %s", query.data, exc)
            await query.message.reply_text(f"⚠️ {esc(exc)}", parse_mode=ParseMode.HTML)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _render_quote_into(self, msg, user_id: int, code: str, lang: Lang) -> None:
        try:
            quote = await self.market_data.get_quote(code)
            in_watch = await self.database.is_in_watchlist(user_id, quote.code)
            await self._safe_edit_msg(
                msg,
                format_stock_quote(quote, lang=lang),
                reply_markup=stock_actions_keyboard(quote.code, in_watch, self.settings.webapp_url, user_id, lang),
            )
        except Exception as exc:
            await msg.edit_text(f"⚠️ {esc(exc)}", parse_mode=ParseMode.HTML)

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
