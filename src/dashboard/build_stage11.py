"""Build the local Stage 11 executive-summary prototype."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.dashboard.executive_summary import build_executive_payload
from src.dashboard.executive_summary_html import DEFAULT_OUTPUT, write_executive_html


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = build_executive_payload()
    output = write_executive_html(payload, args.output)
    print(
        f"Stage 11 executive prototype written to {output} "
        f"({payload['metadata']['quarter_count']} comparable quarters)"
    )


if __name__ == "__main__":
    main()
