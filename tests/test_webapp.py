"""Tests for FastAPI interactive Mini App endpoints."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from httpx import ASGITransport, AsyncClient

from stock_bot.storage.database import Database
from stock_bot.webapp.server import create_webapp


async def test_webapp_health_index_and_watchlist(tmp_path: Path) -> None:
    db = Database(tmp_path / "web.db")
    await db.init()
    await db.add_watchlist(777, "NVDA", "NVIDIA (英伟达)", "US")

    app = create_webapp(market_data=SimpleNamespace(), database=db)  # type: ignore[arg-type]
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r_health = await client.get("/health")
        assert r_health.status_code == 200
        assert r_health.json() == {"status": "ok"}

        r_home = await client.get("/")
        assert r_home.status_code == 200
        assert "LightweightCharts" in r_home.text

        r_watch = await client.get("/api/watchlist", params={"user_id": 777})
        assert r_watch.status_code == 200
        items = r_watch.json()["items"]
        assert len(items) == 1
        assert items[0]["code"] == "NVDA"
        assert items[0]["market_type"] == "US"
