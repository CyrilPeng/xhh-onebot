from __future__ import annotations

import re
from typing import Any


IGNORED_CQ_RE = re.compile(r"\[CQ:(?:image|record|voice|video|file)(?:,[^\]]*)?\]")
MEDIA_SEGMENT_TYPES = {"image", "record", "voice", "video", "file"}


def extract_reply_id(message: Any) -> int | None:
    if not isinstance(message, list):
        return None
    for segment in message:
        if not isinstance(segment, dict):
            continue
        if segment.get("type") != "reply":
            continue
        raw_id = segment.get("data", {}).get("id")
        if raw_id is None:
            continue
        try:
            return int(raw_id)
        except (TypeError, ValueError):
            return None
    return None


def extract_plain_text(message: Any) -> str:
    if isinstance(message, str):
        return IGNORED_CQ_RE.sub("", message)
    if isinstance(message, list):
        parts: list[str] = []
        for segment in message:
            if not isinstance(segment, dict):
                continue
            if segment.get("type") == "text":
                parts.append(str(segment.get("data", {}).get("text", "")))
        return "".join(parts)
    return str(message or "")


def contains_ignored_media(message: Any) -> bool:
    if isinstance(message, str):
        return IGNORED_CQ_RE.search(message) is not None
    if isinstance(message, list):
        for segment in message:
            if isinstance(segment, dict) and segment.get("type") in MEDIA_SEGMENT_TYPES:
                return True
    return False


def success(echo: Any = None, data: Any = None) -> dict[str, Any]:
    response = {"status": "ok", "retcode": 0, "data": data}
    if echo is not None:
        response["echo"] = echo
    return response


def failed(echo: Any = None, message: str = "unsupported action", retcode: int = 1404) -> dict[str, Any]:
    response = {"status": "failed", "retcode": retcode, "message": message, "wording": message}
    if echo is not None:
        response["echo"] = echo
    return response
