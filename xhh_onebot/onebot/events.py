from __future__ import annotations

import time
from typing import Any


def text_segment(text: str) -> dict[str, Any]:
    return {"type": "text", "data": {"text": text}}


def at_segment(user_id: int) -> dict[str, Any]:
    return {"type": "at", "data": {"qq": str(user_id)}}


def group_message_event(
    *,
    self_id: int,
    message_id: int,
    group_id: int,
    user_id: int,
    text: str,
    xhh_context: dict[str, Any],
    mention_self: bool = True,
) -> dict[str, Any]:
    message = [text_segment(text)]
    raw_message = text
    if mention_self:
        message = [at_segment(self_id), text_segment("\n" + text)]
        raw_message = f"[CQ:at,qq={self_id}]\n{text}"
    return {
        "time": int(time.time()),
        "self_id": self_id,
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "message_id": message_id,
        "group_id": group_id,
        "user_id": user_id,
        "message": message,
        "raw_message": raw_message,
        "font": 0,
        "sender": {
            "user_id": user_id,
            "nickname": f"xhh-{user_id}",
            "card": "",
            "sex": "unknown",
            "age": 0,
            "area": "",
            "level": "",
            "role": "member",
            "title": "",
        },
        "xhh_context": xhh_context,
    }


def lifecycle_event(self_id: int) -> dict[str, Any]:
    return {
        "time": int(time.time()),
        "self_id": self_id,
        "post_type": "meta_event",
        "meta_event_type": "lifecycle",
        "sub_type": "connect",
    }


def heartbeat_event(self_id: int, interval_ms: int) -> dict[str, Any]:
    return {
        "time": int(time.time()),
        "self_id": self_id,
        "post_type": "meta_event",
        "meta_event_type": "heartbeat",
        "status": {"online": True, "good": True},
        "interval": interval_ms,
    }
