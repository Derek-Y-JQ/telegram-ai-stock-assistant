"""InlineKeyboard builders including Telegram Mini App WebApp buttons and briefing controls."""

from __future__ import annotations

from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from stock_bot.models import BriefSubscription, PriceAlert, StockCandidate, WatchlistItem


def _webapp_button(
    webapp_url: str | None,
    label: str,
    symbol: str | None = None,
    user_id: int | None = None,
) -> InlineKeyboardButton | None:
    if not webapp_url or not webapp_url.startswith("https://"):
        return None
    params: dict[str, str] = {}
    if symbol:
        params["symbol"] = symbol
    if user_id:
        params["user_id"] = str(user_id)
    base = webapp_url.rstrip("/")
    full_url = f"{base}/?{urlencode(params)}" if params else f"{base}/"
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=full_url))


def stock_actions_keyboard(
    code: str,
    in_watchlist: bool = False,
    webapp_url: str | None = None,
    user_id: int | None = None,
) -> InlineKeyboardMarkup:
    watch_label = "✅ 已在自选" if in_watchlist else "⭐ 加自选"
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("📊 日K线", callback_data=f"kline:{code}:daily"),
            InlineKeyboardButton("📅 周K线", callback_data=f"kline:{code}:weekly"),
            InlineKeyboardButton("🗓 月K线", callback_data=f"kline:{code}:monthly"),
        ],
        [
            InlineKeyboardButton("📐 技术诊断", callback_data=f"tech:{code}"),
            InlineKeyboardButton("💰 财务体检", callback_data=f"finance:{code}"),
            InlineKeyboardButton("📰 最新舆情", callback_data=f"news:{code}"),
        ],
        [
            InlineKeyboardButton("🤖 AI 深度研报", callback_data=f"report:{code}"),
            InlineKeyboardButton(watch_label, callback_data=f"watch:{code}"),
        ],
    ]
    web_btn = _webapp_button(webapp_url, "📱 打开交互式 K 线看板", symbol=code, user_id=user_id)
    if web_btn:
        rows.append([web_btn])
    rows.append([InlineKeyboardButton("🔄 刷新行情", callback_data=f"quote:{code}")])
    return InlineKeyboardMarkup(rows)


def kline_switcher_keyboard(
    code: str,
    active_period: str,
    webapp_url: str | None = None,
    user_id: int | None = None,
) -> InlineKeyboardMarkup:
    def _label(period: str, text: str) -> str:
        return f"• {text} •" if period == active_period else text

    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(_label("daily", "日K"), callback_data=f"kline_edit:{code}:daily"),
            InlineKeyboardButton(_label("weekly", "周K"), callback_data=f"kline_edit:{code}:weekly"),
            InlineKeyboardButton(_label("monthly", "月K"), callback_data=f"kline_edit:{code}:monthly"),
        ],
        [
            InlineKeyboardButton("📐 技术诊断", callback_data=f"tech:{code}"),
            InlineKeyboardButton("🤖 AI 研报", callback_data=f"report:{code}"),
        ],
    ]
    web_btn = _webapp_button(webapp_url, "📱 交互式缩放 K 线", symbol=code, user_id=user_id)
    if web_btn:
        rows.append([web_btn])
    return InlineKeyboardMarkup(rows)


def market_overview_keyboard(
    webapp_url: str | None = None,
    user_id: int | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton("🔄 刷新大盘", callback_data="market:refresh"),
            InlineKeyboardButton("⭐ 我的自选", callback_data="watchlist:open"),
        ],
        [
            InlineKeyboardButton("⏰ 早晚报订阅", callback_data="brief:open"),
        ],
    ]
    web_btn = _webapp_button(webapp_url, "📱 打开交互式看板", user_id=user_id)
    if web_btn:
        rows.append([web_btn])
    return InlineKeyboardMarkup(rows)


def watchlist_keyboard(
    items: list[WatchlistItem],
    webapp_url: str | None = None,
    user_id: int | None = None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for item in items:
        row.append(InlineKeyboardButton(f"{item.name} ({item.code})", callback_data=f"quote:{item.code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    web_btn = _webapp_button(webapp_url, "📱 在看板中打开自选", user_id=user_id)
    if web_btn:
        rows.append([web_btn])
    rows.append([InlineKeyboardButton("🌍 全球大盘", callback_data="market:refresh")])
    return InlineKeyboardMarkup(rows)


def brief_keyboard(sub: BriefSubscription) -> InlineKeyboardMarkup:
    m_btn = "☀️ 关闭盘前早报" if sub.morning_enabled else "☀️ 开启盘前早报"
    e_btn = "🌙 关闭盘后晚报" if sub.evening_enabled else "🌙 开启盘后晚报"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(m_btn, callback_data="brief:toggle:morning"),
                InlineKeyboardButton(e_btn, callback_data="brief:toggle:evening"),
            ],
            [
                InlineKeyboardButton("⚡ 立即预览早报", callback_data="brief:preview:morning"),
                InlineKeyboardButton("⚡ 立即预览晚报", callback_data="brief:preview:evening"),
            ],
        ]
    )


def alerts_keyboard(alerts: list[PriceAlert]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"🗑 删除 #{a.id} ({a.code} {'>' if a.direction == 'above' else '<'} {a.target_price:.2f})", callback_data=f"alert_del:{a.id}")]
        for a in alerts[:8]
    ]
    return InlineKeyboardMarkup(rows)


def candidates_keyboard(candidates: list[StockCandidate]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"[{c.market_type}] {c.name} ({c.ts_code})", callback_data=f"quote:{c.code}")]
        for c in candidates
    ]
    return InlineKeyboardMarkup(rows)
