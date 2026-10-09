"""Offline dry-run/apply for one proven unstarted F2.2 case attempt."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def main() -> int:
    from scripts.chat.reconcile_terminal_campaign_report import _plan
    from src.conversational_analytics.evaluation_live_rearm import rearm_unstarted_case

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path, help="Checkpoint privado de campaña")
    parser.add_argument("--state-sha256", required=True, help="Hash exacto esperado del checkpoint")
    parser.add_argument("--report", required=True, type=Path, help="Informe privado del intento sin inicio")
    parser.add_argument("--report-sha256", required=True, help="Hash exacto esperado del informe")
    parser.add_argument(
        "--apply", action="store_true", help="Aplicar al checkpoint después de todas las pruebas"
    )
    args = parser.parse_args()
    runs, cases = _plan(args.state, args.report)
    result = rearm_unstarted_case(
        state_path=args.state,
        failed_report_path=args.report,
        expected_state_sha256=args.state_sha256,
        expected_report_sha256=args.report_sha256,
        runs=runs,
        cases=cases,
        apply=args.apply,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
