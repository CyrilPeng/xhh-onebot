from xhh_onebot.config import Config, load_config


def test_load_config_accepts_utf8_bom(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(Config().model_dump_json(), encoding="utf-8-sig")

    config = load_config(config_path)

    assert config.onebot.self_id == 10000001
    assert config.poller.reply_max_chars == 1000

from xhh_onebot.config import XhhConfig


def test_xhh_owner_star_allows_all_users():
    config = XhhConfig(owner="*")

    assert config.allow_all_users is True
    assert config.owners == set()


def test_xhh_owner_whitelist_keeps_numeric_ids():
    config = XhhConfig(owner="123, 456")

    assert config.allow_all_users is False
    assert config.owners == {123, 456}
