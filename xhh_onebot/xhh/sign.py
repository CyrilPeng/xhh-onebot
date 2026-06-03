from __future__ import annotations

import hashlib
import time
from collections.abc import Callable

KEY = "AB45STUVWZEFGJ6CH01D237IXYPQRKLMN89"


def vm(num: int) -> int:
    if num & 128 != 0:
        return 255 & ((num << 1) ^ 27)
    return num << 1


def qm(num: int) -> int:
    return vm(num) ^ num


def _m(num: int) -> int:
    return qm(vm(num))


def ym(num: int) -> int:
    return _m(qm(vm(num)))


def gm(num: int) -> int:
    return ym(num) ^ _m(num) ^ qm(num)


def mixed(values: list[int]) -> list[int]:
    return [
        gm(values[0]) ^ ym(values[1]) ^ _m(values[2]) ^ qm(values[3]),
        qm(values[0]) ^ gm(values[1]) ^ ym(values[2]) ^ _m(values[3]),
        _m(values[0]) ^ qm(values[1]) ^ gm(values[2]) ^ ym(values[3]),
        ym(values[0]) ^ _m(values[1]) ^ qm(values[2]) ^ gm(values[3]),
        values[4],
        values[5],
    ]


def get_nonce(timestamp: int, random_number: int | None = None) -> str:
    if random_number is None:
        import random

        random_number = random.randrange(max(1, int(time.time() * 1000)))
    raw = f"{timestamp}{random_number}"
    return hashlib.md5(raw.encode()).hexdigest().upper()


def av(value: str, key: str, n: int) -> str:
    base = key[: len(key) + n]
    return "".join(base[ord(char) % len(base)] for char in value)


def sv(value: str, key: str) -> str:
    return "".join(key[ord(char) % len(key)] for char in value)


def new_str(values: list[str]) -> str:
    result: list[str] = []
    for index in range(len(values[2])):
        if len(values[0]) > index:
            result.append(values[0][index])
        if len(values[1]) > index:
            result.append(values[1][index])
        if len(values[2]) > index:
            result.append(values[2][index])
    return "".join(result)


def build_hkey(req_path: str, timestamp: int, nonce: str) -> str:
    str1 = av(str(timestamp), KEY, -2)
    str2 = sv(req_path, KEY)
    str3 = sv(nonce, KEY)
    values = sorted([str1, str2, str3], key=len)
    merged = new_str(values)
    md5_text = hashlib.md5(merged[:20].encode()).hexdigest()
    last_six = md5_text[-6:]
    count = sum(mixed([ord(char) for char in last_six]))
    suffix = f"{count % 100:02d}"
    prefix = av(md5_text[:5], KEY, -4)
    return f"{prefix}{suffix}"


def get_keys(
    req_path: str,
    *,
    timestamp: int | None = None,
    nonce: str | None = None,
    random_number: int | None = None,
    clock: Callable[[], float] = time.time,
) -> tuple[str, str, int]:
    if timestamp is None:
        timestamp = int(clock())
    if nonce is None:
        nonce = get_nonce(timestamp, random_number)
    return build_hkey(req_path, timestamp, nonce), nonce, timestamp
