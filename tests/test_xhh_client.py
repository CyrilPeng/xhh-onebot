import json
from types import TracebackType
from typing import Any

import pytest

from xhh_onebot.config import XhhConfig
from xhh_onebot.xhh.client import XhhClient


class FakeResponse:
    status = 200

    def __init__(self, text: str | None = None) -> None:
        self._text = text or '{"status":"ok","result":{"link":{"title":"t","text":"[]"}}}'

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    async def text(self) -> str:
        return self._text


class FakeSession:
    def __init__(self, response_text: str | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response_text = response_text

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return FakeResponse(self.response_text)


@pytest.mark.asyncio
async def test_get_link_context_uses_browser_observed_query_params():
    client = XhhClient(XhhConfig(base_url="https://api.example.test"))
    session = FakeSession()
    client.session = session  # type: ignore[assignment]

    await client.get_link_context(123456)

    call = session.calls[0]
    assert call["url"] == "https://api.example.test/bbs/app/link/tree"
    assert "h_src" not in call["params"]
    assert call["params"]["app"] == "heybox"
    assert call["params"]["version"] == "999.0.4"
    assert call["params"]["web_version"] == "2.5"
    assert call["params"]["device_info"] == "Edge"
    assert call["params"]["link_id"] == 123456
    assert call["params"]["is_first"] == 1
    assert call["params"]["page"] == 1
    assert call["params"]["index"] == 1
    assert call["params"]["limit"] == 20
    assert call["params"]["owner_only"] == 0
    assert call["params"]["hkey"]

@pytest.mark.asyncio
async def test_fetch_mentions_uses_browser_observed_message_type():
    client = XhhClient(XhhConfig(base_url="https://api.example.test"))
    session = FakeSession()
    client.session = session  # type: ignore[assignment]

    await client.fetch_mentions(limit=20)

    call = session.calls[0]
    assert call["url"] == "https://api.example.test/bbs/app/user/message"
    assert call["params"]["message_type"] == 16
    assert "list_type" not in call["params"]
    assert call["params"]["offset"] == 0
    assert call["params"]["limit"] == 20
    assert call["params"]["no_more"] == "false"


@pytest.mark.asyncio
async def test_fetch_mentions_parses_log_metadata():
    payload = {
        "status": "ok",
        "result": {
            "messages": [
                {
                    "comment_a_id": 881321164,
                    "comment_a_text": "@bot please review",
                    "message_id": 3885547813,
                    "root_comment_id": 881321164,
                    "linkid": 182596616,
                    "userid_a": 30060992,
                    "user_a": {"username": "author-a"},
                    "userid_b": 99607404,
                    "user_b": {"username": "bot-name"},
                    "link_title": "post title",
                    "link_user": "author-a",
                    "link_userid": 30060992,
                    "timestamp": "1780587671.0000",
                }
            ]
        },
    }
    client = XhhClient(XhhConfig(base_url="https://api.example.test"))
    client.session = FakeSession(json.dumps(payload))  # type: ignore[assignment]

    messages = await client.fetch_mentions(limit=20)

    assert messages[0].user_name == "author-a"
    assert messages[0].link_title == "post title"
    assert messages[0].link_user == "author-a"
    assert messages[0].link_user_id == 30060992
    assert messages[0].mentioned_at == 1780587671
    assert messages[0].mentioned_user_id == 99607404
    assert messages[0].mentioned_user_name == "bot-name"

@pytest.mark.asyncio
async def test_reply_comment_uses_browser_observed_is_cy_default():
    client = XhhClient(XhhConfig(base_url="https://api.example.test"))
    session = FakeSession()
    client.session = session  # type: ignore[assignment]

    await client.reply_comment("hello", link_id=123, reply_id=-1, root_id=-1)

    call = session.calls[0]
    assert call["url"] == "https://api.example.test/bbs/app/comment/create"
    assert call["data"] == "is_cy=0&link_id=123&reply_id=-1&root_id=-1&text=hello"


@pytest.mark.asyncio
async def test_reply_comment_uses_browser_observed_percent_encoding():
    client = XhhClient(XhhConfig(base_url="https://api.example.test"))
    session = FakeSession()
    client.session = session  # type: ignore[assignment]

    await client.reply_comment(
        "xhh-onebot encode test a&b=1\nurl https://example.com/?q=a+b",
        link_id=182596616,
        reply_id=-1,
        root_id=-1,
    )

    call = session.calls[0]
    assert call["data"] == (
        "is_cy=0&link_id=182596616&reply_id=-1&root_id=-1&"
        "text=xhh-onebot%20encode%20test%20a%26b%3D1%0Aurl%20https%3A%2F%2Fexample.com%2F%3Fq%3Da%2Bb"
    )


@pytest.mark.asyncio
async def test_reply_comment_uses_observed_nested_reply_ids():
    client = XhhClient(XhhConfig(base_url="https://api.example.test"))
    session = FakeSession()
    client.session = session  # type: ignore[assignment]

    await client.reply_comment("nested", link_id=182596616, reply_id=879644492, root_id=879644492)

    call = session.calls[0]
    assert call["data"] == "is_cy=0&link_id=182596616&reply_id=879644492&root_id=879644492&text=nested"


def test_parse_qr_login_params_requires_login_url():
    client = XhhClient(XhhConfig(base_url="https://api.example.test"))

    params = client.parse_qr_login_params(
        "https://api.xiaoheihe.cn/account/qr_login/?qr=abc-123&app=heybox"
    )

    assert params == {"qr": "abc-123", "app": "heybox"}


def test_qrcode_file_uses_cookie_directory():
    client = XhhClient(XhhConfig(cookie_file="data/cookie.json"))

    assert str(client.qrcode_file()).replace("\\", "/") == "data/qrcode.png"


def test_cookie_file_uses_configured_relative_path_outside_docker():
    client = XhhClient(XhhConfig(cookie_file="cookie.json"))

    assert str(client.cookie_file()).replace("\\", "/") == "cookie.json"


def test_qrcode_files_include_primary_path():
    client = XhhClient(XhhConfig(cookie_file="data/cookie.json"))

    paths = [str(path).replace("\\", "/") for path in client.qrcode_files()]

    assert "data/qrcode.png" in paths


def test_cookie_file_redirects_to_docker_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path as P

    original_is_dir = P.is_dir

    def mock_is_dir(self: P) -> bool:
        if self == P("/app/data"):
            return True
        return original_is_dir(self)

    monkeypatch.setattr(P, "is_dir", mock_is_dir)

    client = XhhClient(XhhConfig(cookie_file="cookie.json"))
    assert str(client.cookie_file()).replace("\\", "/") == "/app/data/cookie.json"


def test_cookie_file_preserves_subdir_even_in_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    from pathlib import Path as P

    original_is_dir = P.is_dir

    def mock_is_dir(self: P) -> bool:
        if self == P("/app/data"):
            return True
        return original_is_dir(self)

    monkeypatch.setattr(P, "is_dir", mock_is_dir)

    client = XhhClient(XhhConfig(cookie_file="data/cookie.json"))
    assert str(client.cookie_file()).replace("\\", "/") == "data/cookie.json"
