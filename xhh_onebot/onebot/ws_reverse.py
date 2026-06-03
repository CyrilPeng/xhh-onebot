from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from websockets.exceptions import InvalidStatus
from websockets.client import WebSocketClientProtocol

from xhh_onebot.config import OneBotConfig
from xhh_onebot.onebot.events import heartbeat_event, lifecycle_event

logger = logging.getLogger(__name__)
ActionHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any] | None]]


class ReverseWebSocket:
    def __init__(self, config: OneBotConfig, action_handler: ActionHandler) -> None:
        self.config = config
        self.action_handler = action_handler
        self.ws: WebSocketClientProtocol | None = None
        self.connected = asyncio.Event()
        self.outbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._stopped = False

    async def stop(self) -> None:
        self._stopped = True
        if self.ws is not None:
            await self.ws.close()

    async def send_event(self, event: dict[str, Any]) -> None:
        await self.outbox.put(event)

    async def wait_until_idle(self) -> None:
        await self.outbox.join()

    async def run_forever(self) -> None:
        headers = {
            "X-Self-ID": str(self.config.self_id),
            "X-Client-Role": "Universal",
            "User-Agent": "xhh-onebot/0.1.0",
        }
        if self.config.access_token:
            headers["Authorization"] = f"Bearer {self.config.access_token}"
        while not self._stopped:
            try:
                logger.info("connecting to OneBot reverse WS: %s", self.config.reverse_ws_url)
                connect_kwargs: dict[str, Any] = {"ping_interval": None}
                signature = inspect.signature(websockets.connect)
                if headers:
                    if "additional_headers" in signature.parameters:
                        connect_kwargs["additional_headers"] = headers
                    else:
                        connect_kwargs["extra_headers"] = headers
                async with websockets.connect(self.config.reverse_ws_url, **connect_kwargs) as ws:
                    self.ws = ws
                    self.connected.set()
                    await self._send(lifecycle_event(self.config.self_id))
                    tasks = [
                        asyncio.create_task(self._sender(ws)),
                        asyncio.create_task(self._receiver(ws)),
                        asyncio.create_task(self._heartbeat()),
                    ]
                    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
                    for task in pending:
                        task.cancel()
                    for task in pending:
                        with contextlib.suppress(asyncio.CancelledError):
                            await task
                    for task in done:
                        task.result()
            except InvalidStatus as exc:
                status_code = getattr(getattr(exc, "response", None), "status_code", None) or getattr(
                    getattr(exc, "response", None), "status", None
                )
                if status_code == 401:
                    logger.error(
                        "OneBot reverse WS authentication failed: HTTP 401. "
                        "Check onebot.access_token in config.json and AstrBot OneBot settings."
                    )
                else:
                    logger.exception("OneBot reverse WS rejected: %s", exc)
            except Exception:
                logger.exception("OneBot reverse WS disconnected")
            finally:
                self.connected.clear()
                self.ws = None
            if not self._stopped:
                await asyncio.sleep(self.config.reconnect_interval)

    async def _send(self, payload: dict[str, Any]) -> None:
        if self.ws is None:
            await self.outbox.put(payload)
            return
        await self.ws.send(json.dumps(payload, ensure_ascii=False))

    async def _sender(self, ws: WebSocketClientProtocol) -> None:
        while True:
            event = await self.outbox.get()
            try:
                await ws.send(json.dumps(event, ensure_ascii=False))
            finally:
                self.outbox.task_done()

    async def _receiver(self, ws: WebSocketClientProtocol) -> None:
        async for raw in ws:
            try:
                action = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("invalid OneBot action: %s", raw)
                continue
            response = await self.action_handler(action)
            if response is not None:
                await ws.send(json.dumps(response, ensure_ascii=False))

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(self.config.heartbeat_interval)
            await self._send(heartbeat_event(self.config.self_id, self.config.heartbeat_interval * 1000))
