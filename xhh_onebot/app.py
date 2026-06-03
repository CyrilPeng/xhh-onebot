from __future__ import annotations

import asyncio
import logging
from typing import Any

from xhh_onebot.config import Config
from xhh_onebot.onebot.actions import extract_plain_text, extract_reply_id, failed, success
from xhh_onebot.onebot.events import group_message_event
from xhh_onebot.onebot.ws_reverse import ReverseWebSocket
from xhh_onebot.store import PendingEvent, Store
from xhh_onebot.xhh.client import XhhClient
from xhh_onebot.xhh.models import LinkContext
from xhh_onebot.xhh.poller import build_context_message

logger = logging.getLogger(__name__)


class App:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.store = Store(config.database.path)
        self.xhh = XhhClient(config.xhh)
        self.onebot = ReverseWebSocket(config.onebot, self.handle_action)
        self.reply_lock = asyncio.Lock()

    async def start(self) -> None:
        await self.store.open()
        await self.xhh.open()
        if not await self.xhh.check_login():
            logger.warning("xhh login check failed; run `python -m xhh_onebot login` if polling keeps failing")
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
                logger.exception("polling failed")
            await asyncio.sleep(self.config.xhh.check_time)

    async def poll_once(self) -> None:
        expired = await self.store.expire_pending(self.config.poller.reply_timeout)
        if expired:
            logger.warning("expired %s pending event(s)", expired)
        owners = self.config.xhh.owners
        allow_all_users = self.config.xhh.allow_all_users
        if not allow_all_users and not owners:
            logger.warning("xhh.owner is empty, no messages will be delivered")
            return
        messages = await self.xhh.fetch_mentions(limit=20)
        delivered = 0
        for message in messages:
            if delivered >= self.config.poller.max_batch:
                break
            if not allow_all_users and message.user_id not in owners:
                continue
            if message.message_id == 0 or message.comment_id == 0 or message.link_id == 0:
                continue
            if await self.store.seen_xhh_message(message.message_id):
                continue
            try:
                context = await self.xhh.get_link_context(message.link_id)
            except Exception as exc:
                logger.warning(
                    "failed to get xhh link context, delivering comment only: link_id=%s error=%s",
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
                link_id=message.link_id,
                comment_id=message.comment_id,
                root_comment_id=message.root_comment_id,
                user_id=message.user_id,
                raw_text=text,
            )
            await self.store.add_pending(event)
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
            logger.info("delivered xhh message %s as OneBot event", message.message_id)
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
            text = extract_plain_text(params.get("message"))
            if not group_id or not text.strip():
                return failed(echo, "missing group_id or message", 1400)
            reply_id = extract_reply_id(params.get("message"))
            ok = await self.reply_group(group_id, text, reply_id=reply_id)
            if not ok:
                return failed(echo, "no pending xhh message or reply failed", 1400)
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

    async def reply_group(self, group_id: int, text: str, reply_id: int | None = None) -> bool:
        async with self.reply_lock:
            pending = None
            if reply_id is not None:
                pending = await self.store.get_pending_by_message_id(reply_id)
            if pending is None:
                pending = await self.store.get_pending_for_group(group_id)
            if pending is None:
                logger.warning("no pending message for group %s", group_id)
                return False
            ok = await self.xhh.reply_comment(
                text=text,
                link_id=pending.link_id,
                reply_id=pending.comment_id,
                root_id=pending.root_comment_id,
            )
            if ok:
                await self.store.mark_replied(pending.onebot_message_id)
            else:
                await self.store.mark_failed(pending.onebot_message_id)
            await asyncio.sleep(self.config.xhh.reply_time)
            return ok
