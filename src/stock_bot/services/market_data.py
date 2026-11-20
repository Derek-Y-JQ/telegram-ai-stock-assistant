"""Unified async A-share market data service (AkShare primary, optional Tushare fallback)."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Literal

import akshare as ak
import pandas as pd

from stock_bot.models import FinanceSummary, IndexQuote, NewsItem, StockCandidate, StockQuote
from stock_bot.storage.cache import AsyncTTLCache

logger = logging.getLogger(__name__)

CODE_PATTERN = re.compile(r"^(?:sh|sz|bj)?(\d{6})(?:\.(?:SH|SZ|BJ))?$", re.IGNORECASE)


def normalize_stock_code(raw: str) -> tuple[str, str, str]:
    """Normalize an A-share stock code.

    Returns:
        (code_6, ts_code, tx_symbol)
        e.g. ("600519", "600519.SH", "sh600519")
    """
    cleaned = raw.strip()
    match = CODE_PATTERN.match(cleaned)
    if not match:
        raise ValueError(f"无效的 A 股代码格式: {raw}")

    code = match.group(1)
    if code.startswith(("6", "5")):
        return code, f"{code}.SH", f"sh{code}"
    if code.startswith(("0", "3", "1", "2")):
        return code, f"{code}.SZ", f"sz{code}"
    if code.startswith(("4", "8", "9")):
        return code, f"{code}.BJ", f"bj{code}"
    raise ValueError(f"无法识别的交易所前缀: {raw}")


def _safe_float(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, str):
        val = val.strip().replace("%", "").replace(",", "")
        if not val or val in {"-", "--", "nan", "None"}:
            return None
    try:
        num = float(val)
        return None if pd.isna(num) else num
    except (TypeError, ValueError):
        return None


class MarketDataService:
    """Async wrapper around AkShare (with optional Tushare Pro fallback) and TTL caching."""

    def __init__(
        self,
        cache: AsyncTTLCache | None = None,
        tushare_token: str | None = None,
    ) -> None:
        self.cache = cache or AsyncTTLCache(default_ttl=300)
        self._pro: Any | None = None
        if tushare_token:
            try:
                import tushare as ts

                ts.set_token(tushare_token)
                self._pro = ts.pro_api()
                logger.info("Tushare Pro initialized as optional enrichment provider.")
            except Exception as exc:
                logger.warning("Failed to initialize Tushare Pro (falling back to AkShare): %s", exc)

    # ------------------------------------------------------------------
    # Stock directory & fuzzy search
    # ------------------------------------------------------------------

    async def _get_stock_directory(self) -> list[StockCandidate]:
        async def _fetch() -> list[StockCandidate]:
            df = await asyncio.to_thread(ak.stock_info_a_code_name)
            candidates: list[StockCandidate] = []
            for _, row in df.iterrows():
                raw_code = str(row.get("code", "")).zfill(6)
                name = str(row.get("name", "")).strip()
                if not raw_code or not name:
                    continue
                try:
                    code, ts_code, _ = normalize_stock_code(raw_code)
                    market = ts_code.split(".")[1]
                    candidates.append(
                        StockCandidate(code=code, ts_code=ts_code, name=name, market=market)
                    )
                except ValueError:
                    continue
            return candidates

        return await self.cache.get_or_set("stock_directory", _fetch, ttl=86400)

    async def search_stocks(self, query: str, limit: int = 5) -> list[StockCandidate]:
        """Search A-share stocks by 6-digit code or Chinese name substring."""
        q = query.strip()
        if not q:
            return []

        # Direct code match first
        try:
            code, ts_code, _ = normalize_stock_code(q)
            directory = await self._get_stock_directory()
            for item in directory:
                if item.code == code:
                    return [item]
            return [StockCandidate(code=code, ts_code=ts_code, name=code, market=ts_code.split(".")[1])]
        except ValueError:
            pass

        directory = await self._get_stock_directory()
        q_lower = q.lower()

        exact: list[StockCandidate] = []
        prefix: list[StockCandidate] = []
        contains: list[StockCandidate] = []

        for item in directory:
            name_lower = item.name.lower()
            if name_lower == q_lower or item.code == q_lower:
                exact.append(item)
            elif name_lower.startswith(q_lower) or item.code.startswith(q_lower):
                prefix.append(item)
            elif q_lower in name_lower:
                contains.append(item)

        return (exact + prefix + contains)[:limit]

    async def resolve_stock(self, query: str) -> StockCandidate:
        """Resolve a user query (code or name) to the best matching StockCandidate."""
        matches = await self.search_stocks(query, limit=1)
        if not matches:
            raise LookupError(f"未找到与「{query}」匹配的 A 股标的，请检查股票代码或名称。")
        return matches[0]

    # ------------------------------------------------------------------
    # Major A-share indices
    # ------------------------------------------------------------------

    async def get_market_overview(self) -> list[IndexQuote]:
        """Fetch major A-share index quotes (SSE, SZSE, ChiNext, STAR 50)."""
        async def _fetch() -> list[IndexQuote]:
            targets = [
                ("sh000001", "000001.SH", "上证指数"),
                ("sz399001", "399001.SZ", "深证成指"),
                ("sz399006", "399006.SZ", "创业板指"),
                ("sh000688", "000688.SH", "科创50"),
            ]
            results: list[IndexQuote] = []
            for symbol, code, name in targets:
                try:
                    df = await asyncio.to_thread(ak.stock_zh_index_daily_em, symbol=symbol)
                    if df is None or df.empty:
                        continue
                    latest = df.iloc[-1]
                    close = float(latest["close"])
                    pre_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else float(latest["open"])
                    change_amount = close - pre_close
                    change_pct = (change_amount / pre_close * 100.0) if pre_close else 0.0
                    results.append(
                        IndexQuote(
                            code=code,
                            name=name,
                            close=round(close, 2),
                            change_pct=round(change_pct, 2),
                            change_amount=round(change_amount, 2),
                            volume=_safe_float(latest.get("volume")),
                            amount=_safe_float(latest.get("amount")),
                            trade_date=str(latest.get("date", ""))[:10],
                        )
                    )
                except Exception as exc:
                    logger.warning("Failed to fetch index %s: %s", symbol, exc)
            return results

        return await self.cache.get_or_set("market_overview", _fetch, ttl=120)

    # ------------------------------------------------------------------
    # Historical K-line OHLCV
    # ------------------------------------------------------------------

    async def get_kline(
        self,
        code_or_name: str,
        period: Literal["daily", "weekly", "monthly"] = "daily",
        days: int = 180,
    ) -> tuple[StockCandidate, pd.DataFrame]:
        """Fetch adjusted OHLCV DataFrame indexed by DatetimeIndex.

        Columns: Open, High, Low, Close, Volume
        """
        candidate = await self.resolve_stock(code_or_name)
        cache_key = f"kline:{candidate.code}:{period}:{days}"

        async def _fetch() -> pd.DataFrame:
            end_dt = datetime.now()
            # Pull enough history so MA60 / weekly / monthly indicators have warm-up bars
            lookback_days = max(days, 180)
            if period == "weekly":
                lookback_days = max(days, 730)
            elif period == "monthly":
                lookback_days = max(days, 1825)
            start_dt = end_dt - timedelta(days=lookback_days)

            df = await asyncio.to_thread(
                ak.stock_zh_a_hist,
                symbol=candidate.code,
                period=period,
                start_date=start_dt.strftime("%Y%m%d"),
                end_date=end_dt.strftime("%Y%m%d"),
                adjust="qfq",
            )
            if df is None or df.empty:
                raise LookupError(f"暂无 {candidate.name}({candidate.code}) 的历史行情数据。")

            col_map = {
                "日期": "Date",
                "开盘": "Open",
                "最高": "High",
                "最低": "Low",
                "收盘": "Close",
                "成交量": "Volume",
                "成交额": "Amount",
                "涨跌幅": "ChangePct",
                "涨跌额": "ChangeAmt",
                "换手率": "Turnover",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            df["Date"] = pd.to_datetime(df["Date"])
            df = df.sort_values("Date").set_index("Date")
            for col in ("Open", "High", "Low", "Close", "Volume"):
                df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["Open", "High", "Low", "Close"])
            return df

        df = await self.cache.get_or_set(cache_key, _fetch, ttl=180)
        return candidate, df.copy()

    # ------------------------------------------------------------------
    # Stock quote
    # ------------------------------------------------------------------

    async def get_quote(self, code_or_name: str) -> StockQuote:
        """Fetch latest quote and basic info for a single A-share stock."""
        candidate, df = await self.get_kline(code_or_name, period="daily", days=30)
        cache_key = f"quote:{candidate.code}"

        async def _fetch() -> StockQuote:
            latest = df.iloc[-1]
            pre_close = float(df.iloc[-2]["Close"]) if len(df) >= 2 else float(latest["Open"])
            close = float(latest["Close"])

            change_pct = _safe_float(latest.get("ChangePct"))
            change_amt = _safe_float(latest.get("ChangeAmt"))
            if change_pct is None and pre_close:
                change_amt = close - pre_close
                change_pct = (change_amt / pre_close) * 100.0

            industry = ""
            total_mv: float | None = None
            pe_ttm: float | None = None
            pb: float | None = None

            try:
                info_df = await asyncio.to_thread(ak.stock_individual_info_em, symbol=candidate.code)
                if info_df is not None and not info_df.empty:
                    info_map = dict(zip(info_df["item"], info_df["value"], strict=False))
                    industry = str(info_map.get("行业", "") or "")
                    mv_raw = _safe_float(info_map.get("总市值"))
                    if mv_raw is not None:
                        total_mv = round(mv_raw / 1e8, 2)
            except Exception as exc:
                logger.debug("Optional individual info fetch failed for %s: %s", candidate.code, exc)

            # Enrich valuation via Tushare if configured
            if self._pro is not None:
                try:
                    ts_df = await asyncio.to_thread(
                        self._pro.daily_basic,
                        ts_code=candidate.ts_code,
                        fields="trade_date,pe_ttm,pb,total_mv",
                    )
                    if ts_df is not None and not ts_df.empty:
                        row = ts_df.iloc[0]
                        pe_ttm = _safe_float(row.get("pe_ttm"))
                        pb = _safe_float(row.get("pb"))
                        if total_mv is None:
                            mv_wan = _safe_float(row.get("total_mv"))
                            if mv_wan is not None:
                                total_mv = round(mv_wan / 1e4, 2)
                except Exception as exc:
                    logger.debug("Optional Tushare valuation fetch failed: %s", exc)

            return StockQuote(
                code=candidate.code,
                ts_code=candidate.ts_code,
                name=candidate.name,
                market=candidate.market,
                industry=industry,
                trade_date=df.index[-1].strftime("%Y-%m-%d"),
                open=round(float(latest["Open"]), 2),
                close=round(close, 2),
                high=round(float(latest["High"]), 2),
                low=round(float(latest["Low"]), 2),
                pre_close=round(pre_close, 2),
                change_pct=round(change_pct or 0.0, 2),
                change_amount=round(change_amt, 2) if change_amt is not None else None,
                volume=float(latest["Volume"]),
                amount=float(_safe_float(latest.get("Amount")) or 0.0),
                turnover_rate=_safe_float(latest.get("Turnover")),
                pe_ttm=round(pe_ttm, 2) if pe_ttm is not None else None,
                pb=round(pb, 2) if pb is not None else None,
                total_mv=total_mv,
            )

        return await self.cache.get_or_set(cache_key, _fetch, ttl=120)

    # ------------------------------------------------------------------
    # Financial indicators
    # ------------------------------------------------------------------

    async def get_finance(self, code_or_name: str) -> FinanceSummary:
        """Fetch latest financial summary indicators."""
        candidate = await self.resolve_stock(code_or_name)
        cache_key = f"finance:{candidate.code}"

        async def _fetch() -> FinanceSummary:
            # Prefer AkShare financial abstract (free, no token needed)
            try:
                df = await asyncio.to_thread(ak.stock_financial_analysis_indicator, symbol=candidate.code)
                if df is not None and not df.empty:
                    df = df.sort_values("日期", ascending=False)
                    latest = df.iloc[0]
                    return FinanceSummary(
                        code=candidate.code,
                        name=candidate.name,
                        report_date=str(latest.get("日期", ""))[:10],
                        eps=_safe_float(latest.get("摊薄每股收益(元)") or latest.get("加权每股收益(元)")),
                        roe=_safe_float(latest.get("净资产收益率(%)") or latest.get("加权净资产收益率(%)")),
                        bps=_safe_float(latest.get("每股净资产_调整后(元)") or latest.get("每股净资产_调整前(元)")),
                        gross_margin=_safe_float(latest.get("销售毛利率(%)")),
                        net_margin=_safe_float(latest.get("销售净利率(%)")),
                        debt_to_assets=_safe_float(latest.get("资产负债率(%)")),
                        current_ratio=_safe_float(latest.get("流动比率")),
                        revenue_yoy=_safe_float(latest.get("主营业务收入增长率(%)")),
                        profit_yoy=_safe_float(latest.get("净利润增长率(%)")),
                    )
            except Exception as exc:
                logger.warning("AkShare finance fetch failed for %s: %s", candidate.code, exc)

            # Fallback to Tushare if configured
            if self._pro is not None:
                ts_df = await asyncio.to_thread(self._pro.fina_indicator, ts_code=candidate.ts_code)
                if ts_df is not None and not ts_df.empty:
                    row = ts_df.iloc[0]
                    return FinanceSummary(
                        code=candidate.code,
                        name=candidate.name,
                        report_date=str(row.get("end_date") or row.get("ann_date", "")),
                        eps=_safe_float(row.get("eps")),
                        roe=_safe_float(row.get("roe")),
                        bps=_safe_float(row.get("bps")),
                        gross_margin=_safe_float(row.get("grossprofit_margin")),
                        net_margin=_safe_float(row.get("netprofit_margin")),
                        debt_to_assets=_safe_float(row.get("debt_to_assets")),
                        current_ratio=_safe_float(row.get("current_ratio")),
                        revenue_yoy=_safe_float(row.get("tr_yoy")),
                        profit_yoy=_safe_float(row.get("netprofit_yoy")),
                    )

            raise LookupError(f"暂未获取到 {candidate.name}({candidate.code}) 的财务指标数据。")

        return await self.cache.get_or_set(cache_key, _fetch, ttl=3600)

    # ------------------------------------------------------------------
    # Latest news
    # ------------------------------------------------------------------

    async def get_news(self, code_or_name: str, limit: int = 8) -> tuple[StockCandidate, list[NewsItem]]:
        """Fetch recent stock-related news articles."""
        candidate = await self.resolve_stock(code_or_name)
        cache_key = f"news:{candidate.code}:{limit}"

        async def _fetch() -> list[NewsItem]:
            df = await asyncio.to_thread(ak.stock_news_em, symbol=candidate.code)
            if df is None or df.empty:
                return []
            items: list[NewsItem] = []
            for _, row in df.head(limit).iterrows():
                items.append(
                    NewsItem(
                        title=str(row.get("新闻标题", "")).strip(),
                        content=str(row.get("新闻内容", "")).strip()[:500],
                        publish_time=str(row.get("发布时间", "")).strip(),
                        source=str(row.get("文章来源", "")).strip(),
                        url=str(row.get("新闻链接", "")).strip(),
                    )
                )
            return items

        items = await self.cache.get_or_set(cache_key, _fetch, ttl=300)
        return candidate, items
