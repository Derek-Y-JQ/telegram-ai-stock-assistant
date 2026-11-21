"""Bilingual (English default / Chinese) localization helpers."""

from __future__ import annotations

from stock_bot.models import Lang, MarketType

DEFAULT_LANG: Lang = "en"

MARKET_BADGE: dict[Lang, dict[MarketType, str]] = {
    "en": {"CN": "🇨🇳 CN", "HK": "🇭🇰 HK", "US": "🇺🇸 US", "SG": "🇸🇬 SG"},
    "zh": {"CN": "🇨🇳 A股", "HK": "🇭🇰 港股", "US": "🇺🇸 美股", "SG": "🇸🇬 新加坡"},
}

INDEX_NAME_EN: dict[str, str] = {
    "000001.SH": "SSE Composite",
    "399001.SZ": "SZSE Component",
    "399006.SZ": "ChiNext",
    "000688.SH": "STAR 50",
    "HSI": "Hang Seng",
    "HSTECH": "Hang Seng Tech",
    "SPX": "S&P 500",
    "IXIC": "NASDAQ",
    "DJI": "Dow Jones",
    "STI": "Straits Times (STI)",
}

INDEX_NAME_ZH: dict[str, str] = {
    "000001.SH": "上证指数",
    "399001.SZ": "深证成指",
    "399006.SZ": "创业板指",
    "000688.SH": "科创50",
    "HSI": "恒生指数",
    "HSTECH": "恒生科技",
    "SPX": "标普500",
    "IXIC": "纳斯达克",
    "DJI": "道琼斯",
    "STI": "海峡时报指数 (STI)",
}


def localize_index_name(code: str, fallback: str, lang: Lang) -> str:
    table = INDEX_NAME_EN if lang == "en" else INDEX_NAME_ZH
    return table.get(code, fallback)


def market_badge(market_type: MarketType, lang: Lang) -> str:
    return MARKET_BADGE[lang].get(market_type, market_type)
