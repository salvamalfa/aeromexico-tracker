"""Validation of pinned F2.9 source campaign records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.chat.stage2_finalization import parse_pinned_object, validate_terminal_recovery
from src.conversational_analytics.evaluation_campaign import _digest


def validate_sources(
    raw: dict[str, bytes], *, approved_source_sha256: dict[str, str],
    expected_original_execution: str, expected_continuation_execution: str,
    original_known_cost_usd: float, closed_continuation_cost_usd: float,
    sol_low_progress_cost_usd: float,
    low_run_id: str, source_continuation_id: str, source_paths: dict[str, Path],
) -> dict[str, dict[str, Any]]:
    data = {name: parse_pinned_object(content, name) for name, content in raw.items()}
    original, original_report, owner = (
        data[k] for k in ("original_ledger", "original_report", "owner_evidence")
    )
    plan, ledger, progress, recovery = (
        data["continuation_plan"],
        data["continuation_ledger"],
        data["sol_low_progress"],
        data["terminal_recovery"],
    )
    if (original.get("status"), original.get("spent_unknown"), original.get("known_spend_usd")) != (
        "stopped_unknown_spend",
        True,
        original_known_cost_usd,
    ):
        raise ValueError("La campaña original no coincide con el piloto detenido fijado")
    original_hash = original.get("identity_hash")
    if (
        not isinstance(original.get("identity"), dict)
        or _digest(original["identity"]) != original_hash
        or original_report.get("campaign_identity_hash") != original_hash
        or original_report.get("run_identity_hash")
        != owner.get("source_identity", {}).get("run_identity_hash")
        or owner.get("source_identity", {}).get("campaign_ledger_sha256")
        != approved_source_sha256["original_ledger"]
        or owner.get("source_identity", {}).get("report_sha256") != approved_source_sha256["original_report"]
        or owner.get("source_identity", {}).get("execution_commit") != expected_original_execution
        or any(
            run.get("execution_commit") != expected_original_execution
            for run in original["identity"].get("runs", [])
        )
    ):
        raise ValueError("La evidencia de piloto original no concuerda con su ledger")
    if (
        owner.get("kind") != "private_owner_usage_confirmation"
        or owner.get("owner_attestation", {}).get("external_usage_independently_verified") is not False
        or owner.get("owner_attestation", {}).get("input_tokens") != 408_550
        or owner.get("owner_attestation", {}).get("output_tokens") != 7_065
        or owner.get("owner_attestation", {}).get("includes_failed_call") is not True
        or owner.get("reconciliation", {}).get("failed_case_individual_usage") is not None
        or owner.get("reconciliation", {}).get("invoice_total_usd") is not None
    ):
        raise ValueError("La evidencia original debe conservar uso individual desconocido y sin factura")
    if (
        plan.get("schema_version") != 1
        or plan.get("kind") != "f2_9_stage2_continuation_plan"
        or plan.get("continuation", {}).get("execution_commit") != expected_continuation_execution
        or plan.get("source", {}).get("campaign_identity_hash") != original_hash
        or plan.get("source", {}).get("ledger_sha256") != approved_source_sha256["original_ledger"]
        or plan.get("source", {}).get("report_sha256") != approved_source_sha256["original_report"]
    ):
        raise ValueError("El plan interrumpido no deriva del piloto fijado")
    identity = ledger.get("identity")
    completed = ledger.get("completed_runs")
    continuation_runs = plan.get("continuation", {}).get("runs")
    if (
        not isinstance(identity, dict)
        or _digest(identity) != ledger.get("identity_hash")
        or not isinstance(continuation_runs, list)
        or identity.get("runs") != [run.get("identity") for run in continuation_runs]
        or identity.get("run_identity_hashes") != [run.get("identity_hash") for run in continuation_runs]
        or any(_digest(run.get("identity", {})) != run.get("identity_hash") for run in continuation_runs)
        or ledger.get("status") != "running"
        or ledger.get("active_run_id") != low_run_id
        or ledger.get("spent_unknown") is not False
        or not isinstance(completed, dict)
        or set(completed)
        != {
            "f22-s2-gpt-6-luna-medium-proposed-r1-cont-4894e8e275ac0ec2",
            "f22-s2-gpt-6-luna-max-proposed-r1-cont-4894e8e275ac0ec2",
        }
    ):
        raise ValueError("El ledger interrumpido no conserva exactamente las dos corridas cerradas")
    closed_cost = sum(float(run["known_estimated_cost_usd"]) for run in completed.values())
    if abs(closed_cost - closed_continuation_cost_usd) > 1e-12:
        raise ValueError("El costo conocido de las corridas cerradas no coincide con el pin")
    if any(
        run.get("complete") is not True or run.get("spent_unknown") is not False for run in completed.values()
    ):
        raise ValueError("Las dos corridas cerradas deben ser completas y conciliadas")
    original_models = original_report.get("models", [])
    original_cases = original_models[0].get("cases", []) if len(original_models) == 1 else []
    if (
        len(original_cases) != 9
        or sum(row.get("model_turn_completed") is True for row in original_cases) != 8
        or [row.get("case_id") for row in original_cases if row.get("model_turn_completed") is not True]
        != ["en_am_rask"]
    ):
        raise ValueError(
            "El piloto original debe conservar ocho respuestas y el único fallo sin costo individual"
        )
    low = next((run for run in plan["continuation"]["runs"] if run.get("run_id") == low_run_id), None)
    if not isinstance(low, dict) or low.get("candidate") != "gpt-6.1-sol@low":
        raise ValueError("El plan no conserva la corrida SolLow interrumpida")
    planned = {run.get("candidate"): run for run in plan["continuation"]["runs"]}
    source_low = next(
        (
            run
            for run in plan["source"]["runs"]
            if run.get("identity", {}).get("candidate") == "gpt-6.1-sol@low"
        ),
        None,
    )
    if not isinstance(source_low, dict) or not isinstance(source_low.get("identity_hash"), str):
        raise ValueError("El plan no conserva la identidad SolLow de la fuente")
    for name, candidate in (
        ("closed_report_luna_medium", "gpt-6-luna@medium"),
        ("closed_report_luna_max", "gpt-6-luna@max"),
    ):
        report = data[name]
        planned_run = planned.get(candidate)
        model_rows = report.get("models", [])
        if (
            not isinstance(planned_run, dict)
            or len(model_rows) != 1
            or report.get("run_identity_hash") != planned_run.get("identity_hash")
            or report.get("run_identity") != planned_run.get("identity")
            or model_rows[0].get("candidate") != candidate
            or model_rows[0].get("run_identity") != planned_run.get("identity")
            or any(row.get("model_turn_completed") is not True for row in model_rows[0].get("cases", []))
        ):
            raise ValueError("Un reporte cerrado no coincide con su identidad fijada")
    for name, candidate in (
        ("closed_report_luna_medium", "gpt-6-luna@medium"),
        ("closed_report_luna_max", "gpt-6-luna@max"),
    ):
        report_path = ledger["completed_runs"][planned[candidate]["run_id"]]["summary"].get("report_path", "")
        if Path(str(report_path)).name != Path(str(source_paths[name])).name:
            raise ValueError("La ruta de reporte cerrada no coincide con el ledger fijado")
    if (
        progress.get("status") != "running"
        or progress.get("active_case_id") != "es_am_market_share"
        or progress.get("active_usage_state") != "unknown_in_flight"
        or progress.get("models", [{}])[0].get("case_count") != 13
        or progress.get("models", [{}])[0].get("completed_turn_count") != 13
        or abs(progress.get("known_estimated_spend_usd", -1) - sol_low_progress_cost_usd) > 1e-12
        or Path(str(progress.get("output_path", ""))).name != "chat-eval-20261010T145434529289Z.json"
    ):
        raise ValueError("El progreso SolLow no coincide con los 13 casos guardados agregadamente")
    recovered_answer, input_tokens, output_tokens = validate_terminal_recovery(
        recovery,
        expected_source={
            "candidate": "gpt-6.1-sol@low",
            "case_id": "es_am_market_share",
            "continuation_id": source_continuation_id,
            "run_id": low_run_id,
            "source_run_identity_hash": source_low["identity_hash"],
            "plan_sha256": approved_source_sha256["continuation_plan"],
            "progress_sha256": approved_source_sha256["sol_low_progress"],
            "continuation_run_identity_hash": low["identity_hash"],
        },
        expected_case_id="es_am_market_share",
    )
    return {
        **data,
        "_low_run": low,
        "_source_low_run": source_low,
        "_continuation_campaign_hash": ledger["identity_hash"],
        "_recovered_answer": recovered_answer,
        "_answer_sha256": recovery["answer"]["sha256"],
        "_recovered_input_tokens": input_tokens,
        "_recovered_output_tokens": output_tokens,
    }


