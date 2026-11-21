"""Pydantic domain models for CN/HK/US/SG market data, technical diagnosis, alerts, and watchlist."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

MarketType = Literal["CN", "HK", "US", "SG"]
Lang = Literal["en", "zh"]


class StockCandidate(BaseModel):
    code: str = Field(..., description="Canonical display code, e.g. 600519, 00700, AAPL, D05.SI")
    ts_code: str = Field(..., description="Market-qualified code, e.g. 600519.SH, 00700.HK, AAPL, D05.SI")
    name: str
    market: str = ""
    market_type: MarketType = "CN"
    yf_symbol: str = ""


class IndexQuote(BaseModel):
    code: str
    name: str
    market_type: MarketType = "CN"
    close: float
    change_pct: float
    change_amount: float | None = None
    volume: float | None = None
    amount: float | None = None
    trade_date: str = ""


class StockQuote(BaseModel):
    code: str
    ts_code: str
    name: str
    market: str = ""
    market_type: MarketType = "CN"
    currency: str = "CNY"
    industry: str = ""
    trade_date: str = ""
    open: float
    close: float
    high: float
    low: float
    pre_close: float | None = None
    change_pct: float
    change_amount: float | None = None
    volume: float = 0.0
    amount: float = 0.0
    turnover_rate: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None
    total_mv: float | None = None  # Total market cap (in 100M / 亿 local currency)


class FinanceSummary(BaseModel):
    code: str
    name: str
    market_type: MarketType = "CN"
    currency: str = "CNY"
    report_date: str = ""
    eps: float | None = None
    roe: float | None = None
    bps: float | None = None
    gross_margin: float | None = None
    net_margin: float | None = None
    debt_to_assets: float | None = None
    current_ratio: float | None = None
    revenue_yoy: float | None = None
    profit_yoy: float | None = None
    pe_ttm: float | None = None
    pb: float | None = None


class NewsItem(BaseModel):
    title: str
    content: str = ""
    publish_time: str = ""
    source: str = ""
    url: str = ""


class TechnicalSignal(BaseModel):
    name: str
    status: Literal["bullish", "bearish", "neutral"]
    detail: str


class TechnicalReport(BaseModel):
    code: str
    name: str
    market_type: MarketType = "CN"
    trade_date: str
    latest_close: float
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    rsi14: float | None = None
    macd_dif: float | None = None
    macd_dea: float | None = None
    macd_hist: float | None = None
    boll_upper: float | None = None
    boll_mid: float | None = None
    boll_lower: float | None = None
    kdj_k: float | None = None
    kdj_d: float | None = None
    kdj_j: float | None = None
    atr14: float | None = None
    volatility_20d: float | None = None
    support_level: float | None = None
    resistance_level: float | None = None
    score: int = Field(..., ge=0, le=100, description="Composite technical score 0-100")
    rating: str = Field(..., description="Human-readable rating label")
    signals: list[TechnicalSignal] = Field(default_factory=list)


class WatchlistItem(BaseModel):
    user_id: int
    code: str
    name: str
    market_type: MarketType = "CN"
    created_at: str


class BriefSubscription(BaseModel):
    chat_id: int
    user_id: int
    morning_enabled: bool = False
    evening_enabled: bool = False


class PriceAlert(BaseModel):
    id: int
    chat_id: int
    user_id: int
    code: str
    name: str
    market_type: MarketType = "CN"
    direction: Literal["above", "below"]
    target_price: float
    triggered: bool = False
    created_at: str
