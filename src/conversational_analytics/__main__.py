"""Run the local Airline Tracker chat API on loopback."""

from __future__ import annotations

import argparse
import logging

from .api import create_app
from .config import ChatConfig


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Airline Tracker local chat service")
    parser.add_argument("--host", default="127.0.0.1", help="local bind address; must be loopback")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--log-level", choices=("warning", "info", "error"), default="warning")
    args = parser.parse_args(argv)
    try:
        import ipaddress

        if not ipaddress.ip_address(args.host).is_loopback:
            parser.error("local pilot must bind to a loopback address")
    except ValueError:
        parser.error("--host must be a loopback IP address")
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit("Install the optional chat dependencies to run the API") from exc
    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    app = create_app(ChatConfig.from_env())
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
