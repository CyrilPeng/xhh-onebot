from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from xhh_onebot.config import Config
from xhh_onebot.onebot.actions import contains_ignored_media, extract_plain_text, extract_reply_id, failed, success
from xhh_onebot.onebot.events import group_message_event
from xhh_onebot.onebot.ws_reverse import ReverseWebSocket
from xhh_onebot.store import PendingEvent, Store
from xhh_onebot.xhh.client import XhhClient
from xhh_onebot.xhh.models import LinkContext
from xhh_onebot.xhh.poller import build_context_message

logger = logging.getLogger(__name__)


class ReplyBuffer:
    def __init__(self, group_id: int, reply_id: int | None) -> None:
        self.group_id = group_id
        self.reply_id = reply_id
        self.parts: list[str] = []
        self.task: asyncio.Task[None] | None = None


def format_timestamp(timestamp: int) -> str:
    if timestamp <= 0:
        return "未知时间"
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


def summarize_text(text: str, limit: int = 80) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1] + "…"


def limit_text(text: str, max_chars: int) -> tuple[str, bool]:
    if max_chars <= 0 or len(text) <= max_chars:
        return text, False
    return text[: max_chars - 1].rstrip() + "…", True


class App:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.store = Store(config.database.path)
        self.xhh = XhhClient(config.xhh)
        self.onebot = ReverseWebSocket(config.onebot, self.handle_action)
        self.reply_lock = asyncio.Lock()
        self.reply_buffers: dict[tuple[int, int | None], ReplyBuffer] = {}

    async def start(self) -> None:
        await self.store.open()
        await self.xhh.open()
        if not await self.xhh.check_login():
            logger.warning("小黑盒登录检查失败，cookie 可能已在启动后失效")
        logger.info("小黑盒登录检查通过，开始轮询艾特消息并连接 OneBot 反向 WebSocket")
        await asyncio.gather(self.onebot.run_forever(), self.poll_loop())

    async def stop(self) -> None:
        await self.onebot.stop()
        await self.xhh.close()
        await self.store.close()

    async def poll_loop(self) -> None:
        while True:
            try:
                await self.poll_once()
            except Exception:
                logger.exception("轮询小黑盒艾特消息失败")
                await self.recover_login_if_needed()
            await asyncio.sleep(self.config.xhh.check_time)

    async def recover_login_if_needed(self) -> None:
        if await self.xhh.check_login():
            return
        logger.warning("检测到小黑盒登录态失效，暂停轮询并开始扫码重新登录")
        try:
            await self.xhh.login_qrcode()
        except Exception:
            logger.exception("小黑盒扫码重新登录失败，将在下次轮询后重试")
            return
        logger.info("小黑盒扫码重新登录成功，恢复轮询")

    async def poll_once(self) -> None:
        expired = await self.store.expire_pending(self.config.poller.reply_timeout)
        if expired:
            logger.warning("已将 %s 条超时未回复的艾特事件标记为过期", expired)
        owners = self.config.xhh.owners
        allow_all_users = self.config.xhh.allow_all_users
        if not allow_all_users and not owners:
            logger.warning("xhh.owner 为空，不会投递任何艾特消息")
            return
        messages = await self.xhh.fetch_mentions(limit=20)
        delivered = 0
        for message in messages:
            if delivered >= self.config.poller.max_batch:
                break
            if not allow_all_users and message.user_id not in owners:
                logger.info(
                    "跳过未授权用户的艾特：时间=%s，用户=%s(%s)，帖子=%s(%s)，消息=%s",
                    format_timestamp(message.mentioned_at),
                    message.user_name or "未知用户",
                    message.user_id,
                    message.link_title or "未知帖子",
                    message.link_id,
                    message.message_id,
                )
                continue
            if message.message_id == 0 or message.comment_id == 0 or message.link_id == 0:
                logger.warning("跳过字段不完整的艾特消息：%s", message)
                continue
            dedupe_key = self.store.dedupe_key(
                message.link_id,
                message.comment_id,
                message.root_comment_id,
                message.user_id,
            )
            if await self.store.seen_event(message.message_id, dedupe_key):
                continue
            logger.info(
                "收到新的小黑盒艾特：时间=%s，艾特人=%s(%s)，帖子=%s(%s)，帖子作者=%s(%s)，评论=%s，消息=%s",
                format_timestamp(message.mentioned_at),
                message.user_name or "未知用户",
                message.user_id,
                message.link_title or "未知帖子",
                message.link_id,
                message.link_user or "未知作者",
                message.link_user_id,
                summarize_text(message.comment_text),
                message.message_id,
            )
            try:
                context = await self.xhh.get_link_context(message.link_id)
            except Exception as exc:
                logger.warning(
                    "获取小黑盒帖子详情失败，将只投递评论内容：帖子=%s，错误=%s",
                    message.link_id,
                    exc,
                )
                context = LinkContext(title=f"小黑盒帖子 {message.link_id}")
            text = build_context_message(
                message,
                context,
                self.config.poller.context_max_chars,
                self.config.poller.post_context_max_chars,
            )
            event = PendingEvent(
                onebot_message_id=message.message_id,
                xhh_message_id=message.message_id,
                dedupe_key=dedupe_key,
                link_id=message.link_id,
                comment_id=message.comment_id,
                root_comment_id=message.root_comment_id,
                user_id=message.user_id,
                raw_text=text,
            )
            if not await self.store.add_pending(event):
                logger.info(
                    "跳过重复小黑盒艾特：消息=%s，去重键=%s，帖子=%s，评论=%s，用户=%s",
                    message.message_id,
                    dedupe_key,
                    message.link_id,
                    message.comment_id,
                    message.user_id,
                )
                continue
            await self.onebot.send_event(
                group_message_event(
                    self_id=self.config.onebot.self_id,
                    message_id=event.onebot_message_id,
                    group_id=event.link_id,
                    user_id=event.user_id,
                    text=text,
                    mention_self=self.config.onebot.mention_self,
                    xhh_context={
                        "link_id": event.link_id,
                        "comment_id": event.comment_id,
                        "root_comment_id": event.root_comment_id,
                        "xhh_message_id": event.xhh_message_id,
                    },
                )
            )
            logger.info(
                "已投递小黑盒艾特到 OneBot：消息=%s，评论=%s，帖子=%s，艾特人=%s(%s)",
                message.message_id,
                message.comment_id,
                message.link_id,
                message.user_name or "未知用户",
                message.user_id,
            )
            delivered += 1

    async def handle_action(self, action: dict[str, Any]) -> dict[str, Any] | None:
        action_name = action.get("action")
        params = action.get("params") or {}
        echo = action.get("echo")
        logger.info("received OneBot action: %s", action_name)

        if action_name in {"send_group_msg", "send_msg"}:
            group_id = int(params.get("group_id") or 0)
            if action_name == "send_msg" and params.get("message_type") not in {None, "group"}:
                return failed(echo, "only group message is supported")
            message = params.get("message")
            if contains_ignored_media(message):
                logger.info("AstrBot 回复包含图片、语音或文件等媒体段，已忽略，仅发送文本到小黑盒")
            text = extract_plain_text(message)
            if not group_id or not text.strip():
                return failed(echo, "missing group_id or message", 1400)
            text, truncated = limit_text(text.strip(), self.config.poller.reply_max_chars)
            if truncated:
                logger.warning(
                    "AstrBot 回复过长，已截断后发送到小黑盒：原始长度=%s，限制=%s，摘要=%s",
                    len(extract_plain_text(message).strip()),
                    self.config.poller.reply_max_chars,
                    summarize_text(text),
                )
            reply_id = extract_reply_id(message)
            self.buffer_reply(group_id, text, reply_id=reply_id)
            return success(echo, {"message_id": int(asyncio.get_running_loop().time() * 1000)})

        if action_name == "get_login_info":
            return success(
                echo,
                {
                    "user_id": self.config.onebot.self_id,
                    "nickname": "xhh-onebot",
                },
            )

        if action_name == "get_status":
            stats = await self.store.stats()
            return success(echo, {"online": True, "good": True, "xhh": {"events": stats}})

        if action_name == "get_version_info":
            return success(
                echo,
                {
                    "app_name": "xhh-onebot",
                    "app_version": "0.1.0",
                    "protocol_version": "v11",
                },
            )

        if action_name == "get_group_info":
            group_id = int(params.get("group_id") or 0)
            return success(
                echo,
                {
                    "group_id": group_id,
                    "group_name": f"小黑盒帖子 {group_id}",
                    "member_count": 0,
                    "max_member_count": 0,
                },
            )

        if action_name == "get_group_member_info":
            group_id = int(params.get("group_id") or 0)
            user_id = int(params.get("user_id") or 0)
            return success(
                echo,
                {
                    "group_id": group_id,
                    "user_id": user_id,
                    "nickname": f"xhh-{user_id}",
                    "card": "",
                    "sex": "unknown",
                    "age": 0,
                    "area": "",
                    "join_time": 0,
                    "last_sent_time": 0,
                    "level": "",
                    "role": "member",
                    "unfriendly": False,
                    "title": "",
                    "title_expire_time": 0,
                    "card_changeable": False,
                },
            )

        if action_name in {"get_stranger_info", "get_user_info"}:
            user_id = int(params.get("user_id") or params.get("self_id") or 0)
            return success(
                echo,
                {
                    "user_id": user_id,
                    "nickname": "xhh-onebot" if user_id == self.config.onebot.self_id else f"xhh-{user_id}",
                    "sex": "unknown",
                    "age": 0,
                    "qid": "",
                    "level": 0,
                    "login_days": 0,
                },
            )

        if action_name in {"can_send_image", "can_send_record"}:
            return success(echo, {"yes": action_name == "can_send_image"})

        return failed(echo)

    def buffer_reply(self, group_id: int, text: str, reply_id: int | None = None) -> None:
        key = self.reply_buffer_key(group_id, reply_id)
        buffer = self.reply_buffers.get(key)
        if buffer is None:
            buffer = ReplyBuffer(group_id, reply_id)
            self.reply_buffers[key] = buffer
        buffer.parts.append(text)
        if buffer.task is not None:
            buffer.task.cancel()
        buffer.task = asyncio.create_task(self.flush_reply_later(key))

    def reply_buffer_key(self, group_id: int, reply_id: int | None) -> tuple[int, int | None]:
        if reply_id is not None:
            return (group_id, reply_id)
        for key in self.reply_buffers:
            if key[0] == group_id:
                return key
        return (group_id, None)

    async def flush_reply_later(self, key: tuple[int, int | None]) -> None:
        try:
            await asyncio.sleep(max(0, self.config.poller.reply_merge_wait))
            buffer = self.reply_buffers.pop(key, None)
            if buffer is None:
                return
            text = "\n".join(part for part in buffer.parts if part.strip()).strip()
            if not text:
                return
            text, truncated = limit_text(text, self.config.poller.reply_max_chars)
            if truncated:
                logger.warning(
                    "AstrBot 分段回复合并后过长，已截断后发送到小黑盒：限制=%s，摘要=%s",
                    self.config.poller.reply_max_chars,
                    summarize_text(text),
                )
            ok = await self.reply_group(buffer.group_id, text, reply_id=buffer.reply_id)
            if not ok:
                logger.warning("AstrBot 分段回复合并发送失败：帖子=%s", buffer.group_id)
        except asyncio.CancelledError:
            return

    async def reply_group(self, group_id: int, text: str, reply_id: int | None = None) -> bool:
        async with self.reply_lock:
            pending = None
            if reply_id is not None:
                pending = await self.store.get_pending_by_message_id(reply_id)
            if pending is None:
                pending = await self.store.get_pending_for_group(group_id)
            if pending is None:
                logger.warning("没有找到待回复的小黑盒艾特事件：帖子=%s", group_id)
                return False
            logger.info(
                "准备回复小黑盒评论：帖子=%s，评论=%s，根评论=%s，回复摘要=%s",
                pending.link_id,
                pending.comment_id,
                pending.root_comment_id,
                summarize_text(text),
            )
            ok = await self.xhh.reply_comment(
                text=text,
                link_id=pending.link_id,
                reply_id=pending.comment_id,
                root_id=pending.root_comment_id,
            )
            if ok:
                await self.store.mark_replied(pending.onebot_message_id)
                logger.info(
                    "小黑盒评论回复成功：帖子=%s，评论=%s，OneBot消息=%s",
                    pending.link_id,
                    pending.comment_id,
                    pending.onebot_message_id,
                )
            else:
                await self.store.mark_failed(pending.onebot_message_id)
                logger.warning(
                    "小黑盒评论回复失败：帖子=%s，评论=%s，OneBot消息=%s",
                    pending.link_id,
                    pending.comment_id,
                    pending.onebot_message_id,
                )
            await asyncio.sleep(self.config.xhh.reply_time)
            return ok
