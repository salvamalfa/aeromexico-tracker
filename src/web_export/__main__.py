"""CLI entry point: ``uv run python -m src.web_export --out web/public/data/v1``.

Builds the same payloads the published HTML already embeds, validates each
split file against contracts/web/ and privacy.yaml, and writes them under
``--out``. Fails loudly (``MissingWebInput``) instead of silently omitting a
section when a required private Gold input is absent — see
``config/web_inputs.yaml`` and ``src/web_export/inputs.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import PATHS
from src.dashboard.executive_summary import build_executive_payload
from src.dashboard.flights import build_flight_payload
from src.dashboard.market import build_market_payload
from src.web_export.analysis import MissingAnalysisInput, export_analysis
from src.web_export.executive import export_executive
from src.web_export.flights import export_flights
from src.web_export.inputs import MissingWebInput
from src.web_export.market import export_market


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=PATHS.root / "web" / "public" / "data" / "v1",
        help="Output directory (default: web/public/data/v1).",
    )
    parser.add_argument(
        "--allow-missing-analysis",
        action="store_true",
        help="Dev only: skip a period whose analysis record/approval is not present locally.",
    )
    parser.add_argument(
        "--business-metrics-proposal",
        type=Path,
        help="Review proposal to export only with matching approval receipt.",
    )
    parser.add_argument(
        "--business-metrics-receipt",
        type=Path,
        help="Owner approval receipt; both business-metrics options are required together.",
    )
    args = parser.parse_args(argv)
    if bool(args.business_metrics_proposal) != bool(args.business_metrics_receipt):
        parser.error("--business-metrics-proposal and --business-metrics-receipt must be supplied together")

    try:
        flight_payload = build_flight_payload()
        written = export_flights(flight_payload, args.out)
        executive_payload = build_executive_payload()
        written += export_executive(executive_payload, args.out)
        written += export_market(build_market_payload(), args.out)
        written += export_analysis(
            args.out,
            allow_missing=args.allow_missing_analysis,
        )
        if args.business_metrics_proposal and args.business_metrics_receipt:
            from src.web_export.business_metrics import export_approved_business_metrics

            written += export_approved_business_metrics(
                args.business_metrics_proposal,
                PATHS.root / "config/chat/metrics-candidates.json",
                args.business_metrics_receipt,
                args.out,
            )
    except (MissingWebInput, MissingAnalysisInput) as error:
        print(f"web_export: {error}", file=sys.stderr)
        return 1

    for path in sorted(written):
        size = path.stat().st_size
        print(f"{path.relative_to(args.out)}\t{size:,} bytes")
    print(f"{len(written)} file(s) written under {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
