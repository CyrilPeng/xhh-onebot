from __future__ import annotations

import argparse
import asyncio
import logging
import shutil
from pathlib import Path

from xhh_onebot.app import App
from xhh_onebot.config import load_config, write_default_config
from xhh_onebot.log import setup_logging
from xhh_onebot.xhh.client import XhhClient


logger = logging.getLogger(__name__)


async def async_main() -> None:
    parser = argparse.ArgumentParser(prog="xhh-onebot")
    parser.add_argument("command", choices=["init", "login", "start", "check-login", "poll-once", "sign"])
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--path", default="/bbs/app/user/message", help="request path for sign command")
    parser.add_argument("--timestamp", type=int, default=None, help="fixed unix timestamp for sign command")
    parser.add_argument("--nonce", default=None, help="fixed nonce for sign command")
    parser.add_argument("--random", type=int, default=None, help="fixed random number for nonce generation")
    parser.add_argument("--ws-timeout", type=float, default=10.0, help="seconds to wait for OneBot WS in poll-once")
    args = parser.parse_args()

    setup_logging()

    if args.command == "init":
        path = Path(args.config)
        if path.exists():
            raise SystemExit(f"config already exists: {path}")
        example = Path("config.example.json")
        if example.exists():
            shutil.copyfile(example, path)
        else:
            write_default_config(path)
        print(f"created {path}")
        return

    if args.command == "sign":
        from xhh_onebot.xhh.sign import get_keys

        hkey, nonce, timestamp = get_keys(
            args.path,
            timestamp=args.timestamp,
            nonce=args.nonce,
            random_number=args.random,
        )
        print(f"path={args.path}")
        print(f"timestamp={timestamp}")
        print(f"nonce={nonce}")
        print(f"hkey={hkey}")
        return

    config = load_config(args.config)

    if args.command == "login":
        try:
            async with XhhClient(config.xhh) as client:
                await client.login_qrcode()
        except Exception:
            logger.exception("xhh login failed")
            raise SystemExit(1)
        return

    if args.command == "check-login":
        async with XhhClient(config.xhh) as client:
            ok = await client.check_login()
        print("login=ok" if ok else "login=failed")
        return

    if args.command == "poll-once":
        app = App(config)
        ws_task: asyncio.Task[None] | None = None
        try:
            await app.store.open()
            await app.xhh.open()
            ws_task = asyncio.create_task(app.onebot.run_forever())
            await asyncio.wait_for(app.onebot.connected.wait(), timeout=args.ws_timeout)
            await app.poll_once()
            await asyncio.wait_for(app.onebot.wait_until_idle(), timeout=args.ws_timeout)
        finally:
            await app.stop()
            if ws_task is not None:
                ws_task.cancel()
                try:
                    await ws_task
                except asyncio.CancelledError:
                    pass
        return

    if args.command == "start":
        # Auto-detect cookie: if missing or expired, trigger login first
        async with XhhClient(config.xhh) as client:
            if not await client.check_login():
                logger.info("No valid cookie found or cookie expired.")
                logger.info("Starting login flow - please scan the QR code...")
                try:
                    await client.login_qrcode()
                except Exception:
                    logger.exception("xhh login failed during startup")
                    raise SystemExit(1)
                logger.info("Login successful, starting adapter...")
        app = App(config)
        try:
            await app.start()
        finally:
            await app.stop()


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
