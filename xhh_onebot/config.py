from __future__ import annotations

import json
from pathlib import Path
from pydantic import BaseModel, Field


class OneBotConfig(BaseModel):
    reverse_ws_url: str = "ws://127.0.0.1:6199/ws"
    access_token: str = ""
    self_id: int = 10000001
    mention_self: bool = True
    heartbeat_interval: int = 30
    reconnect_interval: int = 5


class XhhConfig(BaseModel):
    base_url: str = "https://api.xiaoheihe.cn"
    owner: str = ""
    check_time: int = 30
    reply_time: int = 5
    device_id: str = ""
    version: str = "999.0.4"
    web_version: str = "2.5"
    cookie_file: str = "cookie.json"

    @property
    def owners(self) -> set[int]:
        result: set[int] = set()
        for item in self.owner.split(","):
            item = item.strip()
            if item == "*":
                continue
            if item:
                result.add(int(item))
        return result

    @property
    def allow_all_users(self) -> bool:
        return any(item.strip() == "*" for item in self.owner.split(","))


class PollerConfig(BaseModel):
    max_batch: int = 3
    context_max_chars: int = 3000
    post_context_max_chars: int = 1200
    reply_max_chars: int = 1000
    reply_timeout: int = 300


class DatabaseConfig(BaseModel):
    path: str = "data/xhh-onebot.db"


class Config(BaseModel):
    onebot: OneBotConfig = Field(default_factory=OneBotConfig)
    xhh: XhhConfig = Field(default_factory=XhhConfig)
    poller: PollerConfig = Field(default_factory=PollerConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)


def load_config(path: str | Path = "config.json") -> Config:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"config file not found: {config_path}")
    return Config.model_validate_json(config_path.read_text(encoding="utf-8-sig"))


def write_default_config(path: str | Path = "config.json") -> None:
    config_path = Path(path)
    config_path.write_text(
        json.dumps(Config().model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
