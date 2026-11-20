"""Pydantic domain models for market data, technical diagnosis, news, and watchlist."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class StockCandidate(BaseModel):
    code: str = Field(..., description="6-digit A-share stock code, e.g. 600519")
    ts_code: str = Field(..., description="Exchange-qualified code, e.g. 600519.SH")
    name: str
    market: str = ""


class IndexQuote(BaseModel):
    code: str
    name: str
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
    total_mv: float | None = None  # Total market cap (亿元)


class FinanceSummary(BaseModel):
    code: str
    name: str
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
    created_at: str
