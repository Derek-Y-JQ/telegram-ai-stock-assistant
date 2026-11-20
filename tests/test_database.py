"""Tests for async SQLite Database repository."""

from __future__ import annotations

from pathlib import Path

from stock_bot.storage.database import Database


async def test_watchlist_and_chat_history(tmp_path: Path) -> None:
    db = Database(tmp_path / "test.db")
    await db.init()

    # Watchlist
    assert await db.add_watchlist(1001, "600519", "贵州茅台") is True
    assert await db.add_watchlist(1001, "600519", "贵州茅台") is False
    assert await db.is_in_watchlist(1001, "600519") is True

    items = await db.get_watchlist(1001)
    assert len(items) == 1
    assert items[0].code == "600519"

    assert await db.remove_watchlist(1001, "600519") is True
    assert await db.is_in_watchlist(1001, "600519") is False

    # Chat history
    await db.append_message(2001, "user", "看看茅台")
    await db.append_message(2001, "assistant", "贵州茅台当前走势...")
    msgs = await db.get_recent_messages(2001, limit=5)
    assert msgs == [
        {"role": "user", "content": "看看茅台"},
        {"role": "assistant", "content": "贵州茅台当前走势..."},
    ]

    await db.clear_history(2001)
    assert await db.get_recent_messages(2001) == []
