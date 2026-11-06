"""Thin CLI entry points shared by the private coordinator and product outbox."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path


def coordinator_main(run, load, description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--workspace", type=Path, required=True)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument("--prepare", type=Path, help="Write private plan once; never activate")
    operation.add_argument("--record", type=Path, help="Record an observed action; never send it")
    parser.add_argument("--now", default=datetime.now(UTC).isoformat())
    args = parser.parse_args()
    try:
        output = run(
            args.workspace,
            request=load(args.prepare) if args.prepare else None,
            action=load(args.record) if args.record else None,
            now=args.now,
        )
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError, OSError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "scheduled_executions": 0}))
        return 1


def handoffs_main(run, load, description, argv=None):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--record", type=Path)
    args = parser.parse_args(argv)
    try:
        result = run(args.workspace, action=load(args.record) if args.record else None)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (KeyError, ValueError, OSError, TypeError, ImportError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "native_sends": 0}))
        return 1
