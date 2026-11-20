"""Unified async global market data service supporting A-Share (CN), Hong Kong (HK), and US stocks."""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Literal

import akshare as ak
import httpx
import pandas as pd
import yfinance as yf

from stock_bot.models import (
    FinanceSummary,
    IndexQuote,
    MarketType,
    NewsItem,
    StockCandidate,
    StockQuote,
)
from stock_bot.storage.cache import AsyncTTLCache

logger = logging.getLogger(__name__)

CN_CODE_RE = re.compile(r"^(?:sh|sz|bj)?(\d{6})(?:\.(?:SH|SZ|BJ))?$", re.IGNORECASE)
HK_CODE_RE = re.compile(r"^(?:hk)?(\d{4,5})(?:\.HK)?$", re.IGNORECASE)
US_CODE_RE = re.compile(r"^([A-Z]{1,5}(?:[.-][A-Z])?)(?:\.US)?$", re.IGNORECASE)

# Popular HK & US Chinese aliases for instant natural-language / fuzzy lookup
POPULAR_GLOBAL_ALIASES: dict[str, StockCandidate] = {
    "腾讯": StockCandidate(code="00700", ts_code="00700.HK", name="腾讯控股", market="HK", market_type="HK", yf_symbol="0700.HK"),
    "腾讯控股": StockCandidate(code="00700", ts_code="00700.HK", name="腾讯控股", market="HK", market_type="HK", yf_symbol="0700.HK"),
    "阿里": StockCandidate(code="09988", ts_code="09988.HK", name="阿里巴巴-W", market="HK", market_type="HK", yf_symbol="9988.HK"),
    "阿里巴巴": StockCandidate(code="09988", ts_code="09988.HK", name="阿里巴巴-W", market="HK", market_type="HK", yf_symbol="9988.HK"),
    "美团": StockCandidate(code="03690", ts_code="03690.HK", name="美团-W", market="HK", market_type="HK", yf_symbol="3690.HK"),
    "小米": StockCandidate(code="01810", ts_code="01810.HK", name="小米集团-W", market="HK", market_type="HK", yf_symbol="1810.HK"),
    "小米集团": StockCandidate(code="01810", ts_code="01810.HK", name="小米集团-W", market="HK", market_type="HK", yf_symbol="1810.HK"),
    "京东": StockCandidate(code="09618", ts_code="09618.HK", name="京东集团-SW", market="HK", market_type="HK", yf_symbol="9618.HK"),
    "网易": StockCandidate(code="09999", ts_code="09999.HK", name="网易-S", market="HK", market_type="HK", yf_symbol="9999.HK"),
    "百度": StockCandidate(code="09888", ts_code="09888.HK", name="百度集团-SW", market="HK", market_type="HK", yf_symbol="9888.HK"),
    "快手": StockCandidate(code="01024", ts_code="01024.HK", name="快手-W", market="HK", market_type="HK", yf_symbol="1024.HK"),
    "港交所": StockCandidate(code="00388", ts_code="00388.HK", name="香港交易所", market="HK", market_type="HK", yf_symbol="0388.HK"),
    "汇丰": StockCandidate(code="00005", ts_code="00005.HK", name="汇丰控股", market="HK", market_type="HK", yf_symbol="0005.HK"),
    "苹果": StockCandidate(code="AAPL", ts_code="AAPL", name="Apple (苹果)", market="US", market_type="US", yf_symbol="AAPL"),
    "英伟达": StockCandidate(code="NVDA", ts_code="NVDA", name="NVIDIA (英伟达)", market="US", market_type="US", yf_symbol="NVDA"),
    "特斯拉": StockCandidate(code="TSLA", ts_code="TSLA", name="Tesla (特斯拉)", market="US", market_type="US", yf_symbol="TSLA"),
    "微软": StockCandidate(code="MSFT", ts_code="MSFT", name="Microsoft (微软)", market="US", market_type="US", yf_symbol="MSFT"),
    "谷歌": StockCandidate(code="GOOGL", ts_code="GOOGL", name="Alphabet (谷歌)", market="US", market_type="US", yf_symbol="GOOGL"),
    "亚马逊": StockCandidate(code="AMZN", ts_code="AMZN", name="Amazon (亚马逊)", market="US", market_type="US", yf_symbol="AMZN"),
    "脸书": StockCandidate(code="META", ts_code="META", name="Meta Platforms", market="US", market_type="US", yf_symbol="META"),
    "拼多多": StockCandidate(code="PDD", ts_code="PDD", name="PDD Holdings (拼多多)", market="US", market_type="US", yf_symbol="PDD"),
    "台积电": StockCandidate(code="TSM", ts_code="TSM", name="TSMC (台积电)", market="US", market_type="US", yf_symbol="TSM"),
    "博通": StockCandidate(code="AVGO", ts_code="AVGO", name="Broadcom (博通)", market="US", market_type="US", yf_symbol="AVGO"),
    "奈飞": StockCandidate(code="NFLX", ts_code="NFLX", name="Netflix (奈飞)", market="US", market_type="US", yf_symbol="NFLX"),
    "英特尔": StockCandidate(code="INTC", ts_code="INTC", name="Intel (英特尔)", market="US", market_type="US", yf_symbol="INTC"),
    "超微": StockCandidate(code="AMD", ts_code="AMD", name="AMD", market="US", market_type="US", yf_symbol="AMD"),
    "伯克希尔": StockCandidate(code="BRK-B", ts_code="BRK-B", name="Berkshire Hathaway", market="US", market_type="US", yf_symbol="BRK-B"),
}


def normalize_stock_code(raw: str) -> tuple[str, str, str]:
    """Normalize an A-share stock code.

    Returns:
        (code_6, ts_code, tx_symbol)
        e.g. ("600519", "600519.SH", "sh600519")
    """
    cleaned = raw.strip()
    match = CN_CODE_RE.match(cleaned)
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


def parse_stock_symbol(raw: str) -> StockCandidate | None:
    """Parse a direct CN / HK / US stock symbol into a StockCandidate, or None if not a direct symbol."""
    cleaned = raw.strip()
    if not cleaned:
        return None

    # 1. A-share (6 digits)
    if CN_CODE_RE.match(cleaned):
        try:
            code, ts_code, _ = normalize_stock_code(cleaned)
            exch = ts_code.split(".")[1]
            yf_suffix = "SS" if exch == "SH" else ("SZ" if exch == "SZ" else "BJ")
            return StockCandidate(
                code=code,
                ts_code=ts_code,
                name=code,
                market=exch,
                market_type="CN",
                yf_symbol=f"{code}.{yf_suffix}",
            )
        except ValueError:
            pass

    # 2. Hong Kong (4-5 digits with optional .HK / hk prefix; 4 digits requires .HK or hk prefix)
    hk_match = HK_CODE_RE.match(cleaned)
    if hk_match:
        digits = hk_match.group(1)
        has_hk_marker = cleaned.lower().startswith("hk") or cleaned.upper().endswith(".HK")
        if len(digits) == 5 or has_hk_marker:
            code_5 = digits.zfill(5)
            # yfinance expects 4-digit HK symbols when leading zero is 0 (e.g. 0700.HK)
            yf_code = code_5[1:] if code_5.startswith("0") else code_5
            return StockCandidate(
                code=code_5,
                ts_code=f"{code_5}.HK",
                name=f"{code_5}.HK",
                market="HK",
                market_type="HK",
                yf_symbol=f"{yf_code}.HK",
            )

    # 3. US ticker (1-5 letters, e.g. AAPL, NVDA, BRK.B)
    us_match = US_CODE_RE.match(cleaned)
    if us_match:
        ticker = us_match.group(1).upper().replace(".", "-")
        return StockCandidate(
            code=ticker,
            ts_code=ticker,
            name=ticker,
            market="US",
            market_type="US",
            yf_symbol=ticker,
        )

    return None


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


def _currency_for_market(market_type: MarketType) -> str:
    return {"CN": "CNY", "HK": "HKD", "US": "USD"}[market_type]


class MarketDataService:
    """Async multi-market data service (A-Share via AkShare, HK/US via yfinance + AkShare)."""

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
    # Stock directory & unified search (CN + HK + US)
    # ------------------------------------------------------------------

    async def _get_cn_directory(self) -> list[StockCandidate]:
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
                    yf_suffix = "SS" if market == "SH" else ("SZ" if market == "SZ" else "BJ")
                    candidates.append(
                        StockCandidate(
                            code=code,
                            ts_code=ts_code,
                            name=name,
                            market=market,
                            market_type="CN",
                            yf_symbol=f"{code}.{yf_suffix}",
                        )
                    )
                except ValueError:
                    continue
            return candidates

        return await self.cache.get_or_set("cn_stock_directory", _fetch, ttl=86400)

    async def search_stocks(self, query: str, limit: int = 5) -> list[StockCandidate]:
        """Search stocks across A-Share, HK, and US by code, ticker, or Chinese name."""
        q = query.strip()
        if not q:
            return []

        # 1. Exact alias match for popular HK/US Chinese names
        if q in POPULAR_GLOBAL_ALIASES:
            return [POPULAR_GLOBAL_ALIASES[q]]

        # 2. Direct symbol parse (CN 6-digit, HK 5-digit/.HK, US ticker)
        parsed = parse_stock_symbol(q)
        if parsed is not None:
            if parsed.market_type == "CN":
                try:
                    directory = await self._get_cn_directory()
                    for item in directory:
                        if item.code == parsed.code:
                            return [item]
                except Exception as exc:
                    logger.warning("CN directory fetch failed while resolving %s: %s", parsed.code, exc)
            else:
                # Check if we have a friendly Chinese alias name for this HK/US code
                for alias_cand in POPULAR_GLOBAL_ALIASES.values():
                    if alias_cand.code == parsed.code and alias_cand.market_type == parsed.market_type:
                        return [alias_cand]
            return [parsed]

        # 3. Fuzzy search: popular HK/US aliases + CN directory
        q_lower = q.lower()
        exact: list[StockCandidate] = []
        prefix: list[StockCandidate] = []
        contains: list[StockCandidate] = []
        seen_codes: set[str] = set()

        for alias, cand in POPULAR_GLOBAL_ALIASES.items():
            key = f"{cand.market_type}:{cand.code}"
            if key in seen_codes:
                continue
            if alias.lower() == q_lower or cand.name.lower() == q_lower:
                exact.append(cand)
                seen_codes.add(key)
            elif alias.lower().startswith(q_lower) or q_lower in cand.name.lower():
                prefix.append(cand)
                seen_codes.add(key)

        try:
            directory = await self._get_cn_directory()
            for item in directory:
                name_lower = item.name.lower()
                if name_lower == q_lower or item.code == q_lower:
                    exact.append(item)
                elif name_lower.startswith(q_lower) or item.code.startswith(q_lower):
                    prefix.append(item)
                elif q_lower in name_lower:
                    contains.append(item)
        except Exception as exc:
            logger.warning("CN directory search failed for '%s': %s", q, exc)

        return (exact + prefix + contains)[:limit]

    async def resolve_stock(self, query: str) -> StockCandidate:
        matches = await self.search_stocks(query, limit=1)
        if not matches:
            raise LookupError(f"未找到与「{query}」匹配的 A 股 / 港股 / 美股标的，请检查代码或名称。")
        return matches[0]

    # ------------------------------------------------------------------
    # Global market overview (A-Share + HK + US)
    # ------------------------------------------------------------------

    async def _fetch_cn_indices_tencent(
        self,
        specs: list[tuple[str, str, str, str]],
    ) -> dict[str, IndexQuote]:
        """Fetch all A-share indices in a single fast HTTP request via Tencent qt.gtimg.cn."""
        symbols = ",".join(s[0] for s in specs)
        url = f"https://qt.gtimg.cn/q={symbols}"
        code_map = {s[0]: (s[1], s[2]) for s in specs}
        results: dict[str, IndexQuote] = {}

        try:
            async with httpx.AsyncClient(timeout=6.0, follow_redirects=True) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                text = resp.content.decode("gbk", errors="ignore")
        except Exception as exc:
            logger.warning("Tencent batch CN index fetch failed: %s", exc)
            return results

        for line in text.splitlines():
            line = line.strip()
            if not line or '="' not in line:
                continue
            prefix, rest = line.split('="', 1)
            symbol = prefix.removeprefix("v_").strip()
            if symbol not in code_map:
                continue
            payload = rest.rstrip('";')
            fields = payload.split("~")
            if len(fields) < 33:
                continue
            close = _safe_float(fields[3])
            pre_close = _safe_float(fields[4])
            if close is None or close <= 0:
                continue
            change_amount = _safe_float(fields[31])
            change_pct = _safe_float(fields[32])
            if change_amount is None and pre_close:
                change_amount = close - pre_close
            if change_pct is None and pre_close:
                change_pct = ((close - pre_close) / pre_close) * 100.0
            raw_dt = fields[30] if len(fields) > 30 else ""
            trade_date = (
                f"{raw_dt[0:4]}-{raw_dt[4:6]}-{raw_dt[6:8]}"
                if len(raw_dt) >= 8 and raw_dt[:8].isdigit()
                else ""
            )
            code, name = code_map[symbol]
            results[symbol] = IndexQuote(
                code=code,
                name=name,
                market_type="CN",
                close=round(close, 2),
                change_pct=round(change_pct or 0.0, 2),
                change_amount=round(change_amount, 2) if change_amount is not None else None,
                volume=_safe_float(fields[6]),
                amount=_safe_float(fields[37]) if len(fields) > 37 else None,
                trade_date=trade_date,
            )
        return results

    async def _fetch_cn_index_fallback(
        self,
        symbol: str,
        code: str,
        name: str,
        yf_symbol: str,
    ) -> IndexQuote | None:
        # Fallback 1: yfinance (fast & reliable from overseas cloud servers)
        yf_quote = await self._fetch_yf_index(yf_symbol, code, name, "CN")
        if yf_quote is not None:
            return yf_quote

        # Fallback 2: AkShare (with strict timeout so slow endpoints never block)
        fetchers = [
            getattr(ak, "index_zh_daily_em", None),
            getattr(ak, "stock_zh_index_daily_em", None),
            getattr(ak, "stock_zh_index_daily", None),
            getattr(ak, "stock_zh_index_daily_tx", None),
        ]
        df = None
        for fetcher in fetchers:
            if fetcher is None:
                continue
            try:
                df = await asyncio.wait_for(asyncio.to_thread(fetcher, symbol=symbol), timeout=6.0)
                if df is not None and not df.empty:
                    break
            except Exception as exc:
                logger.debug("Index %s via %s failed: %s", symbol, fetcher.__name__, exc)

        if df is None or df.empty:
            return None

        col_map = {"日期": "date", "开盘": "open", "收盘": "close", "成交量": "volume", "成交额": "amount"}
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        latest = df.iloc[-1]
        close = float(latest["close"])
        pre_close = float(df.iloc[-2]["close"]) if len(df) >= 2 else float(latest["open"])
        change_amount = close - pre_close
        change_pct = (change_amount / pre_close * 100.0) if pre_close else 0.0
        return IndexQuote(
            code=code,
            name=name,
            market_type="CN",
            close=round(close, 2),
            change_pct=round(change_pct, 2),
            change_amount=round(change_amount, 2),
            volume=_safe_float(latest.get("volume")),
            amount=_safe_float(latest.get("amount")),
            trade_date=str(latest.get("date", ""))[:10],
        )

    async def _fetch_yf_index(self, yf_symbol: str, code: str, name: str, market_type: MarketType) -> IndexQuote | None:
        try:
            def _load() -> pd.DataFrame:
                return yf.Ticker(yf_symbol).history(period="5d", interval="1d")

            df = await asyncio.wait_for(asyncio.to_thread(_load), timeout=8.0)
            if df is None or df.empty:
                return None
            latest = df.iloc[-1]
            close = float(latest["Close"])
            pre_close = float(df.iloc[-2]["Close"]) if len(df) >= 2 else float(latest["Open"])
            change_amount = close - pre_close
            change_pct = (change_amount / pre_close * 100.0) if pre_close else 0.0
            return IndexQuote(
                code=code,
                name=name,
                market_type=market_type,
                close=round(close, 2),
                change_pct=round(change_pct, 2),
                change_amount=round(change_amount, 2),
                volume=_safe_float(latest.get("Volume")),
                trade_date=df.index[-1].strftime("%Y-%m-%d"),
            )
        except Exception as exc:
            logger.debug("yfinance index %s failed: %s", yf_symbol, exc)
            return None

    async def get_market_overview(self) -> list[IndexQuote]:
        """Fetch major A-share, Hong Kong, and US market indices concurrently."""
        cached = await self.cache.get("market_overview")
        if cached is not None:
            return cached

        cn_specs = [
            ("sh000001", "000001.SH", "上证指数", "000001.SS"),
            ("sz399001", "399001.SZ", "深证成指", "399001.SZ"),
            ("sz399006", "399006.SZ", "创业板指", "399006.SZ"),
            ("sh000688", "000688.SH", "科创50", "000688.SS"),
        ]

        cn_task = self._fetch_cn_indices_tencent(cn_specs)
        global_tasks = [
            # Hong Kong
            self._fetch_yf_index("^HSI", "HSI", "恒生指数", "HK"),
            self._fetch_yf_index("HSTECH.HK", "HSTECH", "恒生科技", "HK"),
            # US
            self._fetch_yf_index("^GSPC", "SPX", "标普500", "US"),
            self._fetch_yf_index("^IXIC", "IXIC", "纳斯达克", "US"),
            self._fetch_yf_index("^DJI", "DJI", "道琼斯", "US"),
        ]

        cn_map, *global_raw = await asyncio.gather(cn_task, *global_tasks, return_exceptions=True)
        cn_dict: dict[str, IndexQuote] = cn_map if isinstance(cn_map, dict) else {}

        # Fill any missing CN indices via yfinance/AkShare fallback concurrently
        missing_specs = [s for s in cn_specs if s[0] not in cn_dict]
        if missing_specs:
            fallback_res = await asyncio.gather(
                *(self._fetch_cn_index_fallback(*s) for s in missing_specs),
                return_exceptions=True,
            )
            for spec, res in zip(missing_specs, fallback_res, strict=True):
                if isinstance(res, IndexQuote):
                    cn_dict[spec[0]] = res

        cn_ordered = [cn_dict[s[0]] for s in cn_specs if s[0] in cn_dict]
        global_ordered = [r for r in global_raw if isinstance(r, IndexQuote)]
        results = cn_ordered + global_ordered

        # Cache full results for 120s; if CN failed completely, only cache briefly (15s)
        ttl = 120 if cn_ordered else 15
        if results:
            await self.cache.set("market_overview", results, ttl=ttl)
        return results

    # ------------------------------------------------------------------
    # Historical K-line OHLCV (CN + HK + US)
    # ------------------------------------------------------------------

    async def get_kline(
        self,
        code_or_name: str,
        period: Literal["daily", "weekly", "monthly"] = "daily",
        days: int = 180,
    ) -> tuple[StockCandidate, pd.DataFrame]:
        """Fetch adjusted OHLCV DataFrame indexed by DatetimeIndex."""
        candidate = await self.resolve_stock(code_or_name)
        cache_key = f"kline:{candidate.market_type}:{candidate.code}:{period}:{days}"

        async def _fetch() -> pd.DataFrame:
            if candidate.market_type in ("HK", "US"):
                return await self._fetch_yf_kline(candidate, period, days)
            return await self._fetch_cn_kline(candidate, period, days)

        df = await self.cache.get_or_set(cache_key, _fetch, ttl=180)
        return candidate, df.copy()

    async def _fetch_yf_kline(
        self,
        candidate: StockCandidate,
        period: Literal["daily", "weekly", "monthly"],
        days: int,
    ) -> pd.DataFrame:
        interval = {"daily": "1d", "weekly": "1wk", "monthly": "1mo"}[period]
        yf_period = "1y" if period == "daily" else ("3y" if period == "weekly" else "5y")
        if days > 365 and period == "daily":
            yf_period = "2y"

        def _load() -> pd.DataFrame:
            return yf.Ticker(candidate.yf_symbol).history(period=yf_period, interval=interval, auto_adjust=True)

        df = await asyncio.to_thread(_load)
        if df is None or df.empty:
            raise LookupError(f"暂无 {candidate.name}({candidate.ts_code}) 的历史行情数据。")

        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df = df.sort_index()
        for col in ("Open", "High", "Low", "Close", "Volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        return df[["Open", "High", "Low", "Close", "Volume"]]

    async def _fetch_cn_kline(
        self,
        candidate: StockCandidate,
        period: Literal["daily", "weekly", "monthly"],
        days: int,
    ) -> pd.DataFrame:
        end_dt = datetime.now()
        lookback_days = max(days, 180)
        if period == "weekly":
            lookback_days = max(days, 730)
        elif period == "monthly":
            lookback_days = max(days, 1825)
        start_dt = end_dt - timedelta(days=lookback_days)
        start_str = start_dt.strftime("%Y%m%d")
        end_str = end_dt.strftime("%Y%m%d")

        df = None
        try:
            df = await asyncio.to_thread(
                ak.stock_zh_a_hist,
                symbol=candidate.code,
                period=period,
                start_date=start_str,
                end_date=end_str,
                adjust="qfq",
            )
        except Exception as exc:
            logger.warning("Primary EastMoney kline failed for %s: %s", candidate.code, exc)

        # Fallback 1: Tencent daily history
        if df is None or df.empty:
            try:
                _, _, tx_symbol = normalize_stock_code(candidate.code)
                tx_df = await asyncio.to_thread(
                    ak.stock_zh_a_hist_tx,
                    symbol=tx_symbol,
                    start_date=start_str,
                    end_date=end_str,
                    adjust="qfq",
                )
                if tx_df is not None and not tx_df.empty:
                    tx_df = tx_df.rename(
                        columns={
                            "date": "Date",
                            "open": "Open",
                            "high": "High",
                            "low": "Low",
                            "close": "Close",
                            "amount": "Volume",
                        }
                    )
                    tx_df["Date"] = pd.to_datetime(tx_df["Date"])
                    tx_df = tx_df.sort_values("Date").set_index("Date")
                    for col in ("Open", "High", "Low", "Close", "Volume"):
                        tx_df[col] = pd.to_numeric(tx_df[col], errors="coerce")
                    tx_df = tx_df.dropna(subset=["Open", "High", "Low", "Close"])
                    if period == "weekly":
                        tx_df = tx_df.resample("W-FRI").agg(
                            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
                        ).dropna()
                    elif period == "monthly":
                        tx_df = tx_df.resample("ME").agg(
                            {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
                        ).dropna()
                    return tx_df
            except Exception as exc:
                logger.warning("Tencent kline fallback failed for %s: %s", candidate.code, exc)

        # Fallback 2: yfinance for CN stocks (great for overseas cloud deployments!)
        if df is None or df.empty:
            return await self._fetch_yf_kline(candidate, period, days)

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

    # ------------------------------------------------------------------
    # Stock quote (CN + HK + US)
    # ------------------------------------------------------------------

    async def get_quote(self, code_or_name: str) -> StockQuote:
        candidate, df = await self.get_kline(code_or_name, period="daily", days=30)
        cache_key = f"quote:{candidate.market_type}:{candidate.code}"

        async def _fetch() -> StockQuote:
            latest = df.iloc[-1]
            pre_close = float(df.iloc[-2]["Close"]) if len(df) >= 2 else float(latest["Open"])
            close = float(latest["Close"])

            change_pct = _safe_float(latest.get("ChangePct"))
            change_amt = _safe_float(latest.get("ChangeAmt"))
            if change_pct is None and pre_close:
                change_amt = close - pre_close
                change_pct = (change_amt / pre_close) * 100.0

            stock_name = candidate.name
            industry = ""
            total_mv: float | None = None
            pe_ttm: float | None = None
            pb: float | None = None
            amount = float(_safe_float(latest.get("Amount")) or 0.0)

            if candidate.market_type == "CN":
                try:
                    info_df = await asyncio.to_thread(ak.stock_individual_info_em, symbol=candidate.code)
                    if info_df is not None and not info_df.empty:
                        info_map = dict(zip(info_df["item"], info_df["value"], strict=False))
                        if stock_name == candidate.code and info_map.get("股票简称"):
                            stock_name = str(info_map["股票简称"]).strip()
                        industry = str(info_map.get("行业", "") or "")
                        mv_raw = _safe_float(info_map.get("总市值"))
                        if mv_raw is not None:
                            total_mv = round(mv_raw / 1e8, 2)
                except Exception as exc:
                    logger.debug("Optional CN info fetch failed for %s: %s", candidate.code, exc)

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
            else:
                try:
                    info = await asyncio.to_thread(lambda: yf.Ticker(candidate.yf_symbol).info)
                    if isinstance(info, dict):
                        if stock_name in (candidate.code, candidate.ts_code):
                            stock_name = str(info.get("shortName") or info.get("longName") or stock_name)
                        industry = str(info.get("industry") or info.get("sector") or "")
                        pe_ttm = _safe_float(info.get("trailingPE"))
                        pb = _safe_float(info.get("priceToBook"))
                        mv_raw = _safe_float(info.get("marketCap"))
                        if mv_raw is not None:
                            total_mv = round(mv_raw / 1e8, 2)
                except Exception as exc:
                    logger.debug("Optional yfinance info fetch failed for %s: %s", candidate.yf_symbol, exc)

                if amount == 0.0:
                    amount = float(latest["Volume"]) * close

            return StockQuote(
                code=candidate.code,
                ts_code=candidate.ts_code,
                name=stock_name,
                market=candidate.market,
                market_type=candidate.market_type,
                currency=_currency_for_market(candidate.market_type),
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
                amount=amount,
                turnover_rate=_safe_float(latest.get("Turnover")),
                pe_ttm=round(pe_ttm, 2) if pe_ttm is not None else None,
                pb=round(pb, 2) if pb is not None else None,
                total_mv=total_mv,
            )

        return await self.cache.get_or_set(cache_key, _fetch, ttl=120)

    # ------------------------------------------------------------------
    # Financial indicators (CN + HK + US)
    # ------------------------------------------------------------------

    async def get_finance(self, code_or_name: str) -> FinanceSummary:
        candidate = await self.resolve_stock(code_or_name)
        cache_key = f"finance:{candidate.market_type}:{candidate.code}"

        async def _fetch() -> FinanceSummary:
            if candidate.market_type in ("HK", "US"):
                info = await asyncio.to_thread(lambda: yf.Ticker(candidate.yf_symbol).info)
                if not isinstance(info, dict) or not info:
                    raise LookupError(f"暂未获取到 {candidate.name}({candidate.ts_code}) 的财务数据。")
                roe = _safe_float(info.get("returnOnEquity"))
                gross = _safe_float(info.get("grossMargins"))
                net = _safe_float(info.get("profitMargins"))
                rev_g = _safe_float(info.get("revenueGrowth"))
                earn_g = _safe_float(info.get("earningsGrowth"))
                dte = _safe_float(info.get("debtToEquity"))
                return FinanceSummary(
                    code=candidate.code,
                    name=str(info.get("shortName") or candidate.name),
                    market_type=candidate.market_type,
                    currency=str(info.get("currency") or _currency_for_market(candidate.market_type)),
                    report_date="TTM / 最新财报",
                    eps=_safe_float(info.get("trailingEps")),
                    roe=round(roe * 100, 2) if roe is not None else None,
                    bps=_safe_float(info.get("bookValue")),
                    gross_margin=round(gross * 100, 2) if gross is not None else None,
                    net_margin=round(net * 100, 2) if net is not None else None,
                    debt_to_assets=round(dte, 2) if dte is not None else None,
                    current_ratio=_safe_float(info.get("currentRatio")),
                    revenue_yoy=round(rev_g * 100, 2) if rev_g is not None else None,
                    profit_yoy=round(earn_g * 100, 2) if earn_g is not None else None,
                    pe_ttm=_safe_float(info.get("trailingPE")),
                    pb=_safe_float(info.get("priceToBook")),
                )

            # CN A-Share: AkShare primary
            try:
                df = await asyncio.to_thread(ak.stock_financial_analysis_indicator, symbol=candidate.code)
                if df is not None and not df.empty:
                    df = df.sort_values("日期", ascending=False)
                    latest = df.iloc[0]
                    return FinanceSummary(
                        code=candidate.code,
                        name=candidate.name,
                        market_type="CN",
                        currency="CNY",
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
                        market_type="CN",
                        currency="CNY",
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
    # Latest news (CN + HK + US)
    # ------------------------------------------------------------------

    async def get_news(self, code_or_name: str, limit: int = 8) -> tuple[StockCandidate, list[NewsItem]]:
        candidate = await self.resolve_stock(code_or_name)
        cache_key = f"news:{candidate.market_type}:{candidate.code}:{limit}"

        async def _fetch() -> list[NewsItem]:
            if candidate.market_type == "CN":
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

            # HK / US news via yfinance
            raw_news = await asyncio.to_thread(lambda: yf.Ticker(candidate.yf_symbol).news or [])
            items = []
            for entry in raw_news[:limit]:
                content = entry.get("content", entry) if isinstance(entry, dict) else {}
                title = str(content.get("title") or entry.get("title") or "").strip()
                if not title:
                    continue
                summary = str(content.get("summary") or "").strip()[:500]
                pub_date = str(content.get("pubDate") or "")[:19].replace("T", " ")
                provider = ""
                if isinstance(content.get("provider"), dict):
                    provider = str(content["provider"].get("displayName") or "")
                else:
                    provider = str(entry.get("publisher") or "")
                url = ""
                if isinstance(content.get("canonicalUrl"), dict):
                    url = str(content["canonicalUrl"].get("url") or "")
                else:
                    url = str(entry.get("link") or "")
                items.append(
                    NewsItem(
                        title=title,
                        content=summary,
                        publish_time=pub_date,
                        source=provider,
                        url=url,
                    )
                )
            return items

        items = await self.cache.get_or_set(cache_key, _fetch, ttl=300)
        return candidate, items
