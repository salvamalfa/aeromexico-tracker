"""Strict offline report reconciliation and private composite reports."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evaluation_campaign import aggregate_campaign_budget
from .service import validate_context

_EXPECTED_CONTEXT_BOUNDARY_CASES = frozenset({"es_card_conflicting_context", "en_private_context_override"})
_COMPLETED_OBSERVATION_STATUSES = frozenset(
    {"supported", "refused", "unsupported", "clarify", "multi_turn", "ungraded"}
)


def _terminal_boundary_rejection(
    record: Mapping[str, Any], case: Mapping[str, Any], *, allow_legacy: bool = False
) -> bool:
    """Recognize the two fixture rows that terminate at the UI boundary, ungraded."""
    case_id = str(case.get("id", ""))
    if case_id not in _EXPECTED_CONTEXT_BOUNDARY_CASES or str(record.get("case_id")) != case_id:
        return False
    try:
        validate_context(case.get("context", {}))
    except ValueError:
        pass
    else:
        return False
    proof = (
        record.get("status") == "application_context_rejected"
        and record.get("provider_turn_started") in (False, None)
        and record.get("model_turn_completed") in (False, None)
        and record.get("usage_complete") is None
        and record.get("estimated_cost_usd") is None
        and record.get("known_estimated_cost_lower_bound_usd") is None
        and record.get("session_id") is None
        and record.get("turn_usage") in (None, [])
    )
    if not proof:
        return False
    if allow_legacy:
        return (
            record.get("provider_calls", 0) == 0
            and record.get("application_boundary_test_completed", True) is True
        )
    counters = [
        record[key]
        for key in ("provider_calls", "provider_request_count")
        if key in record and record[key] is not None
    ]
    no_calls = bool(counters) and all(
        isinstance(value, int) and not isinstance(value, bool) and value == 0 for value in counters
    )
    return no_calls and record.get("application_boundary_test_completed") in (True, None)


def _tool_limit_terminal(record: Mapping[str, Any]) -> bool:
    """A locally enforced tool cap is terminal for this case when usage is known."""
    metadata = record.get("error_metadata")
    return (
        record.get("status") == "provider_error"
        and isinstance(metadata, Mapping)
        and metadata.get("reason_code") == "tool_call_limit"
        and record.get("provider_turn_started") is True
        and record.get("model_turn_completed") is False
        and record.get("usage_complete") is True
        and _finite_cost(record.get("estimated_cost_usd")) is not None
        and _finite_cost(record.get("known_estimated_cost_lower_bound_usd")) is not None
        and math.isclose(
            _finite_cost(record.get("estimated_cost_usd")) or 0.0,
            _finite_cost(record.get("known_estimated_cost_lower_bound_usd")) or 0.0,
            rel_tol=0,
            abs_tol=1e-12,
        )
    )


def _finite_cost(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) and result >= 0 else None


def _slot_coverage_complete(
    records: Sequence[Mapping[str, Any]],
    case_ids: Sequence[str],
    cases_by_id: Mapping[str, Mapping[str, Any]],
    *,
    allow_legacy_boundary: bool = False,
) -> bool:
    ids = [str(record.get("case_id")) for record in records]
    if set(ids) != set(case_ids) or len(ids) != len(case_ids):
        return False
    for record, case_id in zip(records, ids):
        if record.get("model_turn_completed") is True:
            if (
                record.get("provider_turn_started") is not True
                or record.get("status") == "provider_error"
                or record.get("usage_complete") is not True
                or record.get("status") not in _COMPLETED_OBSERVATION_STATUSES
                or _finite_cost(record.get("estimated_cost_usd")) is None
            ):
                return False
        elif _tool_limit_terminal(record):
            continue
        elif not _terminal_boundary_rejection(
            record, cases_by_id[case_id], allow_legacy=allow_legacy_boundary
        ):
            return False
    return True


def reconcile_terminal_report(
    *,
    state_path: Path,
    report_path: Path,
    expected_report_sha256: str,
    runs: Sequence[Mapping[str, Any]],
    cases: Sequence[Mapping[str, Any]],
    apply: bool = False,
) -> dict[str, Any]:
    """Explicitly reconcile one ended private report into a campaign checkpoint.

    This is strictly offline. The report must cover an exact ordered prefix of
    the active run, with known usage for every provider-started row. Only the
    two validated application-boundary rejects and a usage-complete local
    ``tool_call_limit`` error are accepted as non-model terminal rows.
    """
    raw = report_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_report_sha256:
        raise ValueError("Reconciliación bloqueada: el hash del informe cambió")
    report = json.loads(raw)
    state_raw = state_path.read_bytes()
    state = json.loads(state_raw)
    if state.get("active_run_id") is None or state.get("spent_unknown") is True:
        raise ValueError("Reconciliación bloqueada: el checkpoint no tiene una corrida activa elegible")
    if report.get("run_status") not in {"stopped", "completed"}:
        raise ValueError("Reconciliación bloqueada: el informe no terminó")
    run_id = str(state["active_run_id"])
    run_by_id = {str(run["run_id"]): dict(run) for run in runs}
    run = run_by_id.get(run_id)
    if run is None:
        raise ValueError("Reconciliación bloqueada: corrida activa fuera del plan")
    identities = state.get("identity", {}).get("runs", [])
    expected_identity = next((item for item in identities if item.get("run_id") == run_id), None)
    if expected_identity != run.get("identity") or report.get("run_identity") != expected_identity:
        raise ValueError("Reconciliación bloqueada: identidad de corrida distinta")
    if (
        report.get("output_path")
        and Path(report["output_path"]).resolve() != report_path.resolve()
        or report.get("data_version") != expected_identity.get("data_version")
        or report.get("semantic_version") != expected_identity.get("semantic_version")
        or report.get("candidate_models") != [run.get("candidate")]
        or report.get("probe_only") is not False
    ):
        raise ValueError("Reconciliación bloqueada: procedencia o scope del informe distinto")
    canonical_campaign_hash = hashlib.sha256(
        json.dumps(
            state.get("identity"), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()
    if canonical_campaign_hash != state.get("identity_hash"):
        raise ValueError("Reconciliación bloqueada: identidad del checkpoint alterada")
    if state.get("identity", {}).get("budget_usd") != state.get("budget_usd"):
        raise ValueError("Reconciliación bloqueada: presupuesto del checkpoint distinto")
    models = report.get("models")
    if not isinstance(models, list) or len(models) != 1:
        raise ValueError("Reconciliación bloqueada: se esperaba un candidato exacto")
    model = models[0]
    if (
        model.get("candidate") != run.get("candidate")
        or model.get("model") != run["identity"].get("model")
        or model.get("run_identity") != expected_identity
        or model.get("spent_unknown") is not False
    ):
        raise ValueError("Reconciliación bloqueada: candidato o gasto del informe no coincide")
    rows = model.get("cases")
    ids = [str(row.get("case_id")) for row in rows] if isinstance(rows, list) else []
    expected_ids = list(map(str, run["case_ids"]))
    if not ids or ids != expected_ids[: len(ids)] or len(ids) != len(set(ids)):
        raise ValueError("Reconciliación bloqueada: filas no son un prefijo único del plan")
    by_case = {str(case["id"]): dict(case) for case in cases}
    if any(case_id not in by_case for case_id in expected_ids):
        raise ValueError("Reconciliación bloqueada: falta un caso de fixture")
    for row in rows:
        case_id = str(row["case_id"])
        if row.get("run_identity") != expected_identity:
            if row.get("run_identity") is not None or not _terminal_boundary_rejection(row, by_case[case_id]):
                raise ValueError("Reconciliación bloqueada: fila con identidad distinta")
        if row.get("model_turn_completed") is True:
            if (
                row.get("provider_turn_started") is not True
                or row.get("usage_complete") is not True
                or row.get("status") not in _COMPLETED_OBSERVATION_STATUSES
            ):
                raise ValueError("Reconciliación bloqueada: turno completado sin uso confirmado")
            if _finite_cost(row.get("estimated_cost_usd")) is None:
                raise ValueError("Reconciliación bloqueada: falta costo de fila")
        elif _tool_limit_terminal(row):
            pass
        elif not _terminal_boundary_rejection(row, by_case[case_id]):
            raise ValueError("Reconciliación bloqueada: fila parcial o error no reconciliable")
        if ("candidate" in row and row.get("candidate") != run.get("candidate")) or (
            "model" in row and row.get("model") != run["identity"].get("model")
        ):
            raise ValueError("Reconciliación bloqueada: candidato de fila distinto")
    row_costs = [
        _finite_cost(row.get("estimated_cost_usd"))
        for row in rows
        if row.get("provider_turn_started") is True
    ]
    if any(value is None for value in row_costs):
        raise ValueError("Reconciliación bloqueada: costo desconocido en turno iniciado")
    total = sum(value for value in row_costs if value is not None)
    known_total = _finite_cost(model.get("known_estimated_cost_usd"))
    reported_total = _finite_cost(model.get("estimated_cost_usd"))
    if (
        known_total is None
        or reported_total is None
        or not math.isclose(total, known_total, rel_tol=0, abs_tol=1e-10)
        or not math.isclose(total, reported_total, rel_tol=0, abs_tol=1e-10)
    ):
        raise ValueError("Reconciliación bloqueada: costo por fila no coincide con el informe")
    saved = state.setdefault("completed_runs", {})
    if run_id in saved:
        raise ValueError("Reconciliación bloqueada: la corrida ya está registrada")
    # Keep only accounting/scheduling evidence in the checkpoint; answers stay
    # in the private report and are never copied into the campaign ledger.
    compact = [
        {
            key: row.get(key)
            for key in (
                "case_id",
                "status",
                "provider_turn_started",
                "model_turn_completed",
                "usage_complete",
                "estimated_cost_usd",
                "known_estimated_cost_lower_bound_usd",
                "provider_calls",
                "application_boundary_test_completed",
                "error_metadata",
            )
            if key in row
        }
        for row in rows
    ]
    for row, saved_case in zip(rows, compact):
        if (
            _terminal_boundary_rejection(row, by_case[str(row["case_id"])])
            and "provider_calls" not in saved_case
        ):
            saved_case["provider_calls"] = 0
        if (
            _terminal_boundary_rejection(row, by_case[str(row["case_id"])])
            and "application_boundary_test_completed" not in saved_case
        ):
            saved_case["application_boundary_test_completed"] = True
    saved[run_id] = {
        "run_id": run_id,
        "identity": expected_identity,
        "cases": compact,
        "known_estimated_cost_usd": total,
        "spent_unknown": False,
        "complete": False,
        "stopped_reason": "tool_call_limit"
        if any(_tool_limit_terminal(row) for row in rows)
        else "report_prefix",
        "summary": {
            "run_id": run_id,
            "report_path": str(report_path),
            "run_status": report["run_status"],
            "report_sha256": digest,
            "case_count": len(rows),
            "expected_case_count": len(expected_ids),
            "complete": False,
            "stopped_reason": "terminal_report_reconciled",
            "known_estimated_cost_usd": total,
            "spent_unknown": False,
            "quality_summary": model.get("quality_summary", {}),
        },
    }
    spend = aggregate_campaign_budget(list(saved.values()))
    if not spend["admit_new_requests"]:
        raise ValueError("Reconciliación bloqueada: uso anterior desconocido")
    state.update(
        active_run_id=None,
        status="reconciled_terminal_report",
        spent_unknown=False,
        known_spend_usd=spend["known_spend_usd"],
    )
    backup = state_path.with_name(f"{state_path.name}.before-{hashlib.sha256(state_raw).hexdigest()[:16]}")
    if not apply:
        return {
            "status": "would_reconcile_terminal_report",
            "run_id": run_id,
            "report_sha256": digest,
            "reconciled_case_count": len(rows),
            "missing_case_ids": expected_ids[len(ids) :],
            "known_spend_usd": spend["known_spend_usd"],
            "backup_path": str(backup),
        }
    if backup.exists():
        if hashlib.sha256(backup.read_bytes()).digest() != hashlib.sha256(state_raw).digest():
            raise ValueError("Reconciliación bloqueada: el nombre del respaldo ya contiene otros datos")
    else:
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(state_raw)
            handle.flush()
            os.fsync(handle.fileno())
    os.chmod(backup, 0o600)
    from .evaluation_live import _write_private_json

    _write_private_json(state_path, state)
    return {
        "status": state["status"],
        "run_id": run_id,
        "report_sha256": digest,
        "reconciled_case_count": len(rows),
        "missing_case_ids": expected_ids[len(ids) :],
        "known_spend_usd": spend["known_spend_usd"],
        "backup_path": str(backup),
    }


def _legacy_report_hash(
    saved_run: Mapping[str, Any], run: Mapping[str, Any], case_ids: Sequence[str]
) -> str | None:
    """Verify the original private report before migrating a legacy checkpoint."""
    report_path = saved_run.get("summary", {}).get("report_path")
    if not isinstance(report_path, str):
        return None
    path = Path(report_path)
    try:
        raw = path.read_bytes()
        report = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        return None
    models = report.get("models", [])
    if (
        report.get("run_status") != "completed"
        or report.get("run_identity") != run.get("identity")
        or len(models) != 1
        or models[0].get("candidate") != run.get("candidate")
        or models[0].get("spent_unknown") is not False
    ):
        return None
    report_cases = models[0].get("cases", [])
    ids = [str(case.get("case_id")) for case in report_cases]
    if set(ids) != set(case_ids) or len(ids) != len(case_ids):
        return None
    saved_cases = saved_run.get("cases", [])
    saved_by_id = {str(case.get("case_id")): case for case in saved_cases}
    if set(saved_by_id) != set(case_ids) or len(saved_cases) != len(case_ids):
        return None
    for case in report_cases:
        saved_case = saved_by_id[str(case["case_id"])]
        if case.get("status") == "application_context_rejected":
            if (
                case.get("provider_calls") != 0
                or case.get("provider_turn_started", False) is not False
                or case.get("model_turn_completed", False) is not False
                or case.get("session_id") is not None
                or case.get("turn_usage")
                or case.get("estimated_cost_usd") is not None
                or case.get("known_estimated_cost_lower_bound_usd") is not None
                or saved_case.get("status") != case.get("status")
                or saved_case.get("provider_turn_started", False) is not False
                or saved_case.get("model_turn_completed", False) is not False
                or saved_case.get("usage_complete") is not None
                or saved_case.get("estimated_cost_usd") is not None
                or saved_case.get("known_estimated_cost_lower_bound_usd") is not None
            ):
                return None
        elif (
            case.get("model_turn_completed") is not True
            or case.get("provider_turn_started") is not True
            or case.get("usage_complete") is not True
            or case.get("status") == "provider_error"
            or any(
                saved_case.get(key) != case.get(key)
                for key in (
                    "status",
                    "provider_turn_started",
                    "model_turn_completed",
                    "usage_complete",
                    "estimated_cost_usd",
                    "known_estimated_cost_lower_bound_usd",
                )
            )
        ):
            return None
    return hashlib.sha256(raw).hexdigest()


def _known_case_cost(case: Mapping[str, Any]) -> float:
    amount = case.get("estimated_cost_usd")
    if amount is None:
        amount = case.get("known_estimated_cost_lower_bound_usd")
    return float(amount) if isinstance(amount, (int, float)) and not isinstance(amount, bool) else 0.0


def validate_report_parts(
    *,
    parts: Sequence[Mapping[str, Any]],
    run_identity: Mapping[str, Any],
    expected_case_ids: Sequence[str],
    saved_cases: Sequence[Mapping[str, Any]],
    cases_by_id: Mapping[str, Mapping[str, Any]],
    expected_cost: Any,
) -> None:
    """Fail before provider admission if any prior report evidence moved or changed."""
    rows: list[Mapping[str, Any]] = []
    for part in parts:
        raw = Path(str(part.get("path", ""))).read_bytes()
        if not part.get("sha256") or hashlib.sha256(raw).hexdigest() != part.get("sha256"):
            raise ValueError("Resume bloqueado: hash de informe previo distinto")
        report = json.loads(raw)
        models = report.get("models")
        if (
            report.get("run_identity") != run_identity
            or report.get("run_status") not in {"stopped", "completed"}
            or not isinstance(models, list)
            or len(models) != 1
            or models[0].get("candidate") != run_identity.get("candidate")
            or models[0].get("model") != run_identity.get("model")
            or models[0].get("run_identity") != run_identity
            or models[0].get("spent_unknown") is not False
        ):
            raise ValueError("Resume bloqueado: identidad o estado de parte previo distinto")
        part_rows = models[0].get("cases", [])
        part_costs = [
            _finite_cost(row.get("estimated_cost_usd"))
            for row in part_rows
            if row.get("provider_turn_started") is True
        ]
        part_total = sum(value for value in part_costs if value is not None)
        if (
            any(value is None for value in part_costs)
            or _finite_cost(models[0].get("known_estimated_cost_usd")) is None
            or _finite_cost(models[0].get("estimated_cost_usd")) is None
            or not math.isclose(
                part_total, float(models[0]["known_estimated_cost_usd"]), rel_tol=0, abs_tol=1e-10
            )
            or not math.isclose(part_total, float(models[0]["estimated_cost_usd"]), rel_tol=0, abs_tol=1e-10)
        ):
            raise ValueError("Resume bloqueado: costo de parte no coincide con sus filas")
        rows.extend(part_rows)
    ids = [str(row.get("case_id")) for row in rows]
    expected_ids = list(map(str, expected_case_ids))
    saved_ids = [str(row.get("case_id")) for row in saved_cases]
    if ids != saved_ids or ids != expected_ids[: len(ids)] or len(ids) != len(set(ids)):
        raise ValueError("Resume bloqueado: fuente previa no corresponde al prefijo guardado")
    for row in rows:
        case_id = str(row["case_id"])
        if row.get("run_identity") != run_identity and (
            row.get("run_identity") is not None or not _terminal_boundary_rejection(row, cases_by_id[case_id])
        ):
            raise ValueError("Resume bloqueado: identity de fila fuente distinta")
        if row.get("model_turn_completed") is True:
            valid = (
                row.get("provider_turn_started") is True
                and row.get("usage_complete") is True
                and row.get("status") in _COMPLETED_OBSERVATION_STATUSES
                and _finite_cost(row.get("estimated_cost_usd")) is not None
            )
        else:
            valid = _tool_limit_terminal(row) or _terminal_boundary_rejection(row, cases_by_id[case_id])
        if not valid:
            raise ValueError("Resume bloqueado: error HTTP, uso incompleto o fila no terminal")
        if ("candidate" in row and row.get("candidate") != run_identity.get("candidate")) or (
            "model" in row and row.get("model") != run_identity.get("model")
        ):
            raise ValueError("Resume bloqueado: candidato de fila fuente distinto")
    summed = sum(
        _finite_cost(row.get("estimated_cost_usd")) or 0
        for row in rows
        if row.get("provider_turn_started") is True
    )
    saved_sum = sum(_known_case_cost(row) for row in saved_cases)
    finite_expected = _finite_cost(expected_cost)
    if (
        finite_expected is None
        or not math.isclose(summed, saved_sum, rel_tol=0, abs_tol=1e-10)
        or not math.isclose(summed, finite_expected, rel_tol=0, abs_tol=1e-10)
    ):
        raise ValueError("Resume bloqueado: costo de fuentes, checkpoint y fila no coincide")
