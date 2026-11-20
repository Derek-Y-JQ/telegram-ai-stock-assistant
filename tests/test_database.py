"""Tests for async SQLite Database repository (watchlist, history, briefings, alerts)."""

from __future__ import annotations

from pathlib import Path

from stock_bot.storage.database import Database


async def test_watchlist_history_briefings_and_alerts(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    await db.init()

    # Watchlist
    assert await db.add_watchlist(1001, "600519", "贵州茅台", "CN") is True
    assert await db.add_watchlist(1001, "NVDA", "NVIDIA", "US") is True
    assert await db.add_watchlist(1001, "600519", "贵州茅台", "CN") is False
    assert await db.is_in_watchlist(1001, "600519") is True

    items = await db.get_watchlist(1001)
    assert len(items) == 2
    assert {i.market_type for i in items} == {"CN", "US"}

    assert await db.remove_watchlist(1001, "600519") is True
    assert await db.is_in_watchlist(1001, "600519") is False

    # Chat history
    await db.append_message(2001, "user", "看看茅台")
    await db.append_message(2001, "assistant", "贵州茅台当前走势...")
    msgs = await db.get_recent_messages(2001, limit=5)
    assert len(msgs) == 2
    await db.clear_history(2001)
    assert await db.get_recent_messages(2001) == []

    # Briefings
    sub = await db.set_brief_subscription(3001, 1001, morning_enabled=True, evening_enabled=False)
    assert sub.morning_enabled is True
    assert sub.evening_enabled is False
    assert len(await db.list_brief_subscribers("morning")) == 1
    assert len(await db.list_brief_subscribers("evening")) == 0

    # Price alerts
    alert = await db.add_price_alert(3001, 1001, "NVDA", "NVIDIA", "US", "above", 150.0)
    active = await db.get_active_alerts(1001)
    assert len(active) == 1
    assert active[0].id == alert.id

    await db.mark_alert_triggered(alert.id)
    assert await db.get_active_alerts(1001) == []
