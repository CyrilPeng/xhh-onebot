from xhh_onebot.xhh.sign import av, build_hkey, get_keys, get_nonce, new_str, sv


def test_mapping_helpers_are_deterministic():
    key = "AB45STUVWZEFGJ6CH01D237IXYPQRKLMN89"
    assert av("123", key, -2) == av("123", key, -2)
    assert sv("/bbs/app/user/message", key) == sv("/bbs/app/user/message", key)
    assert new_str(["a", "bc", "def"]) == "abdcef"


def test_get_keys_accepts_fixed_inputs():
    hkey, nonce, timestamp = get_keys(
        "/bbs/app/user/message",
        timestamp=1770000000,
        random_number=123456,
    )
    assert timestamp == 1770000000
    assert nonce == get_nonce(1770000000, 123456)
    assert hkey == build_hkey("/bbs/app/user/message", timestamp, nonce)
    assert len(hkey) == 7
