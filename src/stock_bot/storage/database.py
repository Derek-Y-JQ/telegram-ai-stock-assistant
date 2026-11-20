"""Async SQLite storage for user watchlists and AI conversation history."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import aiosqlite

from stock_bot.models import WatchlistItem


class Database:
    """Async SQLite repository."""

    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    user_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, code)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_history_chat_id ON chat_history (chat_id, id)"
            )
            await db.commit()

    # --- Watchlist ---

    async def add_watchlist(self, user_id: int, code: str, name: str) -> bool:
        """Add stock to watchlist. Returns True if newly added, False if already existed."""
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT OR IGNORE INTO watchlist (user_id, code, name, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, code, name, now),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def remove_watchlist(self, user_id: int, code: str) -> bool:
        """Remove stock from watchlist. Returns True if removed."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM watchlist WHERE user_id = ? AND code = ?",
                (user_id, code),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def is_in_watchlist(self, user_id: int, code: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT 1 FROM watchlist WHERE user_id = ? AND code = ? LIMIT 1",
                (user_id, code),
            )
            row = await cursor.fetchone()
            return row is not None

    async def get_watchlist(self, user_id: int) -> list[WatchlistItem]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT user_id, code, name, created_at
                FROM watchlist
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [
                WatchlistItem(user_id=r[0], code=r[1], name=r[2], created_at=r[3])
                for r in rows
            ]

    # --- Chat History ---

    async def append_message(self, chat_id: int, role: str, content: str) -> None:
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO chat_history (chat_id, role, content, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, role, content, now),
            )
            await db.commit()

    async def get_recent_messages(self, chat_id: int, limit: int = 10) -> list[dict[str, str]]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT role, content
                FROM (
                    SELECT id, role, content
                    FROM chat_history
                    WHERE chat_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC
                """,
                (chat_id, limit),
            )
            rows = await cursor.fetchall()
            return [{"role": r[0], "content": r[1]} for r in rows]

    async def clear_history(self, chat_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM chat_history WHERE chat_id = ?", (chat_id,))
            await db.commit()
