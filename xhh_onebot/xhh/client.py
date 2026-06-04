from __future__ import annotations

import base64
import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse

import aiohttp
import qrcode

from xhh_onebot.config import XhhConfig
from xhh_onebot.xhh.models import CookieInfo, LinkContext, XhhMessage
from xhh_onebot.xhh.sign import get_keys

logger = logging.getLogger(__name__)


class XhhClient:
    def __init__(self, config: XhhConfig) -> None:
        self.config = config
        self.cookie = CookieInfo()
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "XhhClient":
        await self.open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    async def open(self) -> None:
        if self.session is None:
            self.session = aiohttp.ClientSession()
        self.load_cookie()

    async def close(self) -> None:
        if self.session is not None:
            await self.session.close()
            self.session = None

    def load_cookie(self) -> None:
        path = Path(self.config.cookie_file)
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        self.cookie = CookieInfo(
            cookie=data.get("cookie", ""),
            heybox_id=str(data.get("heyboxId") or data.get("heybox_id") or ""),
            time=int(data.get("time", 0)),
        )

    def save_cookie(self) -> None:
        path = Path(self.config.cookie_file)
        if path.parent != Path(""):
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "cookie": self.cookie.cookie,
                    "heyboxId": self.cookie.heybox_id,
                    "time": self.cookie.time,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def qrcode_file(self) -> Path:
        path = Path(self.config.cookie_file)
        if path.parent == Path(""):
            return Path("qrcode.png")
        return path.parent / "qrcode.png"

    def parse_qr_login_params(self, qr_url: str) -> dict[str, str]:
        parsed = urlparse(qr_url)
        if parsed.path != "/account/qr_login/":
            raise RuntimeError(f"unexpected xhh qr login path: {qr_url}")
        params = dict(parse_qsl(parsed.query, keep_blank_values=True))
        if not params.get("qr"):
            raise RuntimeError(f"missing qr token in xhh qr login url: {qr_url}")
        return params

    def _session(self) -> aiohttp.ClientSession:
        if self.session is None:
            raise RuntimeError("client is not open")
        return self.session

    def _common_params(self, path: str) -> dict[str, str]:
        hkey, nonce, timestamp = get_keys(path)
        params = {
            "os_type": "web",
            "app": "heybox",
            "client_type": "web",
            "version": self.config.version,
            "web_version": self.config.web_version,
            "x_client_type": "web",
            "x_app": "heybox_website",
            "x_os_type": "Windows",
            "device_info": "Edge",
            "device_id": self.config.device_id,
            "hkey": hkey,
            "_time": str(timestamp),
            "nonce": nonce,
            "_notip": "true",
        }
        if self.cookie.heybox_id:
            params["heybox_id"] = self.cookie.heybox_id
        return params

    def _login_params(self, path: str) -> dict[str, str]:
        params = self._common_params(path)
        params.update(
            {
                "app": "web",
                "x_client_type": "weboutapp",
                "web_version": "",
            }
        )
        return params

    def _cookie_from_login_result(self, result: dict[str, Any]) -> tuple[str, str]:
        profile = result.get("profile") or {}
        account_detail = result.get("account_detail") or {}
        heybox_id = str(profile.get("heybox_id") or account_detail.get("userid") or "")
        pkey = str(result.get("pkey") or "")
        if not heybox_id or not pkey:
            raise RuntimeError(f"xhh qr login returned ok but missing heybox_id or pkey: {result}")
        return (
            f"heybox_id={heybox_id};user_heybox_id={heybox_id};pkey={pkey};user_pkey={pkey}"
            + self._token_cookie(),
            heybox_id,
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        raw_query: str = "",
    ) -> dict[str, Any]:
        query = dict(params or {})
        query.update(self._common_params(path))
        headers = {
            "host": urlparse(self.config.base_url).netloc or "api.xiaoheihe.cn",
            "Referer": "https://www.xiaoheihe.cn/",
        }
        if data:
            headers["content-type"] = "application/x-www-form-urlencoded;charset=utf-8"
        if self.cookie.cookie:
            headers["cookie"] = self.cookie.cookie
        url = f"{self.config.base_url}{path}{raw_query}"
        async with self._session().request(
            method,
            url,
            params=query,
            data=urlencode(data or {}, quote_via=quote) if data else None,
            headers=headers,
        ) as response:
            text = await response.text()
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"xhh request failed: {response.status} {text}")
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"invalid xhh json response: {text}") from exc
            if payload.get("status") in {"failed", "fail"} or payload.get("stat") in {"failed", "fail"}:
                logger.warning("xhh api returned failure for %s %s: %s", method, path, payload)
            return payload

    async def login_qrcode(self) -> None:
        self.cookie = CookieInfo()
        while True:
            login_query = self._login_params("/account/get_qrcode_url/")
            async with self._session().get(
                f"{self.config.base_url}/account/get_qrcode_url/",
                params=login_query,
                headers={
                    "host": urlparse(self.config.base_url).netloc or "api.xiaoheihe.cn",
                    "Referer": "https://login.xiaoheihe.cn/",
                },
            ) as qr_response:
                response = await qr_response.json(content_type=None)
            result = response.get("result", {})
            qr_url = result.get("qr_url")
            if not qr_url:
                raise RuntimeError(f"missing qr_url: {response}")
            params = self.parse_qr_login_params(str(qr_url))
            expire = int(result.get("expire") or 120)
            qrcode_path = self.qrcode_file()
            qrcode_path.parent.mkdir(parents=True, exist_ok=True)
            image = qrcode.make(qr_url)
            image.save(qrcode_path)
            if qrcode_path != Path("qrcode.png"):
                image.save("qrcode.png")
            logger.info("Scan %s to login Xiaoheihe", qrcode_path)
            logger.info("If terminal QR cannot be scanned, open the PNG file instead.")
            qr = qrcode.QRCode(border=1)
            qr.add_data(qr_url)
            qr.make(fit=True)
            qr.print_ascii(invert=True)
            logger.info("QR login URL: %s", qr_url)

            expires_at = time.monotonic() + max(expire - 3, 10)
            last_error = None
            while time.monotonic() < expires_at:
                state_params = self._login_params("/account/qr_state/")
                state_params.update(params)
                async with self._session().get(
                    f"{self.config.base_url}/account/qr_state/",
                    params=state_params,
                    headers={
                        "host": urlparse(self.config.base_url).netloc or "api.xiaoheihe.cn",
                        "Referer": "https://login.xiaoheihe.cn/",
                    },
                ) as resp:
                    data = await resp.json(content_type=None)
                    result = data.get("result", {})
                    error = result.get("error")
                    error_msg = result.get("error_msg") or ""
                    if error != last_error:
                        logger.info("QR login state: %s %s", error, error_msg)
                        last_error = error
                    if error == "ready":
                        await asyncio_sleep(1)
                        continue
                    if error != "ok":
                        await asyncio_sleep(1)
                        continue
                    cookies = resp.cookies
                    cookie_parts = [f"{key}={morsel.value}" for key, morsel in cookies.items()]
                    if cookie_parts:
                        self.cookie.cookie = ";".join(cookie_parts) + self._token_cookie()
                        if "user_heybox_id" in cookies:
                            self.cookie.heybox_id = cookies["user_heybox_id"].value
                    else:
                        self.cookie.cookie, self.cookie.heybox_id = self._cookie_from_login_result(result)
                    self.cookie.time = int(time.time())
                    self.save_cookie()
                    logger.info("Login success: %s", result.get("nickname", ""))
                    return
            logger.info("QR code expired, refreshing...")

    async def check_login(self) -> bool:
        if not self.cookie.cookie:
            return False
        try:
            data = await self.request(
                "GET",
                "/bbs/app/user/message",
                params={"list_type": 0, "offset": 0, "limit": 1, "no_more": "false"},
            )
        except Exception:
            logger.exception("xhh login check failed")
            return False
        return data.get("status") == "ok" or data.get("stat") == "ok"

    def _token_cookie(self) -> str:
        raw = bytearray()
        for text in [
            str(int(time.time())),
            "\u5509\uff1f\uff01\u4e91\u6735\uff01",
            "\u54d2\u54d2\u54d2\u54d2\u54d2\uff0c\u597d\u60f3\u73a9\u539f\u795e",
            "\u4e91\uff01\u539f\uff01\u795e\uff01",
        ]:
            raw.extend(hashlib.md5(text.encode()).digest())
        raw.append(0)
        return ";x_xhh_tokenid=" + base64.b64encode(bytes(raw)).decode()

    async def fetch_mentions(self, limit: int = 20) -> list[XhhMessage]:
        data = await self.request(
            "GET",
            "/bbs/app/user/message",
            params={"list_type": 0, "offset": 0, "limit": limit, "no_more": "false"},
        )
        messages = data.get("result", {}).get("messages", []) or []
        result: list[XhhMessage] = []
        for item in messages:
            result.append(
                XhhMessage(
                    comment_id=int(item.get("comment_a_id") or 0),
                    comment_text=str(item.get("comment_a_text") or ""),
                    message_id=int(item.get("message_id") or 0),
                    root_comment_id=int(item.get("root_comment_id") or 0),
                    link_id=int(item.get("linkid") or 0),
                    user_id=int(item.get("userid_a") or 0),
                )
            )
        return result

    async def get_link_context(self, link_id: int) -> LinkContext:
        data = await self.request(
            "GET",
            "/bbs/app/link/tree",
            params={
                "link_id": link_id,
                "is_first": 1,
                "page": 1,
                "index": 1,
                "limit": 20,
                "owner_only": 0,
            },
        )
        if data.get("status") != "ok":
            raise RuntimeError(f"failed to get link context: {data}")
        link = data.get("result", {}).get("link", {})
        context = LinkContext(
            title=str(link.get("title") or ""),
            topics=[str(item.get("name")) for item in link.get("topics", []) if item.get("name")],
            tags=[str(item.get("name")) for item in link.get("hashtags", []) if item.get("name")],
        )
        raw_text = link.get("text") or "[]"
        try:
            context.parts = json.loads(raw_text)
        except json.JSONDecodeError:
            context.parts = [{"type": "text", "text": str(raw_text)}]
        return context

    async def reply_comment(self, text: str, link_id: int, reply_id: int, root_id: int, is_cy: str = "0") -> bool:
        data = await self.request(
            "POST",
            "/bbs/app/comment/create",
            data={
                "is_cy": is_cy,
                "link_id": str(link_id),
                "reply_id": str(reply_id),
                "root_id": str(root_id),
                "text": text,
            },
        )
        if data.get("status") == "ok":
            return True
        if data.get("status") == "failed":
            logger.warning("xhh comment target unavailable, marking as handled: %s", data)
            return True
        logger.error("xhh reply failed: %s", data)
        return False


async def asyncio_sleep(seconds: float) -> None:
    import asyncio

    await asyncio.sleep(seconds)
