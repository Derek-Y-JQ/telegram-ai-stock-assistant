"""InlineKeyboard builders for modern non-spammy Telegram interactions."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from stock_bot.models import StockCandidate, WatchlistItem


def stock_actions_keyboard(code: str, in_watchlist: bool = False) -> InlineKeyboardMarkup:
    watch_label = "✅ 已在自选" if in_watchlist else "⭐ 加自选"
    return InlineKeyboardMarkup(
        [
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
            [
                InlineKeyboardButton("🔄 刷新行情", callback_data=f"quote:{code}"),
            ],
        ]
    )


def kline_switcher_keyboard(code: str, active_period: str) -> InlineKeyboardMarkup:
    def _label(period: str, text: str) -> str:
        return f"• {text} •" if period == active_period else text

    return InlineKeyboardMarkup(
        [
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
    )


def market_overview_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 刷新大盘", callback_data="market:refresh"),
                InlineKeyboardButton("⭐ 我的自选", callback_data="watchlist:open"),
            ]
        ]
    )


def watchlist_keyboard(items: list[WatchlistItem]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for item in items:
        row.append(InlineKeyboardButton(f"{item.name} ({item.code})", callback_data=f"quote:{item.code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("📊 大盘概览", callback_data="market:refresh")])
    return InlineKeyboardMarkup(rows)


def candidates_keyboard(candidates: list[StockCandidate]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"{c.name} ({c.ts_code})", callback_data=f"quote:{c.code}")]
        for c in candidates
    ]
    return InlineKeyboardMarkup(rows)
