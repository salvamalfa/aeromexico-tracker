"""Run the local Airline Tracker chat API on loopback, or hash its password.

``python -m src.conversational_analytics hash-password`` reads a password twice
without echo and prints only its scrypt hash. ``--generate`` creates a random
password instead and prints it once, next to its hash, for the owner to keep.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import sys

from .auth import MIN_PASSWORD_LENGTH, generate_password, hash_password


def hash_password_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.conversational_analytics hash-password",
        description="Print the scrypt hash for CHAT_PASSWORDS_JSON; the password is never stored.",
    )
    parser.add_argument(
        "--generate", action="store_true", help="generate a random password and print it with its hash"
    )
    args = parser.parse_args(argv)
    if args.generate:
        password = generate_password()
        print(f"password: {password}")
        print(f"password_hash: {hash_password(password)}")
        return 0
    password = getpass.getpass("Contraseña: ")
    if password != getpass.getpass("Repite la contraseña: "):
        print("Las contraseñas no coinciden.", file=sys.stderr)
        return 2
    if len(password) < MIN_PASSWORD_LENGTH:
        print(f"Usa al menos {MIN_PASSWORD_LENGTH} caracteres.", file=sys.stderr)
        return 2
    print(hash_password(password))
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["hash-password"]:
        return hash_password_main(argv[1:])
    if argv[:1] == ["import-usage"]:
        from .usage_import import import_main

        return import_main(argv[1:])
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
    from .api import create_app
    from .config import ChatConfig

    logging.basicConfig(level=getattr(logging, args.log_level.upper()))
    app = create_app(ChatConfig.from_env())
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
