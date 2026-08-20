"""Offline rebuild entry point: immutable bronze to silver to gold."""

from src.parse import run as run_parse
from src.transform import run as run_transform


def main() -> int:
    run_parse()
    run_transform()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
