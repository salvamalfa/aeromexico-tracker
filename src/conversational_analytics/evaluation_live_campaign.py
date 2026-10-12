"""Campaign-level budget and resume orchestration for F2.2 evaluations."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

from .evaluation_campaign import aggregate_campaign_budget, validate_resume_identity
from .evaluation_live import _live_provider_run, _write_private_json
from .evaluation_live_campaign_reports import (
    _consolidate_report,
    _fragment_record,
    _load_fragment_cases,
    _private_fragment_path,
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
    reservation_assumption_override: Mapping[str, Any] | None = None,
    continue_after_known_provider_errors: bool = False,
    runtime_config: Any | None = None,
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
    if reservation_assumption_override is not None:
        expected_slots = reservation_assumption_override.get("planned_request_count")
        case_by_id = {str(case["id"]): case for case in cases}
        actual_messages = sum(
            len(case_by_id[case_id].get("turns", [case_by_id[case_id].get("question")]))
            for run in run_specs
            for case_id in run.get("case_ids", [])
        )
        if expected_slots != actual_messages:
            raise ValueError("La reserva empírica no coincide con el total de turnos planificados")
        for field in ("input_tokens_per_turn", "output_tokens_per_turn", "planned_request_count"):
            value = reservation_assumption_override.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("La reserva empírica contiene límites inválidos")
        batch_reservation = reservation_assumption_override.get("planned_batch_estimated_reservation_usd")
        if (
            isinstance(batch_reservation, bool)
            or not isinstance(batch_reservation, (int, float))
            or not math.isfinite(batch_reservation)
            or batch_reservation <= 0
        ):
            raise ValueError("La reserva empírica contiene una proyección inválida")
        if reservation_assumption_override.get("basis") == "f2_9_stage3_projected_usage_not_hard_cap":
            if (
                len(run_specs) != 1
                or len(set(case_id for run in run_specs for case_id in run.get("case_ids", []))) != 30
                or actual_messages != 34
                or run_specs[0].get("candidate") != "gpt-6.1-sol@low"
                or run_specs[0].get("identity", {}).get("coverage_campaign_sha256")
                != reservation_assumption_override.get("campaign_sha256")
                or batch_reservation > budget_usd
            ):
                raise ValueError("La reserva stage3 no coincide con el plan fijado de 30 casos/34 mensajes")
    identity = {
        "runs": [run.get("identity") for run in run_specs],
        "run_identity_hashes": [run.get("identity_hash") for run in run_specs],
        "budget_usd": float(budget_usd),
        "expected_versions": dict(expected_versions),
        "snapshot_root": str(snapshot_root),
        "prices": {key: list(value) for key, value in sorted(prices.items())},
        "reservation_assumption_override": dict(reservation_assumption_override)
        if reservation_assumption_override is not None
        else None,
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
        saved_spec = run_by_id[run_id]
        validate_resume_identity(saved_run.get("identity", {}), saved_spec.get("identity", {}))
        fragments = saved_run.get("report_fragments", [])
        if fragments:
            prior_detail = _load_fragment_cases(
                fragments,
                run_dir=output_dir / run_id,
                run=saved_spec,
                campaign_identity_hash=identity_hash,
            )
            accounting_ids = [str(case.get("case_id")) for case in saved_run.get("cases", [])]
            detail_ids = [str(case.get("case_id")) for case in prior_detail]
            if detail_ids != accounting_ids:
                raise ValueError(
                    "Resume bloqueado: filas detalladas no coinciden con el accounting acumulado"
                )
            summary = saved_run.get("summary", {})
            summary_path = Path(str(summary.get("report_path", "")))
            summary_sha = summary.get("report_sha256")
            if summary_sha:
                consolidated_path, consolidated_sha = _private_fragment_path(
                    summary_path, output_dir / run_id
                )
                if consolidated_sha != summary_sha:
                    raise ValueError("Resume bloqueado: cambió el hash del reporte consolidado")
    budget_rows = [saved_run for saved_run in completed.values()]
    spend = aggregate_campaign_budget(budget_rows)
    if not spend["admit_new_requests"] or state.get("spent_unknown"):
        raise ValueError("Campaña detenida: gasto anterior desconocido; no se reenvían solicitudes")
    reports = []
    by_case = {str(case["id"]): dict(case) for case in cases}
    for run in run_specs:
        run_id = str(run["run_id"])
        run_dir = output_dir / run_id
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
            prior_fragments = list(saved_run.get("report_fragments", []))
        else:
            selected_ids = list(run["case_ids"])
            prior_cases = []
            prior_fragments = []
        prior_detailed_cases = _load_fragment_cases(
            prior_fragments,
            run_dir=run_dir,
            run=run,
            campaign_identity_hash=identity_hash,
        ) if prior_fragments else []
        if prior_detailed_cases and [row["case_id"] for row in prior_detailed_cases] != [
            row["case_id"] for row in prior_cases
        ]:
            raise ValueError("Resume bloqueado: detailed cases no coinciden con accounting previo")
        remaining = budget_usd - float(spend["known_spend_usd"])
        if remaining <= 0:
            state.update(status="stopped_campaign_budget", known_spend_usd=spend["known_spend_usd"])
            _write_private_json(state_path, state)
            break
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
            run_identity_hash=str(run["identity_hash"]),
            campaign_identity_hash=identity_hash,
            limits_override=dict(run["limits"]),
            text_verbosity_override=str(run["text_verbosity"]),
            reservation_assumption_override=(
                dict(reservation_assumption_override) if reservation_assumption_override is not None else None
            ),
            continue_after_known_provider_errors=continue_after_known_provider_errors,
            runtime_config=runtime_config,
        )
        source_report = Path(str(report.get("output_path", "")))
        if source_report.is_file():
            persisted_report = json.loads(source_report.read_text(encoding="utf-8"))
            metadata = {
                "run_identity_hash": str(run["identity_hash"]),
                "campaign_identity_hash": identity_hash,
            }
            changed = False
            for key, value in metadata.items():
                if key not in persisted_report:
                    persisted_report[key] = value
                    changed = True
                elif persisted_report[key] != value:
                    raise ValueError("El reporte live no coincide con la identidad fijada")
            if changed:
                _write_private_json(source_report, persisted_report)
                report.update(metadata)
        new_fragment = _fragment_record(report, run_dir, run, identity_hash)
        fragments = prior_fragments + ([new_fragment] if new_fragment else [])
        model = report["models"][0]
        new_cases = [
            {
                "case_id": case.get("case_id", "unknown"),
                "provider_turn_started": case.get("provider_turn_started", False),
                "usage_complete": case.get("usage_complete"),
                "estimated_cost_usd": case.get("estimated_cost_usd"),
                "known_estimated_cost_lower_bound_usd": case.get("known_estimated_cost_lower_bound_usd"),
                "status": case.get("status"),
                "model_turn_completed": case.get("model_turn_completed", False),
                "usage_reconciled_noncritical_error": case.get("status") == "provider_error_known_usage",
            }
            for case in model["cases"]
        ]
        all_cases = prior_cases + new_cases
        returned_ids = {str(case.get("case_id")) for case in all_cases}
        if (
            len(all_cases) != len(returned_ids)
            or not returned_ids <= set(run["case_ids"])
            or [str(case.get("case_id")) for case in all_cases]
            != [case_id for case_id in run["case_ids"] if case_id in returned_ids]
        ):
            raise ValueError("La corrida produjo IDs duplicados, desconocidos o fuera de orden")
        complete = (
            returned_ids == set(run["case_ids"])
            and len(all_cases) == len(run["case_ids"])
            and report.get("run_status") == "completed"
            and not model.get("stopped_reason")
            and all(
                case.get("model_turn_completed")
                or (continue_after_known_provider_errors and case.get("usage_reconciled_noncritical_error"))
                for case in all_cases
            )
        )
        stopped_reason = (
            "provider_error"
            if any(case.get("status") == "provider_error" for case in all_cases)
            else "known_noncritical_provider_errors"
            if any(case.get("usage_reconciled_noncritical_error") for case in all_cases)
            else "campaign_budget"
            if not complete
            else None
        )
        detailed_cases = prior_detailed_cases
        if new_fragment:
            detailed_cases = _load_fragment_cases(
                fragments,
                run_dir=run_dir,
                run=run,
                campaign_identity_hash=identity_hash,
            )
        consolidated_path: str | None = None
        consolidated_sha: str | None = None
        if fragments and [str(row.get("case_id")) for row in detailed_cases] == [
            str(row.get("case_id")) for row in all_cases
        ]:
            consolidated_path, consolidated_sha = _consolidate_report(
                report=report,
                detailed_cases=detailed_cases,
                all_cases=all_cases,
                run=run,
                complete=complete,
                run_dir=run_dir,
                fragments=fragments,
                fixture_cases=cases,
            )
        completed_run = {
            "run_id": run_id,
            "identity": run["identity"],
            "known_estimated_cost_usd": sum(
                float(
                    case.get("estimated_cost_usd")
                    if case.get("estimated_cost_usd") is not None
                    else case.get("known_estimated_cost_lower_bound_usd", 0.0)
                )
                for case in all_cases
            ),
            "spent_unknown": model["spent_unknown"],
            "cases": all_cases,
            "report_fragments": fragments,
            "complete": complete,
            "stopped_reason": stopped_reason,
            "summary": {
                "run_id": run_id,
                "report_path": consolidated_path or report["output_path"],
                "report_sha256": consolidated_sha,
                "run_status": "completed" if complete else report["run_status"],
                "case_count": len(all_cases),
                "expected_case_count": len(run["case_ids"]),
                "complete": complete,
                "stopped_reason": stopped_reason,
                "known_estimated_cost_usd": sum(
                    float(
                        case.get("estimated_cost_usd")
                        if case.get("estimated_cost_usd") is not None
                        else case.get("known_estimated_cost_lower_bound_usd", 0.0)
                    )
                    for case in all_cases
                ),
                "spent_unknown": model["spent_unknown"],
                "known_noncritical_provider_error_count": sum(
                    case.get("usage_reconciled_noncritical_error", False) for case in all_cases
                ),
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
            else "stopped_campaign_budget"
        )
        _write_private_json(state_path, state)
        reports.append(completed_run["summary"])
        if not spend["admit_new_requests"] or (not complete and not continue_after_known_provider_errors):
            break
    all_runs_complete = all(
        str(run["run_id"]) in completed and completed[str(run["run_id"])].get("complete") for run in run_specs
    )
    state["status"] = (
        state.get("status")
        if state.get("spent_unknown")
        else "completed_with_known_provider_errors"
        if all_runs_complete
        and any(
            completed_run.get("stopped_reason") == "known_noncritical_provider_errors"
            for completed_run in completed.values()
        )
        else "completed"
        if all_runs_complete
        else "stopped_provider_error"
        if state.get("status") == "stopped_provider_error"
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
