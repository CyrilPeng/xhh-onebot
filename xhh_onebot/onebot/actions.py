from __future__ import annotations

from typing import Any


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
        return message
    if isinstance(message, list):
        parts: list[str] = []
        for segment in message:
            if not isinstance(segment, dict):
                continue
            if segment.get("type") == "text":
                parts.append(str(segment.get("data", {}).get("text", "")))
        return "".join(parts)
    return str(message or "")


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
