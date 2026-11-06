#!/usr/bin/env python3
"""Classify AMR queue rows for the current invocation and stale-run recovery."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from amr_dates import parse_sheet_date


QUARANTINE_CLASSES = {"infrastructure", "contract", "cleanup", "integrity"}
SAME_DAY_RETRY_CLASSES = {"infrastructure"}
RECOVERY_SWEEP_CLASSES = {"infrastructure", "contract", "cleanup"}


def optional_sheet_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    return parse_sheet_date(str(value))


def parse_timestamp(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value)
    if "T" not in text:
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("last_attempt timestamp must include a UTC offset")
    return parsed


def classify(
    row: dict[str, Any],
    query_date: date,
    now: datetime,
    allow_recovery_sweep: bool = False,
) -> dict[str, Any]:
    control_row = row["control_row"]
    if not row["active"]:
        return {"control_row": control_row, "action": "skip_inactive", "run_date": None}

    status = str(row.get("status") or "Pendiente")
    last_success = optional_sheet_date(row.get("last_success"))
    last_attempt_date = optional_sheet_date(row.get("last_attempt_date"))
    manual_force = bool(row.get("manual_force", False))
    retry_after = None

    if status in ("Pendiente", ""):
        if manual_force:
            action = "dispatch"
        elif last_success is not None and last_success > query_date:
            action = "review_future_success"
        elif last_success == query_date:
            action = "skip_already_processed_today"
        else:
            action = "dispatch"
    elif status == "Listo":
        if last_success is not None and last_success > query_date:
            action = "review_future_success"
        elif last_success == query_date:
            action = "skip_already_processed_today"
        else:
            action = "dispatch"
    elif status == "Error":
        error_class = row.get("error_class")
        if error_class == "worker_error":
            error_class = "infrastructure"
        consecutive = int(row.get("consecutive") or 0)
        delayed_retry_count = int(row.get("delayed_retry_count") or 0)
        recovery_pass_date = optional_sheet_date(row.get("recovery_pass_date"))
        last_attempt_timestamp = parse_timestamp(row.get("last_attempt_timestamp"))
        if error_class in SAME_DAY_RETRY_CLASSES:
            retry_after = parse_timestamp(row.get("retry_after_timestamp"))
            if retry_after is None and last_attempt_timestamp is not None:
                retry_after = last_attempt_timestamp + timedelta(minutes=10)
        recovery_eligible = (
            allow_recovery_sweep
            and error_class in RECOVERY_SWEEP_CLASSES
            and recovery_pass_date != query_date
            and (last_attempt_date is None or last_attempt_date <= query_date)
        )
        if recovery_eligible:
            action = "dispatch_recovery"
        elif not manual_force and error_class in QUARANTINE_CLASSES and consecutive >= 3:
            action = "quarantine"
        elif manual_force:
            action = "dispatch"
        elif last_attempt_date is None:
            action = "review_ambiguous_error"
        elif last_attempt_date > query_date:
            action = "review_future_attempt"
        elif last_attempt_date == query_date:
            if (
                error_class in SAME_DAY_RETRY_CLASSES
                and delayed_retry_count < 1
                and retry_after is not None
            ):
                action = "dispatch_delayed_retry" if now >= retry_after else "wait_delayed_retry"
            else:
                action = "skip_already_attempted_today"
        else:
            action = "dispatch"
    elif status == "En curso":
        if row.get("current_run_owned", False):
            action = "resume_reconcile"
        elif row.get("foreign_lease_active", False):
            action = "skip_foreign_lease"
        else:
            last_attempt = parse_timestamp(row.get("last_attempt_timestamp"))
            if last_attempt is None:
                definitely_old = (
                    last_attempt_date is not None
                    and last_attempt_date < (now - timedelta(hours=6)).date()
                )
                action = "stale_reconcile" if definitely_old else "review_ambiguous_in_progress"
            elif now - last_attempt >= timedelta(hours=6):
                action = "stale_reconcile"
            else:
                action = "skip_recent_in_progress"
    else:
        action = "review_unknown_status"

    decision = {
        "control_row": control_row,
        "action": action,
        "run_date": query_date.strftime("%d/%m/%Y"),
    }
    if retry_after is not None:
        decision["retry_after"] = retry_after.isoformat()
    return decision


def decide(payload: dict[str, Any]) -> dict[str, Any]:
    query_date = parse_sheet_date(payload["query_date"])
    now = datetime.fromisoformat(payload["now"].replace("Z", "+00:00"))
    if now.tzinfo is None:
        raise ValueError("now must include a UTC offset")
    allow_recovery_sweep = bool(payload.get("allow_recovery_sweep", False))
    return {
        "query_date": payload["query_date"],
        "decisions": [
            classify(row, query_date, now, allow_recovery_sweep)
            for row in payload["rows"]
        ],
    }


def self_test() -> None:
    payload = {
        "query_date": "03/08/2026",
        "now": "2026-08-03T12:00:00-06:00",
        "rows": [
            {"control_row": 2, "active": True, "status": "Listo", "last_success": "26/07/2026"},
            {"control_row": 3, "active": True, "status": "Listo", "last_success": "03/08/2026"},
            {"control_row": 4, "active": True, "status": "Error", "last_attempt_date": "02/08/2026", "error_class": "availability", "consecutive": 9},
            {"control_row": 5, "active": True, "status": "Error", "last_attempt_date": "02/08/2026", "error_class": "infrastructure", "consecutive": 3},
            {"control_row": 6, "active": True, "status": "En curso", "last_attempt_timestamp": "2026-08-03T04:00:00-06:00"},
            {"control_row": 7, "active": True, "status": "En curso", "last_attempt_timestamp": "2026-08-03T10:00:00-06:00"},
            {"control_row": 8, "active": True, "status": "Error", "last_attempt_date": "03/08/2026", "error_class": "availability", "consecutive": ""},
            {"control_row": 9, "active": True, "status": "Error", "last_attempt_date": "26/07/2026", "error_class": "infrastructure", "consecutive": None},
            {"control_row": 10, "active": True, "status": "Error", "last_attempt_date": "", "error_class": "infrastructure", "consecutive": ""},
            {"control_row": 11, "active": True, "status": "En curso", "last_attempt_date": "02/08/2026", "last_attempt_timestamp": ""},
            {"control_row": 12, "active": True, "status": "En curso", "last_attempt_date": "03/08/2026", "last_attempt_timestamp": ""},
            {"control_row": 13, "active": True, "status": "Pendiente", "last_success": "", "manual_force": False},
            {"control_row": 14, "active": True, "status": "Pendiente", "last_success": "", "manual_force": True},
            {"control_row": 15, "active": True, "status": "Error", "last_attempt_date": "02/08/2026", "error_class": "infrastructure", "consecutive": 3, "manual_force": True},
            {"control_row": 16, "active": True, "status": "Listo", "last_success": "04/08/2026"},
            {"control_row": 17, "active": True, "status": "Error", "last_attempt_date": "03/08/2026", "last_attempt_timestamp": "2026-08-03T11:30:00-06:00", "error_class": "infrastructure", "consecutive": 1, "delayed_retry_count": 0},
            {"control_row": 18, "active": True, "status": "Error", "last_attempt_date": "03/08/2026", "last_attempt_timestamp": "2026-08-03T11:55:00-06:00", "error_class": "infrastructure", "consecutive": 1, "delayed_retry_count": 0},
            {"control_row": 19, "active": True, "status": "Error", "last_attempt_date": "03/08/2026", "last_attempt_timestamp": "2026-08-03T11:30:00-06:00", "error_class": "infrastructure", "consecutive": 1, "delayed_retry_count": 1},
            {"control_row": 20, "active": True, "status": "Error", "last_attempt_date": "03/08/2026", "last_attempt_timestamp": "2026-08-03T11:30:00-06:00", "error_class": "worker_error", "consecutive": 1},
        ],
    }
    actions = [item["action"] for item in decide(payload)["decisions"]]
    assert actions == [
        "dispatch",
        "skip_already_processed_today",
        "dispatch",
        "quarantine",
        "stale_reconcile",
        "skip_recent_in_progress",
        "skip_already_attempted_today",
        "dispatch",
        "review_ambiguous_error",
        "stale_reconcile",
        "review_ambiguous_in_progress",
        "dispatch",
        "dispatch",
        "dispatch",
        "review_future_success",
        "dispatch_delayed_retry",
        "wait_delayed_retry",
        "skip_already_attempted_today",
        "dispatch_delayed_retry",
    ]

    recovery_payload = json.loads(json.dumps(payload))
    recovery_payload["allow_recovery_sweep"] = True
    recovery_payload["rows"] = [
        {
            "control_row": 21,
            "active": True,
            "status": "Error",
            "last_attempt_date": "03/08/2026",
            "error_class": "contract",
            "consecutive": 3,
            "recovery_pass_date": None,
        },
        {
            "control_row": 22,
            "active": True,
            "status": "Error",
            "last_attempt_date": "03/08/2026",
            "error_class": "cleanup",
            "consecutive": 1,
            "recovery_pass_date": "03/08/2026",
        },
        {
            "control_row": 23,
            "active": True,
            "status": "Error",
            "last_attempt_date": "03/08/2026",
            "error_class": "availability",
            "consecutive": 1,
            "recovery_pass_date": None,
        },
        {
            "control_row": 24,
            "active": True,
            "status": "Error",
            "last_attempt_date": "02/08/2026",
            "error_class": "infrastructure",
            "consecutive": 4,
            "recovery_pass_date": None,
        },
    ]
    recovery_actions = [
        item["action"] for item in decide(recovery_payload)["decisions"]
    ]
    assert recovery_actions == [
        "dispatch_recovery",
        "skip_already_attempted_today",
        "skip_already_attempted_today",
        "dispatch_recovery",
    ]
    print(json.dumps({"ok": True, "tests": 24}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.stdin:
        payload = json.load(sys.stdin)
    elif args.input:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        parser.error("provide --input or --stdin")
    print(json.dumps(decide(payload), ensure_ascii=True))


if __name__ == "__main__":
    main()
