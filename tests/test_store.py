import sqlite3
import pytest

from xhh_onebot.store import PendingEvent, Store


def make_event(message_id: int, dedupe_key: str) -> PendingEvent:
    return PendingEvent(
        onebot_message_id=message_id,
        xhh_message_id=message_id,
        dedupe_key=dedupe_key,
        link_id=1,
        comment_id=2,
        root_comment_id=3,
        user_id=4,
        raw_text="text",
    )


@pytest.mark.asyncio
async def test_store_dedupes_by_composite_key(tmp_path):
    store = Store(str(tmp_path / "events.db"))
    await store.open()
    try:
        assert await store.add_pending(make_event(100, "1:2:3:4")) is True
        assert await store.add_pending(make_event(101, "1:2:3:4")) is False
        assert await store.seen_event(101, "1:2:3:4") is True
        assert await store.seen_event(102, "1:2:3:5") is False
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_store_migrates_existing_events_with_dedupe_key(tmp_path):
    db_path = tmp_path / "events.db"
    db = sqlite3.connect(db_path)
    try:
        db.executescript(
            """
            CREATE TABLE events (
                onebot_message_id INTEGER PRIMARY KEY,
                xhh_message_id INTEGER UNIQUE NOT NULL,
                link_id INTEGER NOT NULL,
                comment_id INTEGER NOT NULL,
                root_comment_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                raw_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            );
            INSERT INTO events
                (onebot_message_id, xhh_message_id, link_id, comment_id, root_comment_id, user_id, raw_text)
            VALUES (200, 200, 10, 20, 30, 40, 'old');
            """
        )
    finally:
        db.close()

    store = Store(str(db_path))
    await store.open()
    try:
        assert await store.seen_event(999, "10:20:30:40") is True
    finally:
        await store.close()
