"""Offline recovery for a single proven provider-unstarted case."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evaluation_campaign import aggregate_campaign_budget
from .evaluation_live_reconciliation import _finite_cost, validate_report_parts

_PENDING_AFTER_N25 = ["N25", "N26", "N27", "N28", "N30"]
_ZERO_OR_ABSENT_COUNTERS = ("provider_calls", "provider_request_count", "turn_count", "tool_call_count")
_NO_SIDE_EFFECT_FIELDS = (
    "session_id",
    "tool_calls",
    "turn_usage",
    "events",
    "event_ids",
    "event_id",
    "request_id",
    "response_id",
    "provider_request_id",
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_identity_hash(identity: Mapping[str, Any]) -> str:
    return _sha256(
        json.dumps(
            identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    )


def _is_empty(value: Any) -> bool:
    return value is None or value is False or value == [] or value == {}


def _verify_zero_token_totals(totals: Any) -> None:
    if not isinstance(totals, Mapping):
        raise ValueError("Rearme bloqueado: faltan totales de uso del intento")
    for key in (
        "input_tokens",
        "output_tokens",
        "known_input_tokens_lower_bound",
        "known_output_tokens_lower_bound",
        "usage_complete_case_count",
        "turn_count",
    ):
        value = totals.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value != 0:
            raise ValueError("Rearme bloqueado: el intento acumula tokens o turnos")
    if (
        totals.get("cached_tokens") != "unknown"
        or totals.get("reasoning_tokens") != "unknown; included in output_tokens"
    ):
        raise ValueError("Rearme bloqueado: el desglose de tokens no es el de un intento sin uso")


def _verify_unstarted_failure(row: Mapping[str, Any], run_identity: Mapping[str, Any]) -> None:
    if (
        row.get("case_id") != "N25"
        or row.get("status") != "provider_error"
        or row.get("provider_turn_started") is not False
        or row.get("model_turn_completed") is not False
        or row.get("usage_complete") is not False
        or row.get("estimated_cost_usd") is not None
        or _finite_cost(row.get("known_estimated_cost_lower_bound_usd")) != 0
        or row.get("run_identity") != run_identity
        or row.get("candidate") != run_identity.get("candidate")
        or row.get("model") != run_identity.get("model")
    ):
        raise ValueError("Rearme bloqueado: el caso no prueba un fallo anterior al inicio del proveedor")
    counters = [row[key] for key in _ZERO_OR_ABSENT_COUNTERS if key in row]
    if any(
        value is not None and (not isinstance(value, int) or isinstance(value, bool) or value != 0)
        for value in counters
    ):
        raise ValueError("Rearme bloqueado: hay un contador de solicitudes positivo o inválido")
    if any(not _is_empty(row.get(key)) for key in _NO_SIDE_EFFECT_FIELDS):
        raise ValueError("Rearme bloqueado: hay sesión, herramientas o eventos de proveedor")
    for key in ("input_tokens", "output_tokens", "cached_tokens", "reasoning_tokens"):
        value = row.get(key)
        if key == "cached_tokens" and value == "unknown":
            continue
        if key == "reasoning_tokens" and value == "unknown; included in output_tokens":
            continue
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value != 0):
            raise ValueError("Rearme bloqueado: el fallo contiene uso de tokens")
    totals = row.get("token_totals")
    if totals is not None:
        _verify_zero_token_totals(totals)
    if row.get("provider_cancel") not in (None, False, "not_available") or row.get(
        "post_cancel_usage_reconciliation"
    ) not in (None, False, "not_attempted"):
        raise ValueError("Rearme bloqueado: el fallo contiene actividad de cancelación o conciliación")
    quality = row.get("quality")
    metadata = row.get("error_metadata")
    if (
        not isinstance(quality, Mapping)
        or quality.get("scored") is not False
        or quality.get("not_scored_reason") != "provider_error"
        or not isinstance(metadata, Mapping)
        or dict(metadata) != {"exception_types": ["OpenAIProviderError"]}
    ):
        raise ValueError("Rearme bloqueado: el error no coincide con el fallo local de arranque conocido")
    if any(key in row for key in ("response", "answer", "http_status", "request_id")):
        raise ValueError("Rearme bloqueado: la fila contiene respuesta o evidencia HTTP")


def rearm_unstarted_case(
    *,
    state_path: Path,
    failed_report_path: Path,
    expected_state_sha256: str,
    expected_report_sha256: str,
    runs: Sequence[Mapping[str, Any]],
    cases: Sequence[Mapping[str, Any]],
    apply: bool = False,
) -> dict[str, Any]:
    """Archive one zero-start N25 attempt and restore the five-case missing prefix.

    This function never calls a provider. All evidence, source parts, campaign
    identity, and known-cost arithmetic are verified before any optional write.
    """
    state_raw = state_path.read_bytes()
    state_sha = _sha256(state_raw)
    if state_sha != expected_state_sha256:
        raise ValueError("Rearme bloqueado: el hash del checkpoint cambió")
    report_raw = failed_report_path.read_bytes()
    report_sha = _sha256(report_raw)
    if report_sha != expected_report_sha256:
        raise ValueError("Rearme bloqueado: el hash del intento fallido cambió")
    state = json.loads(state_raw)
    report = json.loads(report_raw)
    if (
        state.get("active_run_id") is not None
        or state.get("spent_unknown") is not False
        or state.get("status") != "stopped_provider_error"
        or state.get("budget_usd") != 3.0
        or state.get("identity", {}).get("budget_usd") != 3.0
        or state.get("identity", {}).get("budget_usd") != state.get("budget_usd")
        or state.get("identity_hash") != _canonical_identity_hash(state.get("identity", {}))
        or _finite_cost(state.get("known_spend_usd")) is None
    ):
        raise ValueError("Rearme bloqueado: checkpoint activo, alterado o con gasto desconocido")
    if stat.S_IMODE(state_path.stat().st_mode) & 0o077:
        raise ValueError("Rearme bloqueado: checkpoint no es privado")
    if stat.S_IMODE(failed_report_path.stat().st_mode) & 0o077:
        raise ValueError("Rearme bloqueado: informe fallido no es privado")

    report_identity = report.get("run_identity")
    run_id = str(report_identity.get("run_id", "")) if isinstance(report_identity, Mapping) else ""
    run_by_id = {str(run.get("run_id")): dict(run) for run in runs}
    run = run_by_id.get(run_id)
    if run is None or run.get("identity") != report_identity:
        raise ValueError("Rearme bloqueado: la corrida no coincide con el plan reconstruido")
    expected_run_identity = run.get("identity", {})
    state_run_identities = state.get("identity", {}).get("runs", [])
    if report_identity not in state_run_identities or report_identity.get("stage") != 1:
        raise ValueError("Rearme bloqueado: identidad no aprobada para stage 1")
    if (
        report.get("run_status") != "stopped"
        or report.get("output_path")
        and Path(report["output_path"]).resolve() != failed_report_path.resolve()
        or report.get("candidate_models") != [run.get("candidate")]
        or report.get("data_version") != expected_run_identity.get("data_version")
        or report.get("semantic_version") != expected_run_identity.get("semantic_version")
        or report.get("probe_only") is not False
    ):
        raise ValueError("Rearme bloqueado: procedencia o modo del informe fallido distinto")
    if (
        expected_run_identity.get("candidate") != "gpt-6-luna@medium"
        or expected_run_identity.get("prompt_variant") != "current"
        or expected_run_identity.get("model") != "gpt-6-luna"
        or expected_run_identity.get("text_verbosity") != "medium"
        or expected_run_identity.get("limits", {}).get("max_tool_calls") != 16
    ):
        raise ValueError("Rearme bloqueado: configuración fuera del slot Luna aprobado")
    expected_ids = list(map(str, run.get("case_ids", [])))
    if len(expected_ids) != 58 or expected_ids[53:] != _PENDING_AFTER_N25:
        raise ValueError("Rearme bloqueado: la cobertura pendiente no coincide con los cinco casos fijados")

    slot = state.get("completed_runs", {}).get(run_id)
    if not isinstance(slot, dict) or slot.get("complete") is True or slot.get("spent_unknown") is not False:
        raise ValueError("Rearme bloqueado: el slot actual no es recuperable")
    summary = slot.get("summary", {})
    if (
        slot.get("stopped_reason") != "provider_error"
        or summary.get("run_status") != "stopped"
        or summary.get("stopped_reason") != "provider_error"
        or slot.get("archived_unstarted_attempts")
    ):
        raise ValueError("Rearme bloqueado: el slot no terminó por un único error recuperable")
    parts = summary.get("report_parts")
    cases_saved = slot.get("cases")
    if not isinstance(parts, list) or len(parts) != 2 or not isinstance(cases_saved, list):
        raise ValueError("Rearme bloqueado: no hay exactamente un reporte base y un intento nuevo")
    first_part, failed_part = parts
    if (
        not isinstance(first_part, Mapping)
        or not isinstance(failed_part, Mapping)
        or Path(str(failed_part.get("path", ""))).resolve() != failed_report_path.resolve()
        or failed_part.get("sha256") != report_sha
        or summary.get("report_path") != str(failed_report_path)
        or summary.get("report_sha256") != report_sha
    ):
        raise ValueError("Rearme bloqueado: partes o hash del intento no coinciden con el checkpoint")

    first_raw = Path(str(first_part.get("path", ""))).read_bytes()
    if not first_part.get("sha256") or _sha256(first_raw) != first_part["sha256"]:
        raise ValueError("Rearme bloqueado: el reporte fuente de 53 casos cambió")
    first_report = json.loads(first_raw)
    models = report.get("models")
    if (
        not isinstance(models, list)
        or len(models) != 1
        or models[0].get("candidate") != run.get("candidate")
        or models[0].get("model") != expected_run_identity.get("model")
        or models[0].get("run_identity") != expected_run_identity
        or models[0].get("spent_unknown") is not False
        or _finite_cost(models[0].get("estimated_cost_usd")) != 0
        or _finite_cost(models[0].get("known_estimated_cost_usd")) != 0
        or models[0].get("stopped_reason") != "provider_error_or_usage_unknown; no further cases admitted"
    ):
        raise ValueError("Rearme bloqueado: el modelo del intento no demuestra gasto cero")
    _verify_zero_token_totals(models[0].get("token_totals"))
    failed_rows = models[0].get("cases")
    if not isinstance(failed_rows, list) or len(failed_rows) != 1:
        raise ValueError("Rearme bloqueado: el intento fallido no contiene exactamente una fila")
    failed_row = failed_rows[0]
    _verify_unstarted_failure(failed_row, expected_run_identity)
    if (
        _finite_cost(report.get("estimated_cost_usd")) != 0
        or _finite_cost(report.get("known_estimated_cost_usd")) != 0
    ):
        raise ValueError("Rearme bloqueado: el total del intento fallido no es cero")

    saved_ids = [str(row.get("case_id")) for row in cases_saved]
    if saved_ids != expected_ids[:53] + ["N25"]:
        raise ValueError("Rearme bloqueado: checkpoint no es exactamente 53 filas más N25")
    if failed_row.get("case_id") != expected_ids[53]:
        raise ValueError("Rearme bloqueado: el intento no corresponde al siguiente caso pendiente")
    saved_failed = cases_saved[-1]
    for key in (
        "case_id",
        "status",
        "provider_turn_started",
        "model_turn_completed",
        "usage_complete",
        "estimated_cost_usd",
        "known_estimated_cost_lower_bound_usd",
        "provider_calls",
        "quality",
        "error_metadata",
    ):
        if key in saved_failed and saved_failed.get(key) != failed_row.get(key):
            raise ValueError("Rearme bloqueado: fila compacta y reporte fallido difieren")
    known_slot_cost = _finite_cost(slot.get("known_estimated_cost_usd"))
    summary_slot_cost = _finite_cost(summary.get("known_estimated_cost_usd"))
    if (
        known_slot_cost is None
        or summary_slot_cost is None
        or not math.isclose(known_slot_cost, summary_slot_cost, rel_tol=0, abs_tol=1e-12)
    ):
        raise ValueError("Rearme bloqueado: costo previo no es finito y conocido")
    prior_cases = cases_saved[:53]
    by_case = {str(case.get("id")): dict(case) for case in cases}
    if any(case_id not in by_case for case_id in expected_ids):
        raise ValueError("Rearme bloqueado: el fixture no contiene todos los casos esperados")
    validate_report_parts(
        parts=[first_part],
        run_identity=expected_run_identity,
        expected_case_ids=expected_ids,
        saved_cases=prior_cases,
        cases_by_id=by_case,
        expected_cost=known_slot_cost,
    )
    first_models = first_report.get("models")
    if (
        first_report.get("run_identity") != expected_run_identity
        or not isinstance(first_models, list)
        or len(first_models) != 1
        or not math.isclose(
            _finite_cost(first_models[0].get("known_estimated_cost_usd")) or -1,
            known_slot_cost,
            rel_tol=0,
            abs_tol=1e-10,
        )
        or not math.isclose(
            _finite_cost(first_models[0].get("estimated_cost_usd")) or -1,
            known_slot_cost,
            rel_tol=0,
            abs_tol=1e-10,
        )
    ):
        raise ValueError("Rearme bloqueado: costo o identidad de las 53 filas fuente distinto")
    first_rows = first_models[0].get("cases", [])
    if [str(row.get("case_id")) for row in first_rows] != expected_ids[:53]:
        raise ValueError("Rearme bloqueado: reporte fuente no cubre el prefijo exacto de 53 casos")
    if not math.isclose(
        _finite_cost(first_report.get("estimated_cost_usd")) or -1,
        known_slot_cost,
        rel_tol=0,
        abs_tol=1e-10,
    ) or not math.isclose(
        _finite_cost(first_report.get("known_estimated_cost_usd")) or -1,
        known_slot_cost,
        rel_tol=0,
        abs_tol=1e-10,
    ):
        raise ValueError("Rearme bloqueado: costo total de la parte fuente no coincide")
    projection_keys = (
        "case_id",
        "status",
        "provider_turn_started",
        "model_turn_completed",
        "usage_complete",
        "estimated_cost_usd",
        "known_estimated_cost_lower_bound_usd",
        "application_boundary_test_completed",
        "quality",
        "error_metadata",
        "provider_calls",
    )
    for source_row, saved_row in zip(first_rows, prior_cases):
        for key in projection_keys:
            if key == "application_boundary_test_completed":
                continue
            if key in source_row or key in saved_row:
                if source_row.get(key) != saved_row.get(key):
                    raise ValueError("Rearme bloqueado: fila compacta de origen difiere del reporte hasheado")
        if "application_boundary_test_completed" in saved_row:
            source_boundary_flag = source_row.get("application_boundary_test_completed")
            allowed_reconciled_boundary_flag = (
                source_row.get("status") == "application_context_rejected"
                and source_boundary_flag is None
                and saved_row.get("application_boundary_test_completed") is True
            )
            if (
                not allowed_reconciled_boundary_flag
                and saved_row.get("application_boundary_test_completed") != source_boundary_flag
            ):
                raise ValueError("Rearme bloqueado: prueba de frontera compacta difiere del reporte")
    spend = aggregate_campaign_budget(list(state.get("completed_runs", {}).values()))
    if not spend.get("admit_new_requests") or not math.isclose(
        float(spend["known_spend_usd"]), float(state["known_spend_usd"]), rel_tol=0, abs_tol=1e-10
    ):
        raise ValueError("Rearme bloqueado: presupuesto acumulado no se reconcilia")

    backup = state_path.with_name(f"{state_path.name}.before-unstarted-rearm-{state_sha[:16]}")
    if backup.exists():
        raise ValueError("Rearme bloqueado: ya existe un respaldo con esta identidad")
    updated = json.loads(state_raw)
    updated_slot = updated["completed_runs"][run_id]
    updated_slot["cases"] = prior_cases
    updated_slot["known_estimated_cost_usd"] = known_slot_cost
    updated_slot["stopped_reason"] = None
    updated_slot["archived_unstarted_attempts"] = [
        {
            "case_id": "N25",
            "attempt_report_path": str(failed_report_path),
            "attempt_report_sha256": report_sha,
            "reason": "provider_not_started_local_sdk_startup_failure",
            "provider_turn_started": False,
            "usage_complete": False,
            "known_cost_usd": 0.0,
        }
    ]
    updated_summary = updated_slot["summary"]
    updated_summary.update(
        report_path=str(first_part["path"]),
        report_sha256=first_part["sha256"],
        report_parts=[dict(first_part)],
        case_count=53,
        stopped_reason="rearmed_unstarted_case",
        known_estimated_cost_usd=known_slot_cost,
        terminal_case_failure_count=0,
        terminal_case_failure_reason=None,
    )
    updated["status"] = "rearmed_unstarted_case"
    updated["active_run_id"] = None
    updated["spent_unknown"] = False
    updated["known_spend_usd"] = spend["known_spend_usd"]
    history = updated.setdefault("unstarted_case_rearm_history", [])
    if not isinstance(history, list):
        raise ValueError("Rearme bloqueado: historial de recovery inválido")
    history.append(
        {
            "run_id": run_id,
            "case_id": "N25",
            "attempt_report_sha256": report_sha,
            "source_checkpoint_sha256": state_sha,
            "checkpoint_backup_path": str(backup),
            "source_part_sha256": first_part["sha256"],
            "known_spend_usd_unchanged": spend["known_spend_usd"],
        }
    )
    if not apply:
        return {
            "status": "would_rearm_unstarted_case",
            "run_id": run_id,
            "case_id": "N25",
            "failed_report_sha256": report_sha,
            "source_checkpoint_sha256": state_sha,
            "restored_source_case_count": 53,
            "remaining_case_ids": _PENDING_AFTER_N25,
            "known_spend_usd": spend["known_spend_usd"],
            "backup_path": str(backup),
        }

    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(state_raw)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(backup, 0o600)
    from .evaluation_live import _write_private_json

    _write_private_json(state_path, updated)
    return {
        "status": updated["status"],
        "run_id": run_id,
        "case_id": "N25",
        "failed_report_sha256": report_sha,
        "source_checkpoint_sha256": state_sha,
        "restored_source_case_count": 53,
        "remaining_case_ids": _PENDING_AFTER_N25,
        "known_spend_usd": spend["known_spend_usd"],
        "backup_path": str(backup),
        "updated_checkpoint_sha256": _sha256(state_path.read_bytes()),
    }
