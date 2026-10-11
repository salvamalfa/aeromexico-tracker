"""Regenerate only existing query-plan gold rows from the pinned public snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.evaluation import BUSINESS_FIXTURE_PATH, _snapshot_rows
from src.conversational_analytics.evaluation_business import validate_business_fixture


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=ROOT / "site")
    parser.add_argument("--write", action="store_true", help="guardar filas solo después de validar las versiones")
    args = parser.parse_args()
    payload = json.loads(BUSINESS_FIXTURE_PATH.read_text(encoding="utf-8"))
    validate_business_fixture(payload)
    snapshot = Snapshot(args.snapshot)
    expected = payload["expected_versions"]
    actual = {"data_version": snapshot.version, "semantic_version": snapshot.semantic_version}
    if actual != expected:
        print(json.dumps({"status": "blocked_version_mismatch", "expected": expected, "actual": actual}, indent=2))
        return 2
    changed = []
    for case in payload["cases"]:
        if case["expected"].get("status") != "supported" or not case["expected"].get("plan"):
            continue
        rows = _snapshot_rows(snapshot, case)
        case["expected"]["rows"] = rows
        case["gold_state"] = "generated_by_tool_registry_from_pinned_public_snapshot"
        changed.append(case["id"])
    if args.write:
        BUSINESS_FIXTURE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "written" if args.write else "preview", "case_ids": changed, "writes": [str(BUSINESS_FIXTURE_PATH)] if args.write else []}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
