"""Campaign-level budget and resume orchestration for F2.2 evaluations."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evaluation_campaign import aggregate_campaign_budget, validate_resume_identity
from .evaluation_live import _live_provider_run, _write_private_json
from .evaluation_live_composite import _merge_private_reports
from .evaluation_live_reconciliation import (
    _known_case_cost,
    _legacy_boundary_quality_proof,
    _legacy_report_hash,
    _slot_coverage_complete,
    _tool_limit_terminal,
    validate_report_parts,
)


def run_campaign(
    *,
    runs: Sequence[Mapping[str, Any]],
    cases: Sequence[Mapping[str, Any]],
    budget_usd: float,
    snapshot_root: Path,
    prices: Mapping[str, tuple[float, float]],
    expected_versions: Mapping[str, str],
    state_path: Path,
    output_dir: Path,
    resume: bool = False,
) -> dict[str, Any]:
    """Execute stable run slots under one shared hard campaign stop.

    A run is persisted as active before the provider boundary is entered. An
    interrupted active run cannot be replayed: its spend is unknown until
    reconciled. Successfully persisted run slots are skipped on an exact
    identity resume, so prompt variants and repetitions cannot collapse.
    """
    if (
        isinstance(budget_usd, bool)
        or not isinstance(budget_usd, (int, float))
        or not math.isfinite(budget_usd)
        or budget_usd <= 0
    ):
        raise ValueError("El presupuesto de campaña debe ser finito y positivo")
    if not runs:
        raise ValueError("La campaña requiere al menos una corrida")
    run_specs = [dict(run) for run in runs]
    identity = {
        "runs": [run.get("identity") for run in run_specs],
        "run_identity_hashes": [run.get("identity_hash") for run in run_specs],
        "budget_usd": float(budget_usd),
        "expected_versions": dict(expected_versions),
        "snapshot_root": str(snapshot_root),
        "prices": {key: list(value) for key, value in sorted(prices.items())},
    }
    identity_hash = hashlib.sha256(
        json.dumps(
            identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()
    if state_path.exists():
        if not resume:
            raise ValueError("La campaña ya tiene estado; usa resume con la misma identidad")
        saved = json.loads(state_path.read_text(encoding="utf-8"))
        validate_resume_identity(saved.get("identity", {}), identity)
        if saved.get("active_run_id"):
            saved["spent_unknown"] = True
            saved["status"] = "blocked_unknown_spend_after_interrupted_run"
            _write_private_json(state_path, saved)
            raise ValueError("Resume bloqueado: una corrida quedó interrumpida y su gasto es desconocido")
        state = saved
    else:
        if resume:
            raise ValueError("No existe estado de campaña que se pueda reanudar")
        state = {
            "identity": identity,
            "identity_hash": identity_hash,
            "status": "starting",
            "budget_usd": float(budget_usd),
            "known_spend_usd": 0.0,
            "spent_unknown": False,
            "active_run_id": None,
            "completed_runs": {},
        }
        _write_private_json(state_path, state)

    run_by_id = {run["run_id"]: run for run in run_specs}
    completed = state.setdefault("completed_runs", {})
    for run_id, saved_run in completed.items():
        if run_id not in run_by_id:
            raise ValueError("Resume bloqueado: estado contiene un run_id fuera del plan")
        validate_resume_identity(saved_run.get("identity", {}), run_by_id[run_id].get("identity", {}))
    by_case = {str(case["id"]): dict(case) for case in cases}
    # Migrate only complete legacy slots whose exact fixture coverage is fully
    # evidenced. This repairs the old boundary predicate without replaying calls.
    for run_id, saved_run in completed.items():
        run = run_by_id[run_id]
        summary = saved_run.get("summary", {})
        legacy_report_hash = _legacy_report_hash(saved_run, run, run["case_ids"])
        legacy_quality_proof = (
            _legacy_boundary_quality_proof(saved_run, run, run["case_ids"], legacy_report_hash)
            if legacy_report_hash is not None
            else None
        )
        migrated_cases = []
        for case in saved_run.get("cases", []):
            enriched = dict(case)
            proof = (legacy_quality_proof or {}).get(str(case.get("case_id")))
            if proof is not None:
                for key, value in proof.items():
                    enriched.setdefault(key, value)
            migrated_cases.append(enriched)
        if (
            not saved_run.get("complete")
            and summary.get("run_status") == "completed"
            and not saved_run.get("spent_unknown")
            and legacy_report_hash is not None
            and legacy_quality_proof is not None
            and _slot_coverage_complete(migrated_cases, run["case_ids"], by_case, allow_legacy_boundary=True)
        ):
            saved_run["cases"] = migrated_cases
            saved_run["complete"] = True
            saved_run["stopped_reason"] = None
            summary.update(
                complete=True,
                stopped_reason=None,
                boundary_migration_report_sha256=legacy_report_hash,
                boundary_migration_reason="verified_ungraded_application_boundary_cases",
            )
            _write_private_json(state_path, state)
    budget_rows = [saved_run for saved_run in completed.values()]
    spend = aggregate_campaign_budget(budget_rows)
    if not spend["admit_new_requests"] or state.get("spent_unknown"):
        raise ValueError("Campaña detenida: gasto anterior desconocido; no se reenvían solicitudes")
    reports = []
    for run in run_specs:
        run_id = str(run["run_id"])
        if run_id in completed:
            saved_run = completed[run_id]
            if saved_run.get("complete"):
                reports.append(saved_run["summary"])
                continue
            if saved_run.get("stopped_reason") == "provider_error":
                state["status"] = "stopped_provider_error"
                _write_private_json(state_path, state)
                break
            prior_case_ids = {str(case.get("case_id")) for case in saved_run.get("cases", [])}
            selected_ids = [case_id for case_id in run["case_ids"] if case_id not in prior_case_ids]
            if not selected_ids:
                state["status"] = "stopped_campaign_budget"
                _write_private_json(state_path, state)
                break
            prior_cases = list(saved_run.get("cases", []))
            prior_parts = list(saved_run.get("summary", {}).get("report_parts", []))
            if not prior_parts and saved_run.get("summary", {}).get("report_path"):
                prior_parts = [
                    {
                        "path": saved_run["summary"]["report_path"],
                        "sha256": saved_run["summary"].get("report_sha256"),
                    }
                ]
        else:
            selected_ids = list(run["case_ids"])
            prior_cases = []
            prior_parts = []
        remaining = budget_usd - float(spend["known_spend_usd"])
        if remaining <= 0:
            state.update(status="stopped_campaign_budget", known_spend_usd=spend["known_spend_usd"])
            _write_private_json(state_path, state)
            break
        if prior_cases:
            validate_report_parts(
                parts=prior_parts,
                run_identity=run["identity"],
                expected_case_ids=run["case_ids"],
                saved_cases=prior_cases,
                cases_by_id=by_case,
                expected_cost=completed[run_id].get("known_estimated_cost_usd"),
            )
        if any(output_dir.glob(f"{run_id}-composite-*.json")):
            raise ValueError("Resume bloqueado: ya existe un composite para esta corrida")
        selected = [by_case[case_id] for case_id in selected_ids]
        candidate = str(run["candidate"])
        if candidate not in prices:
            raise ValueError(f"Falta tarifa de catálogo para {candidate}")
        state.update(status="running", active_run_id=run_id, known_spend_usd=spend["known_spend_usd"])
        _write_private_json(state_path, state)
        report = _live_provider_run(
            cases=selected,
            models=[candidate],
            budget_usd=remaining,
            snapshot_root=snapshot_root,
            prices={candidate: prices[candidate]},
            probe_only=False,
            output_dir=output_dir / run_id,
            expected_versions=dict(expected_versions),
            system_instructions=str(run["prompt"]),
            run_identity=dict(run["identity"]),
            limits_override=dict(run["limits"]),
        )
        report_path = Path(report["output_path"])
        if not report_path.exists():
            # Offline stubs and alternate runners may return an in-memory
            # report; persist it privately so resumed accounting has evidence.
            report_path = output_dir / f"{run_id}-part-{len(prior_parts) + 1}.json"
            if report_path.exists():
                raise ValueError("Informe bloqueado: destino de parte ya existe")
            _write_private_json(report_path, report)
            report["output_path"] = str(report_path)
        model = report["models"][0]
        new_cases = []
        for case in model["cases"]:
            saved_case = {
                "case_id": case.get("case_id", "unknown"),
                "provider_turn_started": case.get("provider_turn_started", False),
                "usage_complete": case.get("usage_complete"),
                "estimated_cost_usd": case.get("estimated_cost_usd"),
                "known_estimated_cost_lower_bound_usd": case.get("known_estimated_cost_lower_bound_usd"),
                "status": case.get("status"),
                "model_turn_completed": case.get("model_turn_completed", False),
                "application_boundary_test_completed": case.get("application_boundary_test_completed", False),
            }
            if "error_metadata" in case:
                saved_case["error_metadata"] = case["error_metadata"]
            if "provider_calls" in case:
                saved_case["provider_calls"] = case["provider_calls"]
            if "quality" in case:
                saved_case["quality"] = case["quality"]
            new_cases.append(saved_case)
        all_cases = prior_cases + new_cases
        coverage_complete = _slot_coverage_complete(all_cases, run["case_ids"], by_case)
        complete = (
            coverage_complete
            and report.get("run_status") == "completed"
            and not model.get("stopped_reason")
            and not model.get("spent_unknown")
        )
        report_digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
        current_parts = prior_parts + [{"path": report["output_path"], "sha256": report_digest}]
        composite_path = None
        composite_digest = None
        if coverage_complete:
            for part in current_parts:
                if (
                    not part.get("sha256")
                    or hashlib.sha256(Path(part["path"]).read_bytes()).hexdigest() != part["sha256"]
                ):
                    raise ValueError("Composite bloqueado: el hash de un informe fuente no coincide")
            source_set_hash = hashlib.sha256(
                "|".join(part["sha256"] for part in current_parts).encode("ascii")
            ).hexdigest()[:16]
            composite_path = output_dir / f"{run_id}-composite-{source_set_hash}.json"
            if composite_path.exists():
                raise ValueError("Composite bloqueado: destino de informe ya existe")
            composite_digest, _ = _merge_private_reports(
                report_paths=[part["path"] for part in current_parts],
                expected_identity=run["identity"],
                expected_case_ids=run["case_ids"],
                cases=[by_case[case_id] for case_id in run["case_ids"]],
                output_path=composite_path,
            )
        nonlocal_provider_error = any(
            case.get("status") in {"provider_error", "error", "failed"} and not _tool_limit_terminal(case)
            for case in all_cases
        )
        controlled_error_count = sum(_tool_limit_terminal(case) for case in all_cases)
        stopped_reason = (
            "provider_error"
            if nonlocal_provider_error
            else "stopped_controlled_case_failure"
            if controlled_error_count and not complete
            else "campaign_budget"
            if not complete
            else None
        )
        completed_run = {
            "run_id": run_id,
            "identity": run["identity"],
            "known_estimated_cost_usd": sum(_known_case_cost(case) for case in all_cases),
            "spent_unknown": model["spent_unknown"],
            "cases": all_cases,
            "complete": complete,
            "stopped_reason": stopped_reason,
            "summary": {
                "run_id": run_id,
                "report_path": str(composite_path) if composite_path else report["output_path"],
                "report_sha256": composite_digest or report_digest,
                "report_parts": current_parts,
                "run_status": "completed" if complete else report["run_status"],
                "case_count": len(all_cases),
                "expected_case_count": len(run["case_ids"]),
                "complete": complete,
                "stopped_reason": stopped_reason,
                "terminal_case_failure_count": controlled_error_count,
                "terminal_case_failure_reason": "tool_call_limit" if controlled_error_count else None,
                "known_estimated_cost_usd": sum(_known_case_cost(case) for case in all_cases),
                "spent_unknown": model["spent_unknown"],
                "quality_summary": model["quality_summary"],
            },
        }
        completed[run_id] = completed_run
        state["active_run_id"] = None
        state["spent_unknown"] = bool(model["spent_unknown"])
        spend = aggregate_campaign_budget(list(completed.values()))
        state["known_spend_usd"] = spend["known_spend_usd"]
        state["status"] = (
            "stopped_unknown_spend"
            if model["spent_unknown"]
            else "running"
            if complete
            else "stopped_provider_error"
            if stopped_reason == "provider_error"
            else "stopped_controlled_case_failure"
            if stopped_reason == "stopped_controlled_case_failure"
            else "stopped_campaign_budget"
        )
        _write_private_json(state_path, state)
        reports.append(completed_run["summary"])
        if not spend["admit_new_requests"] or not complete:
            break
    all_runs_complete = all(
        str(run["run_id"]) in completed and completed[str(run["run_id"])].get("complete") for run in run_specs
    )
    state["status"] = (
        state.get("status")
        if state.get("spent_unknown")
        else "completed"
        if all_runs_complete
        else "stopped_provider_error"
        if state.get("status") == "stopped_provider_error"
        else "stopped_controlled_case_failure"
        if state.get("status") == "stopped_controlled_case_failure"
        else "stopped_campaign_budget"
    )
    state["active_run_id"] = None
    state["known_spend_usd"] = spend["known_spend_usd"]
    _write_private_json(state_path, state)
    return {
        "mode": "live-campaign",
        "identity_hash": identity_hash,
        "status": state["status"],
        "budget_usd_operational_stop": budget_usd,
        "budget_guaranteed": False,
        **spend,
        "run_summaries": reports,
        "state_path": str(state_path),
        "note": (
            "Un turno iniciado puede exceder la reserva; gasto desconocido detiene la campaña "
            "y bloquea replay."
        ),
    }
