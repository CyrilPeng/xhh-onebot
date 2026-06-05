from __future__ import annotations

import re
from html import unescape

from xhh_onebot.xhh.models import LinkContext, XhhMessage


TAG_RE = re.compile(r"<[^>]+>")
IMG_RE = re.compile(r"<img\b[^>]*(?:data-original|src)=[\"']([^\"']+)[\"'][^>]*>", re.IGNORECASE)
BR_RE = re.compile(r"</p\s*>|<br\s*/?>|</h[1-6]\s*>", re.IGNORECASE)


def html_to_text(value: str) -> str:
    value = IMG_RE.sub(lambda match: f"\n[Image] {match.group(1)}\n", value)
    value = BR_RE.sub("\n", value)
    value = TAG_RE.sub("", value)
    value = unescape(value)
    lines = [line.strip() for line in value.splitlines()]
    return "\n".join(line for line in lines if line)


def truncate_text(text: str, max_chars: int) -> str:
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 20)].rstrip() + "\n...[truncated]"


def strip_self_mention(text: str, self_name: str = "") -> str:
    text = text.strip()
    if not self_name:
        return text
    pattern = re.compile(rf"^(?:@{re.escape(self_name)}\s*)+")
    return pattern.sub("", text).strip()


def build_context_message(
    message: XhhMessage,
    context: LinkContext,
    max_chars: int,
    post_context_max_chars: int | None = None,
) -> str:
    user_comment = html_to_text(message.comment_text).strip() or message.comment_text
    user_comment = strip_self_mention(user_comment, message.mentioned_user_name) or user_comment
    lines: list[str] = [
        "[User Comment - Reply To This]",
        user_comment,
        "",
        "[Reference Post Context - Use Only As Background]",
    ]
    if context.title:
        lines.append(f"Title: {context.title}")
    if context.topics:
        lines.append("Topics: " + ", ".join(context.topics))
    if context.tags:
        lines.append("Tags: " + ", ".join(context.tags))

    body_parts: list[str] = []
    for part in context.parts:
        part_type = str(part.get("type") or "")
        if part_type in {"text", "html"}:
            body_parts.append(html_to_text(str(part.get("text") or "")))
        else:
            url = part.get("url")
            if url:
                body_parts.append(f"[Image] {url}")

    body = "\n".join(item for item in body_parts if item).strip()
    if body:
        if post_context_max_chars is not None:
            body = truncate_text(body, post_context_max_chars)
        lines.append("Body Summary: " + body)

    lines.append("\n[Instruction]")
    lines.append("Reply to the user comment above. The post context is background only; do not answer the post itself unless the user asks about it.")
    lines.append("\n[User Comment - Repeat For Attention]")
    lines.append(user_comment)
    text = "\n".join(lines)
    return truncate_text(text, max_chars)
