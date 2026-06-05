from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiosqlite


@dataclass(slots=True)
class PendingEvent:
    onebot_message_id: int
    xhh_message_id: int
    dedupe_key: str
    link_id: int
    comment_id: int
    root_comment_id: int
    user_id: int
    raw_text: str


class Store:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.db: aiosqlite.Connection | None = None

    async def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(self.path)
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                onebot_message_id INTEGER PRIMARY KEY,
                xhh_message_id INTEGER UNIQUE NOT NULL,
                dedupe_key TEXT NOT NULL DEFAULT '',
                link_id INTEGER NOT NULL,
                comment_id INTEGER NOT NULL,
                root_comment_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                raw_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_events_pending
                ON events (status, link_id, created_at);
            """
        )
        await self._migrate()
        await self.db.commit()

    async def _migrate(self) -> None:
        db = self._conn()
        async with db.execute("PRAGMA table_info(events)") as cursor:
            columns = {str(row["name"]) async for row in cursor}
        if "dedupe_key" not in columns:
            await db.execute("ALTER TABLE events ADD COLUMN dedupe_key TEXT NOT NULL DEFAULT ''")
        await db.execute(
            """
            UPDATE events
            SET dedupe_key = link_id || ':' || comment_id || ':' || root_comment_id || ':' || user_id
            WHERE dedupe_key = ''
            """
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_events_dedupe_key ON events (dedupe_key)")

    async def close(self) -> None:
        if self.db is not None:
            await self.db.close()
            self.db = None

    def _conn(self) -> aiosqlite.Connection:
        if self.db is None:
            raise RuntimeError("store is not open")
        return self.db

    async def seen_xhh_message(self, xhh_message_id: int) -> bool:
        db = self._conn()
        async with db.execute(
            "SELECT 1 FROM events WHERE xhh_message_id = ? LIMIT 1",
            (xhh_message_id,),
        ) as cursor:
            return await cursor.fetchone() is not None

    @staticmethod
    def dedupe_key(link_id: int, comment_id: int, root_comment_id: int, user_id: int) -> str:
        return f"{link_id}:{comment_id}:{root_comment_id}:{user_id}"

    async def seen_event(self, xhh_message_id: int, dedupe_key: str) -> bool:
        db = self._conn()
        async with db.execute(
            "SELECT 1 FROM events WHERE xhh_message_id = ? OR dedupe_key = ? LIMIT 1",
            (xhh_message_id, dedupe_key),
        ) as cursor:
            return await cursor.fetchone() is not None

    async def add_pending(self, event: PendingEvent) -> bool:
        db = self._conn()
        if await self.seen_event(event.xhh_message_id, event.dedupe_key):
            return False
        cursor = await db.execute(
            """
            INSERT OR IGNORE INTO events
                (onebot_message_id, xhh_message_id, dedupe_key, link_id, comment_id, root_comment_id, user_id, raw_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.onebot_message_id,
                event.xhh_message_id,
                event.dedupe_key,
                event.link_id,
                event.comment_id,
                event.root_comment_id,
                event.user_id,
                event.raw_text,
            ),
        )
        await db.commit()
        return cursor.rowcount > 0

    async def get_pending_for_group(self, group_id: int) -> Optional[PendingEvent]:
        db = self._conn()
        async with db.execute(
            """
            SELECT * FROM events
            WHERE status = 'pending' AND link_id = ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            (group_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return PendingEvent(
            onebot_message_id=row["onebot_message_id"],
            xhh_message_id=row["xhh_message_id"],
            dedupe_key=row["dedupe_key"],
            link_id=row["link_id"],
            comment_id=row["comment_id"],
            root_comment_id=row["root_comment_id"],
            user_id=row["user_id"],
            raw_text=row["raw_text"],
        )

    async def expire_pending(self, timeout_seconds: int) -> int:
        db = self._conn()
        cursor = await db.execute(
            """
            UPDATE events
            SET status = 'expired', updated_at = strftime('%s','now')
            WHERE status = 'pending'
              AND created_at < strftime('%s','now') - ?
            """,
            (timeout_seconds,),
        )
        await db.commit()
        return cursor.rowcount

    async def get_pending_by_message_id(self, message_id: int) -> Optional[PendingEvent]:
        db = self._conn()
        async with db.execute(
            """
            SELECT * FROM events
            WHERE status = 'pending' AND onebot_message_id = ?
            LIMIT 1
            """,
            (message_id,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return PendingEvent(
            onebot_message_id=row["onebot_message_id"],
            xhh_message_id=row["xhh_message_id"],
            dedupe_key=row["dedupe_key"],
            link_id=row["link_id"],
            comment_id=row["comment_id"],
            root_comment_id=row["root_comment_id"],
            user_id=row["user_id"],
            raw_text=row["raw_text"],
        )

    async def stats(self) -> dict[str, int]:
        db = self._conn()
        result = {"total": 0, "pending": 0, "replied": 0, "failed": 0, "expired": 0}
        async with db.execute("SELECT status, COUNT(*) AS count FROM events GROUP BY status") as cursor:
            async for row in cursor:
                status = row["status"]
                count = int(row["count"])
                result[status] = count
                result["total"] += count
        return result

    async def mark_replied(self, onebot_message_id: int) -> None:
        db = self._conn()
        await db.execute(
            "UPDATE events SET status = 'replied', updated_at = strftime('%s','now') WHERE onebot_message_id = ?",
            (onebot_message_id,),
        )
        await db.commit()

    async def mark_failed(self, onebot_message_id: int) -> None:
        db = self._conn()
        await db.execute(
            "UPDATE events SET status = 'failed', updated_at = strftime('%s','now') WHERE onebot_message_id = ?",
            (onebot_message_id,),
        )
        await db.commit()
