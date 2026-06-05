from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class CookieInfo:
    cookie: str = ""
    heybox_id: str = ""
    time: int = 0


@dataclass(slots=True)
class XhhMessage:
    comment_id: int
    comment_text: str
    message_id: int
    root_comment_id: int
    link_id: int
    user_id: int
    user_name: str = ""
    link_title: str = ""
    link_user: str = ""
    link_user_id: int = 0
    mentioned_at: int = 0
    mentioned_user_id: int = 0
    mentioned_user_name: str = ""


@dataclass(slots=True)
class LinkContext:
    title: str = ""
    parts: list[dict] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
