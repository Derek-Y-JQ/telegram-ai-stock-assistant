"""Bilingual InlineKeyboard builders with Telegram Mini App WebApp buttons and language switch."""

from __future__ import annotations

from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from stock_bot.models import BriefSubscription, Lang, PriceAlert, StockCandidate, WatchlistItem


def _webapp_button(
    webapp_url: str | None,
    label: str,
    symbol: str | None = None,
    user_id: int | None = None,
    lang: Lang = "en",
) -> InlineKeyboardButton | None:
    if not webapp_url or not webapp_url.startswith("https://"):
        return None
    params: dict[str, str] = {"lang": lang}
    if symbol:
        params["symbol"] = symbol
    if user_id:
        params["user_id"] = str(user_id)
    base = webapp_url.rstrip("/")
    full_url = f"{base}/?{urlencode(params)}"
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=full_url))


def language_keyboard(current: Lang) -> InlineKeyboardMarkup:
    en_lbl = "✅ English" if current == "en" else "🇺🇸 English"
    zh_lbl = "✅ 中文" if current == "zh" else "🇨🇳 中文"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(en_lbl, callback_data="lang:en"),
                InlineKeyboardButton(zh_lbl, callback_data="lang:zh"),
            ]
        ]
    )


def stock_actions_keyboard(
    code: str,
    in_watchlist: bool = False,
    webapp_url: str | None = None,
    user_id: int | None = None,
    lang: Lang = "en",
) -> InlineKeyboardMarkup:
    en = lang == "en"
    watch_label = ("✅ Watching" if in_watchlist else "⭐ Watchlist") if en else ("✅ 已在自选" if in_watchlist else "⭐ 加自选")
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("📊 Daily" if en else "📊 日K线", callback_data=f"kline:{code}:daily"),
            InlineKeyboardButton("📅 Weekly" if en else "📅 周K线", callback_data=f"kline:{code}:weekly"),
            InlineKeyboardButton("🗓 Monthly" if en else "🗓 月K线", callback_data=f"kline:{code}:monthly"),
        ],
        [
            InlineKeyboardButton("📐 Technicals" if en else "📐 技术诊断", callback_data=f"tech:{code}"),
            InlineKeyboardButton("💰 Financials" if en else "💰 财务体检", callback_data=f"finance:{code}"),
            InlineKeyboardButton("📰 News" if en else "📰 最新舆情", callback_data=f"news:{code}"),
        ],
        [
            InlineKeyboardButton("🤖 AI Research Brief" if en else "🤖 AI 深度研报", callback_data=f"report:{code}"),
            InlineKeyboardButton(watch_label, callback_data=f"watch:{code}"),
        ],
    ]
    web_btn = _webapp_button(
        webapp_url,
        "📱 Interactive Chart Terminal" if en else "📱 打开交互式 K 线看板",
        symbol=code,
        user_id=user_id,
        lang=lang,
    )
    if web_btn:
        rows.append([web_btn])
    rows.append([InlineKeyboardButton("🔄 Refresh Quote" if en else "🔄 刷新行情", callback_data=f"quote:{code}")])
    return InlineKeyboardMarkup(rows)


def kline_switcher_keyboard(
    code: str,
    active_period: str,
    webapp_url: str | None = None,
    user_id: int | None = None,
    lang: Lang = "en",
) -> InlineKeyboardMarkup:
    en = lang == "en"

    def _label(period: str, text: str) -> str:
        return f"• {text} •" if period == active_period else text

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(_label("daily", "1D" if en else "日K"), callback_data=f"kline_edit:{code}:daily"),
            InlineKeyboardButton(_label("weekly", "1W" if en else "周K"), callback_data=f"kline_edit:{code}:weekly"),
            InlineKeyboardButton(_label("monthly", "1M" if en else "月K"), callback_data=f"kline_edit:{code}:monthly"),
        ],
        [
            InlineKeyboardButton("📐 Technicals" if en else "📐 技术诊断", callback_data=f"tech:{code}"),
            InlineKeyboardButton("🤖 AI Brief" if en else "🤖 AI 研报", callback_data=f"report:{code}"),
        ],
    ]
    web_btn = _webapp_button(
        webapp_url,
        "📱 Interactive Chart" if en else "📱 交互式缩放 K 线",
        symbol=code,
        user_id=user_id,
        lang=lang,
    )
    if web_btn:
        rows.append([web_btn])
    return InlineKeyboardMarkup(rows)


def market_overview_keyboard(
    webapp_url: str | None = None,
    user_id: int | None = None,
    lang: Lang = "en",
) -> InlineKeyboardMarkup:
    en = lang == "en"
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("🔄 Refresh" if en else "🔄 刷新大盘", callback_data="market:refresh"),
            InlineKeyboardButton("⭐ Watchlist" if en else "⭐ 我的自选", callback_data="watchlist:open"),
        ],
        [
            InlineKeyboardButton("⏰ Briefings" if en else "⏰ 早晚报订阅", callback_data="brief:open"),
            InlineKeyboardButton("🌐 中文" if en else "🌐 English", callback_data="lang:zh" if en else "lang:en"),
        ],
    ]
    web_btn = _webapp_button(
        webapp_url,
        "📱 Open Market Terminal" if en else "📱 打开交互式看板",
        user_id=user_id,
        lang=lang,
    )
    if web_btn:
        rows.append([web_btn])
    return InlineKeyboardMarkup(rows)


def watchlist_keyboard(
    items: list[WatchlistItem],
    webapp_url: str | None = None,
    user_id: int | None = None,
    lang: Lang = "en",
) -> InlineKeyboardMarkup:
    en = lang == "en"
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for item in items:
        row.append(InlineKeyboardButton(f"{item.name} ({item.code})", callback_data=f"quote:{item.code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    web_btn = _webapp_button(
        webapp_url,
        "📱 Open Watchlist in Terminal" if en else "📱 在看板中打开自选",
        user_id=user_id,
        lang=lang,
    )
    if web_btn:
        rows.append([web_btn])
    rows.append([InlineKeyboardButton("🌍 Global Markets" if en else "🌍 全球大盘", callback_data="market:refresh")])
    return InlineKeyboardMarkup(rows)


def brief_keyboard(sub: BriefSubscription, lang: Lang = "en") -> InlineKeyboardMarkup:
    en = lang == "en"
    m_btn = ("☀️ Disable Morning" if sub.morning_enabled else "☀️ Enable Morning") if en else ("☀️ 关闭盘前早报" if sub.morning_enabled else "☀️ 开启盘前早报")
    e_btn = ("🌙 Disable Evening" if sub.evening_enabled else "🌙 Enable Evening") if en else ("🌙 关闭盘后晚报" if sub.evening_enabled else "🌙 开启盘后晚报")
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(m_btn, callback_data="brief:toggle:morning"),
                InlineKeyboardButton(e_btn, callback_data="brief:toggle:evening"),
            ],
            [
                InlineKeyboardButton("⚡ Preview Morning" if en else "⚡ 立即预览早报", callback_data="brief:preview:morning"),
                InlineKeyboardButton("⚡ Preview Evening" if en else "⚡ 立即预览晚报", callback_data="brief:preview:evening"),
            ],
        ]
    )


def alerts_keyboard(alerts: list[PriceAlert], lang: Lang = "en") -> InlineKeyboardMarkup:
    en = lang == "en"
    prefix = "🗑 Delete" if en else "🗑 删除"
    rows = [
        [InlineKeyboardButton(f"{prefix} #{a.id} ({a.code} {'>' if a.direction == 'above' else '<'} {a.target_price:.2f})", callback_data=f"alert_del:{a.id}")]
        for a in alerts[:8]
    ]
    return InlineKeyboardMarkup(rows)


def candidates_keyboard(candidates: list[StockCandidate]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"[{c.market_type}] {c.name} ({c.ts_code})", callback_data=f"quote:{c.code}")]
        for c in candidates
    ]
    return InlineKeyboardMarkup(rows)
