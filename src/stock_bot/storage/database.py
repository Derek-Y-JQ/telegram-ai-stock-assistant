"""Async SQLite storage for watchlists, chat history, language preferences, briefings, and alerts."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import aiosqlite

from stock_bot.i18n import DEFAULT_LANG
from stock_bot.models import BriefSubscription, Lang, MarketType, PriceAlert, WatchlistItem


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
                    market_type TEXT NOT NULL DEFAULT 'CN',
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, code)
                )
                """
            )
            cursor = await db.execute("PRAGMA table_info(watchlist)")
            columns = {row[1] for row in await cursor.fetchall()}
            if "market_type" not in columns:
                await db.execute(
                    "ALTER TABLE watchlist ADD COLUMN market_type TEXT NOT NULL DEFAULT 'CN'"
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

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id INTEGER PRIMARY KEY,
                    lang TEXT NOT NULL DEFAULT 'en',
                    updated_at TEXT NOT NULL
                )
                """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS brief_subscriptions (
                    chat_id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    morning_enabled INTEGER NOT NULL DEFAULT 0,
                    evening_enabled INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
                """
            )

            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS price_alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    market_type TEXT NOT NULL DEFAULT 'CN',
                    direction TEXT NOT NULL,
                    target_price REAL NOT NULL,
                    triggered INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerts_active ON price_alerts (triggered, user_id)"
            )
            await db.commit()

    # ------------------------------------------------------------------
    # User Language Preference (default: English)
    # ------------------------------------------------------------------

    async def get_user_lang(self, user_id: int) -> Lang:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT lang FROM user_preferences WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row and row[0] in ("en", "zh"):
                return row[0]
            return DEFAULT_LANG

    async def set_user_lang(self, user_id: int, lang: Lang) -> Lang:
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO user_preferences (user_id, lang, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    lang = excluded.lang,
                    updated_at = excluded.updated_at
                """,
                (user_id, lang, now),
            )
            await db.commit()
        return lang

    # ------------------------------------------------------------------
    # Watchlist
    # ------------------------------------------------------------------

    async def add_watchlist(
        self,
        user_id: int,
        code: str,
        name: str,
        market_type: MarketType = "CN",
    ) -> bool:
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT OR IGNORE INTO watchlist (user_id, code, name, market_type, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, code, name, market_type, now),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def remove_watchlist(self, user_id: int, code: str) -> bool:
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
            return (await cursor.fetchone()) is not None

    async def get_watchlist(self, user_id: int) -> list[WatchlistItem]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT user_id, code, name, market_type, created_at
                FROM watchlist
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [
                WatchlistItem(
                    user_id=r[0],
                    code=r[1],
                    name=r[2],
                    market_type=r[3],
                    created_at=r[4],
                )
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Chat History
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Scheduled Briefing Subscriptions
    # ------------------------------------------------------------------

    async def get_brief_subscription(self, chat_id: int, user_id: int) -> BriefSubscription:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT chat_id, user_id, morning_enabled, evening_enabled
                FROM brief_subscriptions
                WHERE chat_id = ?
                """,
                (chat_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                return BriefSubscription(chat_id=chat_id, user_id=user_id)
            return BriefSubscription(
                chat_id=row[0],
                user_id=row[1],
                morning_enabled=bool(row[2]),
                evening_enabled=bool(row[3]),
            )

    async def set_brief_subscription(
        self,
        chat_id: int,
        user_id: int,
        *,
        morning_enabled: bool | None = None,
        evening_enabled: bool | None = None,
    ) -> BriefSubscription:
        current = await self.get_brief_subscription(chat_id, user_id)
        new_morning = current.morning_enabled if morning_enabled is None else morning_enabled
        new_evening = current.evening_enabled if evening_enabled is None else evening_enabled
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO brief_subscriptions (chat_id, user_id, morning_enabled, evening_enabled, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    user_id = excluded.user_id,
                    morning_enabled = excluded.morning_enabled,
                    evening_enabled = excluded.evening_enabled,
                    updated_at = excluded.updated_at
                """,
                (chat_id, user_id, int(new_morning), int(new_evening), now),
            )
            await db.commit()
        return BriefSubscription(
            chat_id=chat_id,
            user_id=user_id,
            morning_enabled=new_morning,
            evening_enabled=new_evening,
        )

    async def list_brief_subscribers(self, kind: Literal["morning", "evening"]) -> list[BriefSubscription]:
        col = "morning_enabled" if kind == "morning" else "evening_enabled"
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"SELECT chat_id, user_id, morning_enabled, evening_enabled FROM brief_subscriptions WHERE {col} = 1"
            )
            rows = await cursor.fetchall()
            return [
                BriefSubscription(
                    chat_id=r[0],
                    user_id=r[1],
                    morning_enabled=bool(r[2]),
                    evening_enabled=bool(r[3]),
                )
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Price Alerts
    # ------------------------------------------------------------------

    async def add_price_alert(
        self,
        chat_id: int,
        user_id: int,
        code: str,
        name: str,
        market_type: MarketType,
        direction: Literal["above", "below"],
        target_price: float,
    ) -> PriceAlert:
        now = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO price_alerts (chat_id, user_id, code, name, market_type, direction, target_price, triggered, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (chat_id, user_id, code, name, market_type, direction, target_price, now),
            )
            alert_id = cursor.lastrowid or 0
            await db.commit()
        return PriceAlert(
            id=alert_id,
            chat_id=chat_id,
            user_id=user_id,
            code=code,
            name=name,
            market_type=market_type,
            direction=direction,
            target_price=target_price,
            triggered=False,
            created_at=now,
        )

    async def get_active_alerts(self, user_id: int | None = None) -> list[PriceAlert]:
        async with aiosqlite.connect(self.db_path) as db:
            if user_id is None:
                cursor = await db.execute(
                    """
                    SELECT id, chat_id, user_id, code, name, market_type, direction, target_price, triggered, created_at
                    FROM price_alerts
                    WHERE triggered = 0
                    ORDER BY id DESC
                    """
                )
            else:
                cursor = await db.execute(
                    """
                    SELECT id, chat_id, user_id, code, name, market_type, direction, target_price, triggered, created_at
                    FROM price_alerts
                    WHERE triggered = 0 AND user_id = ?
                    ORDER BY id DESC
                    """,
                    (user_id,),
                )
            rows = await cursor.fetchall()
            return [
                PriceAlert(
                    id=r[0],
                    chat_id=r[1],
                    user_id=r[2],
                    code=r[3],
                    name=r[4],
                    market_type=r[5],
                    direction=r[6],
                    target_price=r[7],
                    triggered=bool(r[8]),
                    created_at=r[9],
                )
                for r in rows
            ]

    async def mark_alert_triggered(self, alert_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE price_alerts SET triggered = 1 WHERE id = ?", (alert_id,))
            await db.commit()

    async def delete_price_alert(self, user_id: int, alert_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM price_alerts WHERE id = ? AND user_id = ?",
                (alert_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0
