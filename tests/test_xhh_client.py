from types import TracebackType
from typing import Any

import pytest

from xhh_onebot.config import XhhConfig
from xhh_onebot.xhh.client import XhhClient


class FakeResponse:
    status = 200

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
        return '{"status":"ok","result":{"link":{"title":"t","text":"[]"}}}'


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return FakeResponse()


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
