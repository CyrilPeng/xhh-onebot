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
