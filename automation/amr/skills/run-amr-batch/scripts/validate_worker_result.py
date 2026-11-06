#!/usr/bin/env python3
"""Validate an AMR assignment/result pair before any spreadsheet write."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from amr_dates import calculate, parse_sheet_date


SCRIPT_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SCRIPT_DIR.parents[1]
WORKER_REFS = SKILLS_DIR / "run-amr-worker" / "references"
ASSIGNMENT_SCHEMA = WORKER_REFS / "worker-assignment.schema.json"
RESULT_SCHEMA = WORKER_REFS / "worker-result.schema.json"


def load_json(path: Path) -> Any:
    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(path.read_text(encoding="utf-8"), parse_constant=reject_constant)


def build_url(destination: str, departure_url: str, return_url: str) -> str:
    return (
        "https://www.aeromexico.com/bf/es-mx/reserva/opciones?"
        f"itinerary=MEX_{destination}_{departure_url}."
        f"{destination}_MEX_{return_url}"
        "&amrpoints=true&leg=1&travelers=A1_C0_I0_PH0_PC0"
    )


def schema_errors(instance: Any, schema_path: Path, label: str) -> list[str]:
    schema = load_json(schema_path)
    validator = Draft202012Validator(schema)
    errors = []
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
        location = ".".join(str(part) for part in error.path) or "$"
        errors.append(f"{label}.{location}: {error.message}")
    return errors


def validate_assignment(assignment: dict[str, Any]) -> list[str]:
    errors = schema_errors(assignment, ASSIGNMENT_SCHEMA, "assignment")
    if errors:
        return errors

    try:
        query_date = parse_sheet_date(assignment["query_date"])
        dates = calculate(query_date, assignment["months"], assignment["date_shift_days"])
    except ValueError as exc:
        return [f"assignment dates: {exc}"]
    expected_base_departure = dates["base_departure_date"] if assignment["date_shift_days"] else None
    expected_base_return = dates["base_return_date"] if assignment["date_shift_days"] else None

    expected_assignment = {
        "departure_date": dates["departure_date"],
        "return_date": dates["return_date"],
        "base_departure_date": expected_base_departure,
        "base_return_date": expected_base_return,
        "clean_url": build_url(
            assignment["destination"],
            str(dates["departure_url_date"]),
            str(dates["return_url_date"]),
        ),
    }
    for key, expected in expected_assignment.items():
        if assignment[key] != expected:
            errors.append(f"assignment.{key}: expected {expected!r}, got {assignment[key]!r}")

    expected_run_prefix = f"AMR-{query_date.strftime('%Y%m%d')}-"
    if not assignment["run_id"].startswith(expected_run_prefix):
        errors.append("assignment.run_id: date prefix must equal query_date")
    expected_lane = (
        f"AMR {assignment['run_id']} {assignment['order']} "
        f"{assignment['destination']}-{assignment['months']}m"
    )
    if assignment["browser_lane"] != expected_lane:
        errors.append(f"assignment.browser_lane: expected {expected_lane!r}")

    return errors


def validate_pair(assignment: dict[str, Any], result: dict[str, Any]) -> list[str]:
    errors = validate_assignment(assignment)
    errors.extend(schema_errors(result, RESULT_SCHEMA, "result"))
    if errors:
        return errors

    top_identity = ("run_id", "region", "browser_lane")
    for key in top_identity:
        if result[key] != assignment[key]:
            errors.append(f"result.{key}: does not match assignment")

    job_identity = (
        "control_row",
        "order",
        "destination",
        "months",
        "query_date",
        "departure_date",
        "return_date",
        "date_shift_days",
    )
    for key in job_identity:
        if result["job"][key] != assignment[key]:
            errors.append(f"result.job.{key}: does not match assignment")

    worker_status = result["worker_status"]
    job_status = result["job"]["status"]
    job_error = result["job"]["error"]

    if worker_status == "error" and result["worker_error"] != job_error:
        errors.append("worker_error and job.error must match for worker failures")
    if worker_status == "ok" and job_status == "error" and job_error != "No hay vuelos disponibles":
        errors.append("an operational worker may return only the exact availability error")
    if job_error == "No hay vuelos disponibles" and worker_status != "ok":
        errors.append("confirmed no availability must keep worker_status ok")
    if job_status == "partial":
        expected_missing = {
            "Main: No disponible": "main",
            "Premier: No disponible": "premier",
        }.get(job_error)
        if expected_missing is None:
            errors.append("partial results require the exact missing-cabin error")
        else:
            available = "premier" if expected_missing == "main" else "main"
            if result["job"][expected_missing] is not None:
                errors.append(f"partial result must set missing {expected_missing} to null")
            if result["job"][available] is None:
                errors.append(f"partial result must preserve available {available}")

    for cabin_name in ("main", "premier"):
        cabin = result["job"][cabin_name]
        if cabin is not None:
            for key in (
                "carrier_points",
                "award_taxes_mxn",
                "cash_carrier_mxn",
                "cash_taxes_mxn",
                "points_accrual",
            ):
                if not math.isfinite(cabin[key]):
                    errors.append(f"result.job.{cabin_name}.{key}: must be finite")

    return errors


def build_worker_prompt(assignment: dict[str, Any]) -> str:
    """Return one transport-safe prompt without raw non-ASCII identity text."""
    encoded = json.dumps(
        assignment,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return (
        "Use $run-amr-worker for exactly this assignment. Validate the assignment "
        "against worker-assignment.schema.json and return only the strict JSON result "
        "defined by worker-result.schema.json. Assignment JSON:\n"
        f"{encoded}"
    )


def emit(
    errors: list[str],
    assignment: dict[str, Any] | None = None,
    emit_worker_prompt: bool = False,
) -> int:
    payload: dict[str, Any] = {"valid": not errors, "errors": errors}
    if not errors and emit_worker_prompt:
        if assignment is None:
            raise ValueError("assignment is required to emit a worker prompt")
        payload["worker_prompt"] = build_worker_prompt(assignment)
    print(json.dumps(payload, ensure_ascii=True))
    return 1 if errors else 0


def valid_fixture() -> tuple[dict[str, Any], dict[str, Any]]:
    assignment = {
        "run_id": "AMR-20260803-123e4567-e89b-42d3-a456-426614174000",
        "control_row": 2,
        "order": 1,
        "region": "México",
        "destination": "MTY",
        "months": 1,
        "query_date": "03/08/2026",
        "departure_date": "03/09/2026",
        "return_date": "10/09/2026",
        "date_shift_days": 0,
        "base_departure_date": None,
        "base_return_date": None,
        "browser_lane": "AMR AMR-20260803-123e4567-e89b-42d3-a456-426614174000 1 MTY-1m",
        "clean_url": build_url("MTY", "2026-09-03", "2026-09-10"),
    }
    cabin = {
        "outbound_fare": "Clasica",
        "return_fare": "Clasica",
        "outbound_time": "09:00",
        "return_time": "12:00",
        "promotion": "No",
        "carrier_points": 100,
        "award_taxes_mxn": 200.5,
        "cash_carrier_mxn": 3000,
        "cash_taxes_mxn": 900,
        "points_accrual": 1200,
    }
    result = {
        "run_id": assignment["run_id"],
        "region": assignment["region"],
        "browser_lane": assignment["browser_lane"],
        "worker_status": "ok",
        "worker_error": None,
        "cleanup_status": "ok",
        "cleanup_error": None,
        "job": {
            "control_row": assignment["control_row"],
            "order": assignment["order"],
            "destination": assignment["destination"],
            "months": assignment["months"],
            "query_date": assignment["query_date"],
            "departure_date": assignment["departure_date"],
            "return_date": assignment["return_date"],
            "date_shift_days": assignment["date_shift_days"],
            "status": "ok",
            "error": None,
            "main": cabin.copy(),
            "premier": cabin.copy(),
        },
    }
    return assignment, result


def self_test() -> int:
    assignment, result = valid_fixture()
    assert validate_assignment(assignment) == []
    assert validate_pair(assignment, result) == []

    dynamic_region_assignment = json.loads(json.dumps(assignment))
    dynamic_region_result = json.loads(json.dumps(result))
    dynamic_region_assignment["region"] = "Sudamérica"
    dynamic_region_result["region"] = "Sudamérica"
    assert validate_assignment(dynamic_region_assignment) == []
    assert validate_pair(dynamic_region_assignment, dynamic_region_result) == []
    dynamic_region_prompt = build_worker_prompt(dynamic_region_assignment)
    assert dynamic_region_prompt.isascii()
    assert "Sudam\\u00e9rica" in dynamic_region_prompt

    unavailable = json.loads(json.dumps(result))
    unavailable["job"].update(
        status="error", error="No hay vuelos disponibles", main=None, premier=None
    )
    assert validate_pair(assignment, unavailable) == []

    main_only = json.loads(json.dumps(result))
    main_only["job"].update(
        status="partial", error="Premier: No disponible", premier=None
    )
    assert validate_pair(assignment, main_only) == []

    premier_only = json.loads(json.dumps(result))
    premier_only["job"].update(
        status="partial", error="Main: No disponible", main=None
    )
    assert validate_pair(assignment, premier_only) == []

    partial_cleanup = json.loads(json.dumps(main_only))
    partial_cleanup.update(
        cleanup_status="error",
        cleanup_error="Browser cleanup failed",
    )
    assert validate_pair(assignment, partial_cleanup) == []

    invalid_partial_pair = json.loads(json.dumps(result))
    invalid_partial_pair["job"].update(
        status="partial", error="Premier: No disponible"
    )
    assert validate_pair(assignment, invalid_partial_pair)

    invalid_partial_marker = json.loads(json.dumps(main_only))
    invalid_partial_marker["job"]["error"] = "Main: No disponible"
    assert validate_pair(assignment, invalid_partial_marker)

    malformed = json.loads(json.dumps(result))
    malformed["job"]["departure_date"] = "04/09/2026"
    assert validate_pair(assignment, malformed)

    invalid_calendar = json.loads(json.dumps(assignment))
    invalid_calendar["query_date"] = "31/02/2026"
    assert validate_assignment(invalid_calendar)
    assert validate_pair(invalid_calendar, result)

    cleanup = json.loads(json.dumps(result))
    cleanup.update(
        cleanup_status="error",
        cleanup_error="Browser cleanup failed",
    )
    assert validate_pair(assignment, cleanup) == []
    assert cleanup["worker_status"] == "ok"
    assert cleanup["job"]["status"] == "ok"
    assert cleanup["job"]["main"] is not None

    browsing_failure = json.loads(json.dumps(result))
    browsing_failure.update(
        worker_status="error",
        worker_error="Browser navigation failed",
    )
    browsing_failure["job"].update(
        status="error", error="Browser navigation failed", main=None, premier=None
    )
    assert validate_pair(assignment, browsing_failure) == []

    prompt = build_worker_prompt(assignment)
    assert prompt.isascii()
    assert "M\\u00e9xico" in prompt
    prompt_assignment = json.loads(prompt.split("Assignment JSON:\n", 1)[1])
    assert prompt_assignment == assignment

    shifted_assignment, shifted_result = valid_fixture()
    shifted_run_id = "AMR-20260831-123e4567-e89b-42d3-a456-426614174000"
    shifted_lane = f"AMR {shifted_run_id} 1 MTY-6m"
    shifted_assignment.update(
        run_id=shifted_run_id,
        months=6,
        query_date="31/08/2026",
        departure_date="01/03/2027",
        return_date="08/03/2027",
        date_shift_days=1,
        base_departure_date="28/02/2027",
        base_return_date="07/03/2027",
        browser_lane=shifted_lane,
        clean_url=build_url("MTY", "2027-03-01", "2027-03-08"),
    )
    shifted_result.update(run_id=shifted_run_id, browser_lane=shifted_lane)
    shifted_result["job"].update(
        months=6,
        query_date="31/08/2026",
        departure_date="01/03/2027",
        return_date="08/03/2027",
        date_shift_days=1,
    )
    assert validate_pair(shifted_assignment, shifted_result) == []
    print(json.dumps({"ok": True, "tests": 23}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assignment", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--stdin", action="store_true")
    parser.add_argument("--assignment-only", action="store_true")
    parser.add_argument("--emit-worker-prompt", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()
    if args.stdin:
        payload = json.load(sys.stdin)
        if args.assignment_only:
            assignment = payload.get("assignment", payload)
            return emit(
                validate_assignment(assignment),
                assignment=assignment,
                emit_worker_prompt=args.emit_worker_prompt,
            )
        return emit(validate_pair(payload["assignment"], payload["result"]))
    if args.assignment_only and args.assignment is not None:
        assignment = load_json(args.assignment)
        return emit(
            validate_assignment(assignment),
            assignment=assignment,
            emit_worker_prompt=args.emit_worker_prompt,
        )
    if args.emit_worker_prompt:
        parser.error("--emit-worker-prompt requires --assignment-only")
    if args.assignment is None or args.result is None:
        parser.error("provide --assignment and --result, or --stdin")
    return emit(validate_pair(load_json(args.assignment), load_json(args.result)))


if __name__ == "__main__":
    raise SystemExit(main())
