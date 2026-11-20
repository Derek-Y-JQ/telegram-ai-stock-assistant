"""FastAPI backend powering the interactive K-line & Watchlist Telegram Mini App."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

from stock_bot.services.market_data import MarketDataService
from stock_bot.storage.database import Database

DASHBOARD_HTML_PATH = Path(__file__).parent / "dashboard.html"


def create_webapp(market_data: MarketDataService, database: Database) -> FastAPI:
    app = FastAPI(title="Stock Bot Interactive Dashboard", version="2.5.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(DASHBOARD_HTML_PATH.read_text(encoding="utf-8"))

    @app.get("/api/market")
    async def api_market() -> dict[str, object]:
        indices = await market_data.get_market_overview()
        return {"indices": [i.model_dump() for i in indices]}

    @app.get("/api/quote")
    async def api_quote(symbol: str = Query(..., min_length=1)) -> dict[str, object]:
        try:
            quote = await market_data.get_quote(symbol)
            return quote.model_dump()
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/kline")
    async def api_kline(
        symbol: str = Query(..., min_length=1),
        period: Literal["daily", "weekly", "monthly"] = Query("daily"),
        bars: int = Query(160, ge=20, le=500),
    ) -> dict[str, object]:
        try:
            candidate, df = await market_data.get_kline(symbol, period=period)
            close = df["Close"].astype(float)
            df["MA5"] = close.rolling(5).mean()
            df["MA10"] = close.rolling(10).mean()
            df["MA20"] = close.rolling(20).mean()
            sliced = df.tail(bars)

            candles: list[dict[str, object]] = []
            volumes: list[dict[str, object]] = []
            ma5: list[dict[str, object]] = []
            ma10: list[dict[str, object]] = []
            ma20: list[dict[str, object]] = []

            for idx, row in sliced.iterrows():
                t = idx.strftime("%Y-%m-%d")
                o = round(float(row["Open"]), 3)
                h = round(float(row["High"]), 3)
                lo = round(float(row["Low"]), 3)
                c = round(float(row["Close"]), 3)
                v = float(row["Volume"])
                candles.append({"time": t, "open": o, "high": h, "low": lo, "close": c})
                volumes.append(
                    {
                        "time": t,
                        "value": v,
                        "color": "rgba(239, 83, 80, 0.45)" if c >= o else "rgba(38, 166, 154, 0.45)",
                    }
                )
                if not (row["MA5"] != row["MA5"]):
                    ma5.append({"time": t, "value": round(float(row["MA5"]), 3)})
                if not (row["MA10"] != row["MA10"]):
                    ma10.append({"time": t, "value": round(float(row["MA10"]), 3)})
                if not (row["MA20"] != row["MA20"]):
                    ma20.append({"time": t, "value": round(float(row["MA20"]), 3)})

            return {
                "stock": candidate.model_dump(),
                "period": period,
                "candles": candles,
                "volumes": volumes,
                "ma5": ma5,
                "ma10": ma10,
                "ma20": ma20,
            }
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/api/watchlist")
    async def api_watchlist(user_id: int = Query(...)) -> dict[str, object]:
        items = await database.get_watchlist(user_id)
        return {"items": [i.model_dump() for i in items]}

    return app
