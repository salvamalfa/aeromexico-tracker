"""Internal worker launched inside the clean offline rebuild checkout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.pipeline.model import PipelinePhase, PipelineRunError
from src.pipeline.runner import run_pipeline


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--phases", default="parse,transform,analytics,dashboard")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--offline", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    phases = [PipelinePhase(item.strip()) for item in args.phases.split(",") if item.strip()]
    report_path = args.report if args.report.is_absolute() else args.root / args.report
    try:
        report = run_pipeline(
            root=args.root,
            phases=phases,
            offline=args.offline,
            report_path=report_path,
            run_id="offline-rebuild",
        )
    except PipelineRunError as exc:
        print(json.dumps(exc.report.to_dict(), indent=2, ensure_ascii=False))
        return 1
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
