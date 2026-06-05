import pytest

from xhh_onebot.app import App, limit_text
from xhh_onebot.config import Config, DatabaseConfig, OneBotConfig
from xhh_onebot.onebot.actions import contains_ignored_media, extract_plain_text
from xhh_onebot.onebot.events import group_message_event, heartbeat_event


@pytest.mark.asyncio
async def test_get_group_info_uses_readable_chinese_group_name(tmp_path):
    app = App(
        Config(
            onebot=OneBotConfig(self_id=12345),
            database=DatabaseConfig(path=str(tmp_path / "events.db")),
        )
    )

    response = await app.handle_action(
        {"action": "get_group_info", "params": {"group_id": 98765}, "echo": "echo-1"}
    )

    assert response["status"] == "ok"
    assert response["echo"] == "echo-1"
    assert response["data"]["group_name"] == "小黑盒帖子 98765"


def test_heartbeat_event_uses_configured_interval_ms():
    event = heartbeat_event(self_id=12345, interval_ms=15000)

    assert event["self_id"] == 12345
    assert event["meta_event_type"] == "heartbeat"
    assert event["interval"] == 15000


def test_group_message_event_mentions_self_by_default():
    event = group_message_event(
        self_id=12345,
        message_id=1,
        group_id=2,
        user_id=3,
        text="hello",
        xhh_context={},
    )

    assert event["message"][0] == {"type": "at", "data": {"qq": "12345"}}
    assert event["message"][1] == {"type": "text", "data": {"text": "\nhello"}}
    assert event["raw_message"].startswith("[CQ:at,qq=12345]")


def test_group_message_event_can_disable_self_mention():
    event = group_message_event(
        self_id=12345,
        message_id=1,
        group_id=2,
        user_id=3,
        text="hello",
        xhh_context={},
        mention_self=False,
    )

    assert event["message"] == [{"type": "text", "data": {"text": "hello"}}]
    assert event["raw_message"] == "hello"


def test_extract_plain_text_merges_text_segments_and_ignores_media_segments():
    message = [
        {"type": "text", "data": {"text": "第一段"}},
        {"type": "image", "data": {"file": "a.png"}},
        {"type": "record", "data": {"file": "a.amr"}},
        {"type": "text", "data": {"text": "第二段"}},
    ]

    assert extract_plain_text(message) == "第一段第二段"


def test_extract_plain_text_removes_media_cq_codes_from_string_message():
    message = "文字[CQ:image,file=a.png]更多[CQ:record,file=a.amr]结束"

    assert extract_plain_text(message) == "文字更多结束"
    assert contains_ignored_media(message)


def test_contains_ignored_media_detects_media_segments():
    assert contains_ignored_media([{"type": "text", "data": {"text": "x"}}, {"type": "image", "data": {}}])
    assert not contains_ignored_media([{"type": "text", "data": {"text": "x"}}])


def test_limit_text_truncates_long_reply():
    text, truncated = limit_text("abcdef", 4)

    assert text == "abc…"
    assert truncated is True


def test_limit_text_keeps_short_reply():
    text, truncated = limit_text("abc", 4)

    assert text == "abc"
    assert truncated is False

@pytest.mark.asyncio
async def test_get_stranger_info_returns_basic_user(tmp_path):
    app = App(
        Config(
            onebot=OneBotConfig(self_id=12345),
            database=DatabaseConfig(path=str(tmp_path / "events.db")),
        )
    )

    response = await app.handle_action(
        {"action": "get_stranger_info", "params": {"user_id": 12345}, "echo": {"seq": 22}}
    )

    assert response["status"] == "ok"
    assert response["retcode"] == 0
    assert response["echo"] == {"seq": 22}
    assert response["data"]["user_id"] == 12345
    assert response["data"]["nickname"] == "xhh-onebot"
