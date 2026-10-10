"""Offline validation of the pinned F2.9 finalization provenance chain."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from stage2_continuation_lineage import validate_continuation_inputs

APPROVED_SOURCE_SHA256 = {
    "original_ledger": "fb6a661a8635b8e139951a541ee549ba7f3b35dfde611ebfc73e31eb5fad5140",
    "original_report": "0305ac40cc52e72371a1ed3b3334624c6261ed4be99adcfd9518727265913002",
    "owner_evidence": "a042789788649f22e9bf213d14a274fc9e117fcd825b8ce6cfd0221007c4446c",
    "continuation_plan": "33c7167c21998d0773329104b74a1d6c1b1f697cb3e411d88b31f2cf21be89af",
    "continuation_ledger": "7cc1c0408f26ed3307ff3b0ad3de13d7984ff52a2837115d3c6662fc4742f0e3",
    "closed_report_luna_medium": "98be1fa45a1407e35fa368e62090b111139e8a7e5619352fe35a44c35f1108ac",
    "closed_report_luna_max": "1d090a49966876cf3fe9b0f847e079c6b0b72da1ef3f19d73d76fa8c19bd51ca",
    "sol_low_progress": "f7a085c2d56ca79b8a8d52402392c9f10dae62e388e1437f941759fd9fe20821",
    "recovery": "74709aadfb6c255726ebaa6a5f32dafd868abc9d640f489861ed672fa04bf1d6",
}
ORIGINAL_EXECUTION = "73db4d1c638e0c208feae433642e652485f5dfe6"
CONTINUATION_EXECUTION = "8f671846f819db57dd0a96d70074d4d568551100"
RECOVERED_CASE = "es_am_market_share"
ORIGINAL_FAILURE = "en_am_rask"
SOL_LOW = "gpt-6.1-sol@low"
SOL_MEDIUM = "gpt-6.1-sol@medium"


def _path(section: dict[str, Any], key: str, label: str, error: type[ValueError]) -> Path:
    value = section.get(key)
    if not isinstance(value, str) or not value:
        raise error(f"El plan no conserva la ruta privada de {label}")
    path = Path(value).absolute()
    cursor = Path(path.anchor)
    for part in path.parts[1:]:
        cursor /= part
        if cursor.is_symlink():
            raise error(f"La ruta privada de {label} contiene un enlace simbólico")
    if not path.is_file():
        raise error(f"Falta el archivo privado de {label}")
    return path.resolve()


def _read(path: Path, label: str, read_json_with_hash: Any) -> tuple[dict[str, Any], str]:
    return read_json_with_hash(path, label)


def _pinned_sources(plan: dict[str, Any], error: type[ValueError], read_json_with_hash: Any):
    source = plan.get("source")
    interrupted = plan.get("interrupted_continuation")
    recovery = plan.get("recovery")
    final = plan.get("finalization")
    if not all(isinstance(item, dict) for item in (source, interrupted, recovery, final)):
        raise error("El plan no conserva source, interrupted_continuation, recovery y finalization")
    source_paths = source.get("paths")
    if not isinstance(source_paths, dict):
        raise error("El plan no conserva las rutas del piloto original")
    paths = {
        "original_ledger": _path(source_paths, "original_ledger", "ledger original", error),
        "original_report": _path(source_paths, "original_report", "reporte original", error),
        "owner_evidence": _path(source_paths, "owner_evidence", "evidencia del dueño", error),
        "continuation_plan": _path(interrupted, "plan_path", "plan interrumpido", error),
        "continuation_ledger": _path(interrupted, "ledger_path", "ledger interrumpido", error),
        "sol_low_progress": _path(interrupted, "progress_path", "progreso agregado SolLow", error),
        "recovery": _path(recovery, "path", "evidencia terminal recuperada", error),
    }
    closed = interrupted.get("closed_reports")
    if not isinstance(closed, list) or len(closed) != 2:
        raise error("El plan debe conservar exactamente los dos reportes cerrados de continuación")
    by_candidate = {row.get("candidate"): row for row in closed if isinstance(row, dict)}
    if set(by_candidate) != {"gpt-6-luna@medium", "gpt-6-luna@max"}:
        raise error("Los reportes cerrados no corresponden a Luna medium y Luna max")
    paths["closed_report_luna_medium"] = _path(
        by_candidate["gpt-6-luna@medium"], "path", "reporte Luna medium", error
    )
    paths["closed_report_luna_max"] = _path(by_candidate["gpt-6-luna@max"], "path", "reporte Luna max", error)
    values: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for name, path in paths.items():
        value, actual_hash = _read(path, name, read_json_with_hash)
        if actual_hash != APPROVED_SOURCE_SHA256[name]:
            raise error(f"El SHA-256 de la fuente privada no coincide con el pin: {name}")
        values[name], hashes[name] = value, actual_hash
    declared = plan.get("source_sha256")
    if (
        not isinstance(declared, dict)
        or set(declared) != set(hashes)
        or any(declared.get(name) != value for name, value in hashes.items())
    ):
        raise error("Los SHA-256 de fuentes del plan no corresponden a los bytes fijados")
    if (
        source.get("ledger_sha256") != hashes["original_ledger"]
        or source.get("report_sha256") != hashes["original_report"]
        or source.get("owner_evidence_sha256") != hashes["owner_evidence"]
        or source.get("execution_commit") != ORIGINAL_EXECUTION
        or interrupted.get("continuation_plan_sha256") != hashes["continuation_plan"]
        or interrupted.get("continuation_ledger_sha256") != hashes["continuation_ledger"]
        or interrupted.get("execution_commit") != CONTINUATION_EXECUTION
        or interrupted.get("progress_sha256") != hashes["sol_low_progress"]
        or recovery.get("sha256") != hashes["recovery"]
        or recovery.get("plan_sha256") != hashes["continuation_plan"]
        or recovery.get("progress_sha256") != hashes["sol_low_progress"]
    ):
        raise error("Los metadatos de lineage no coinciden con las fuentes congeladas")
    return source, interrupted, recovery, final, values, hashes


def _verify_recovery(
    recovery_plan: dict[str, Any],
    recovery_artifact: dict[str, Any],
    continuation: dict[str, Any],
    progress: dict[str, Any],
    derived: dict[str, Any],
    derived_parts: tuple[Any, ...],
    expected_low_run: dict[str, Any],
    continuation_campaign_hash: str,
    source_hashes: dict[str, str],
    error: type[ValueError],
    digest: Any,
) -> None:
    artifact = recovery_artifact
    row_source = artifact.get("source")
    provider, usage = artifact.get("provider"), artifact.get("usage")
    answer, evaluation = artifact.get("answer"), artifact.get("evaluation")
    if not all(isinstance(item, dict) for item in (row_source, provider, usage, answer, evaluation)):
        raise error("La evidencia de recuperación terminal está incompleta")
    candidate, case_id = recovery_plan.get("candidate"), recovery_plan.get("case_id")
    expected_cont_run_hash = expected_low_run.get("identity_hash")
    source_run_id = expected_low_run.get("identity", {}).get("continuation", {}).get("source_run_id")
    original_source = next(
        (run for run in continuation.get("source", {}).get("runs", []) if run.get("run_id") == source_run_id),
        None,
    )
    expected = {
        "candidate": SOL_LOW,
        "case_id": RECOVERED_CASE,
        "continuation_id": continuation.get("continuation", {}).get("continuation_id"),
        "run_id": expected_low_run.get("run_id"),
        "plan_sha256": source_hashes["continuation_plan"],
        "progress_sha256": source_hashes["sol_low_progress"],
        "source_run_identity_hash": original_source.get("identity_hash")
        if isinstance(original_source, dict)
        else None,
        "continuation_run_identity_hash": expected_cont_run_hash,
    }
    if recovery_plan.get("status") != "GET_recovered_remote_completed_idle" or any(
        row_source.get(key) != value for key, value in expected.items()
    ):
        raise error("La recuperación no pertenece al slot SolLow terminal fijado")
    answer_text = answer.get("text")
    answer_sha = (
        hashlib.sha256(answer_text.encode("utf-8")).hexdigest() if isinstance(answer_text, str) else None
    )
    if (
        candidate != SOL_LOW
        or case_id != RECOVERED_CASE
        or recovery_plan.get("usage_complete") is not True
        or (recovery_plan.get("input_tokens"), recovery_plan.get("output_tokens")) != (137_951, 499)
        or recovery_plan.get("latency_ms") is not None
        or recovery_plan.get("tool_trace") != "unavailable"
        or recovery_plan.get("auto_graded") is not False
        or recovery_plan.get("auto_approved") is not False
        or recovery_plan.get("tool_calls_inferred") is not False
        or recovery_plan.get("answer_sha256") != answer_sha
        or answer.get("sha256") != answer_sha
        or answer.get("present") is not True
        or answer.get("selected_assistant_message_count") != 1
        or provider.get("turn_status") != "completed"
        or provider.get("session_status") != "idle"
        or provider.get("session_idle") is not True
        or provider.get("turn_identity_verified") is not True
        or usage.get("usage_complete") is not True
        or (usage.get("input_tokens"), usage.get("output_tokens")) != (137_951, 499)
        or evaluation.get("transport_recovered") is not True
        or evaluation.get("latency_valid") is not False
        or evaluation.get("auto_graded") is not False
        or evaluation.get("auto_approved") is not False
        or evaluation.get("tool_calls_inferred") is not False
        or artifact.get("request_controls", {}).get("side_effecting_requests") != 0
    ):
        raise error("La recuperación no prueba un único turno terminado sin replay ni autoevaluación")
    rows, meta, identity_hash, campaign_hash = derived_parts
    row = rows.get(RECOVERED_CASE)
    lineage = meta["report"].get("derived_lineage", {})
    if (
        set(rows) != {RECOVERED_CASE}
        or identity_hash != expected_cont_run_hash
        or campaign_hash != continuation_campaign_hash
        or meta["identity"] != expected_low_run.get("identity")
        or meta["report"].get("case_count") != 1
        or meta["report"].get("run_status") != "recovered_partial"
        or lineage.get("kind") != "single_terminal_turn_recovery"
        or lineage.get("source_progress_sha256") != source_hashes["sol_low_progress"]
        or lineage.get("recovery_sha256") != source_hashes["recovery"]
        or lineage.get("continuation_plan_sha256") != source_hashes["continuation_plan"]
        or lineage.get("tool_trace") != "unavailable"
        or lineage.get("human_review_required") is not True
        or row.get("status") != "recovered_terminal_turn"
        or row.get("model_turn_completed") is not True
        or row.get("response") != answer_text
        or row.get("latency_seconds") is not None
        or row.get("quality", {}).get("evaluated") is not False
        or row.get("quality", {}).get("requires_blinded_human_rubric") is not True
        or row.get("quality", {}).get("automatic_grade_type") is not None
        or row.get("provider_tool_call_count") is not None
        or row.get("tool_calls") is not None
        or row.get("recovery_metadata", {}).get("tool_calls_inferred") is not False
    ):
        raise error("El reporte derivado debe contener solo la respuesta recuperada y su lineage literal")


def validate_finalization_inputs(
    plan_path: Path,
    fixture_path: Path,
    owner_evidence_path: Path,
    fixture: dict[str, Any],
    *,
    candidates: dict[str, tuple[str, str]],
    expected_case_ids: tuple[str, ...],
    ExportError: type[ValueError],
    canonical: Any,
    digest: Any,
    read_json_with_hash: Any,
    report_cases: Any,
    fixture_cases: Any,
) -> tuple[dict[str, list[Path]], dict[str, Any]]:
    """Verify all pinned source, recovery, and terminal finalization artifacts."""
    _path({"value": str(plan_path)}, "value", "plan de finalización", ExportError)
    _path({"value": str(fixture_path)}, "value", "fixture congelado", ExportError)
    _path({"value": str(owner_evidence_path)}, "value", "evidencia del dueño", ExportError)
    plan, plan_sha = read_json_with_hash(plan_path, "finalization plan")
    if plan.get("schema_version") != 1 or plan.get("kind") != "f2_9_stage2_finalization_plan":
        raise ExportError("El archivo no es un plan de finalización stage2 compatible")
    if plan.get("mode") != "live-campaign" or plan.get("provider_calls_now") is not None:
        raise ExportError("El plan de finalización aún no tiene corrida live registrada")
    source, interrupted, recovery, final, sources, source_hashes = _pinned_sources(
        plan, ExportError, read_json_with_hash
    )
    if source.get("campaign_identity_hash") != sources["original_ledger"].get("identity_hash"):
        raise ExportError("El plan final no conserva el hash de campaña fuente original")
    if owner_evidence_path.resolve() != Path(str(source["paths"].get("owner_evidence", ""))).resolve():
        raise ExportError("La evidencia owner-reported no es la fuente privada fijada en el plan")
    fixture_sha = hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    final_runs = final.get("runs")
    if not isinstance(final_runs, list) or len(final_runs) != 2:
        raise ExportError("El plan final debe conservar exactamente dos corridas nativas")

    # Reuse the strict source-to-continuation verifier, permitting only its
    # explicitly pinned running SolLow slot to remain active and unreported.
    cont_plan_path = Path(interrupted["plan_path"]).resolve()
    report_paths, lineage = validate_continuation_inputs(
        cont_plan_path,
        fixture_path,
        owner_evidence_path,
        fixture,
        candidates=candidates,
        expected_case_ids=expected_case_ids,
        ExportError=ExportError,
        canonical=canonical,
        digest=digest,
        read_json_with_hash=read_json_with_hash,
        report_cases=report_cases,
        fixture_cases=fixture_cases,
        allow_interrupted_active_run=True,
    )
    if (
        lineage["plan_sha256"] != source_hashes["continuation_plan"]
        or lineage["continuation_ledger_sha256"] != source_hashes["continuation_ledger"]
        or lineage["source_ledger_sha256"] != source_hashes["original_ledger"]
        or lineage["source_report_sha256"] != source_hashes["original_report"]
        or lineage["owner_evidence_sha256"] != source_hashes["owner_evidence"]
        or lineage["source_execution_commit"] != ORIGINAL_EXECUTION
        or lineage["source_execution_commit"] == CONTINUATION_EXECUTION
        or lineage["continuation_execution_commit"] != CONTINUATION_EXECUTION
        or fixture_sha != sources["continuation_plan"].get("continuation", {}).get("fixture_sha256")
    ):
        raise ExportError("El plan final no se encadena con los bytes del piloto y continuación fijados")

    cont_plan = sources["continuation_plan"]
    cont_ledger = sources["continuation_ledger"]
    progress = sources["sol_low_progress"]
    low_continuation = next(
        (run for run in cont_plan.get("continuation", {}).get("runs", []) if run.get("candidate") == SOL_LOW),
        None,
    )
    if not isinstance(low_continuation, dict):
        raise ExportError("Falta la identidad planeada de continuación SolLow")
    closed_candidate_set = {
        run.get("identity", {}).get("candidate")
        for run in cont_ledger.get("completed_runs", {}).values()
        if isinstance(run, dict)
    }
    progress_models = progress.get("models", [])
    progress_low = next(
        (row for row in progress_models if isinstance(row, dict) and row.get("candidate") == SOL_LOW), {}
    )
    if (
        cont_ledger.get("status") != "running"
        or cont_ledger.get("active_run_id") != low_continuation.get("run_id")
        or closed_candidate_set != {"gpt-6-luna@medium", "gpt-6-luna@max"}
        or progress.get("status") != "running"
        or progress.get("active_case_id") != RECOVERED_CASE
        or progress_low.get("case_count") != 13
        or progress_low.get("completed_turn_count") != 13
        or interrupted.get("progress_case_count") != 13
        or interrupted.get("progress_cost_is_aggregate") is not True
    ):
        raise ExportError("El plan interrumpido no conserva su estado parcial original sin filas inventadas")

    derived_spec = final.get("derived_reports", {}).get("sol_low_recovery", {})
    derived_path = _path(derived_spec, "path", "reporte de recuperación derivado", ExportError)
    derived_report, derived_sha = read_json_with_hash(derived_path, "reporte recuperado derivado")
    if derived_sha != derived_spec.get("sha256") or derived_sha != recovery.get("report_sha256"):
        raise ExportError("El SHA del reporte recuperado derivado no coincide con el plan")
    derived_rows, derived_meta, derived_hash, derived_campaign = report_cases(derived_report, derived_path)
    _verify_recovery(
        recovery,
        sources["recovery"],
        cont_plan,
        progress,
        derived_report,
        (derived_rows, derived_meta, derived_hash, derived_campaign),
        low_continuation,
        cont_ledger["identity_hash"],
        source_hashes,
        ExportError,
        digest,
    )
    if (
        derived_spec.get("candidate") != SOL_LOW
        or derived_spec.get("case_id") not in (None, RECOVERED_CASE)
        or derived_spec.get("identity") != low_continuation.get("identity")
        or derived_spec.get("identity_hash") != low_continuation.get("identity_hash")
        or derived_spec.get("source_run_identity_hash") != low_continuation.get("identity_hash")
        or derived_spec.get("recovery_sha256") != source_hashes["recovery"]
        or derived_spec.get("progress_sha256") != source_hashes["sol_low_progress"]
        or derived_spec.get("human_review_required") is not True
    ):
        raise ExportError("El reporte derivado no está ligado al progreso y recuperación correctos")

    expected_replacements = list(expected_case_ids[:13])
    expected_recovered = expected_case_ids[13]
    expected_never_attempted = [expected_case_ids[14]]
    final_low_ids = expected_replacements + expected_never_attempted
    final_cases = {case["id"]: case for case in fixture_cases(fixture)}
    expected_by_candidate = {SOL_LOW: final_low_ids, SOL_MEDIUM: list(expected_case_ids)}
    if (
        final.get("replacement_case_ids") != expected_replacements
        or final.get("never_attempted_case_ids") != expected_never_attempted
        or final.get("recovered_case_id_skipped") != expected_recovered
        or final.get("excluded_original_failure")
        != {"candidate": "gpt-6-luna@medium", "case_id": ORIGINAL_FAILURE}
        or final.get("new_provider_request_count") != 29
        or final.get("response_count_ceiling_if_complete") != 59
        or final.get("max_reviewable_candidates") != 59
        or recovery.get("case_id") != expected_recovered
    ):
        raise ExportError("La partición de slots finales no coincide con los 29 casos aprobados")
    if [row.get("candidate") for row in final_runs] != [SOL_LOW, SOL_MEDIUM]:
        raise ExportError("Las corridas nativas finales no son SolLow y SolMedium")

    final_ledger_path = _path(final, "ledger_path", "ledger final", ExportError)
    final_ledger, final_ledger_sha = read_json_with_hash(final_ledger_path, "ledger final")
    final_identity = final_ledger.get("identity")
    final_campaign_hash = final_ledger.get("identity_hash")
    live_result = plan.get("live_result")
    if (
        not isinstance(final_identity, dict)
        or final_campaign_hash != digest(final_identity)
        or not isinstance(live_result, dict)
        or live_result.get("identity_hash") != final_campaign_hash
        or final_ledger.get("status") != "completed"
        or final_ledger.get("active_run_id") is not None
        or final.get("execution_commit") == CONTINUATION_EXECUTION
        or final.get("execution_commit") == ORIGINAL_EXECUTION
        or not isinstance(final.get("execution_commit"), str)
        or len(final.get("execution_commit", "")) != 40
        or any(char not in "0123456789abcdef" for char in final.get("execution_commit", ""))
        or final_identity.get("runs") != [row.get("identity") for row in final_runs]
        or final_identity.get("run_identity_hashes") != [row.get("identity_hash") for row in final_runs]
        or final_identity.get("budget_usd")
        != plan.get("billing_reconciliation", {}).get("remaining_budget_usd")
    ):
        raise ExportError("El ledger final no es terminal ni coincide con el resultado live del plan")
    if plan.get("billing_reconciliation", {}).get("authorized_reserve_usd") != 8.0:
        raise ExportError("La reserva autorizada de la campaña final cambió")

    actual_runs = final_ledger.get("completed_runs")
    if not isinstance(actual_runs, dict) or len(actual_runs) != 2:
        raise ExportError("El ledger final debe conservar exactamente dos corridas cerradas")
    final_by_candidate = {row.get("candidate"): row for row in final_runs}
    final_specs: dict[str, dict[str, Any]] = {}
    final_chains = dict(lineage["identity_chains"])
    for candidate, selected in expected_by_candidate.items():
        slot = final_by_candidate[candidate]
        identity, run_hash = slot.get("identity"), slot.get("identity_hash")
        if (
            not isinstance(identity, dict)
            or run_hash != digest(identity)
            or identity.get("candidate") != candidate
            or identity.get("execution_commit") != final.get("execution_commit")
            or identity.get("case_ids_hash") != digest(selected)
            or identity.get("case_fixture_hash") != digest([final_cases[case_id] for case_id in selected])
            or slot.get("case_ids") != selected
            or slot.get("source_run_id") != identity.get("finalization", {}).get("source_continuation_run_id")
        ):
            raise ExportError("La identidad del slot final no coincide con su partición de casos")
        source_run_id = identity.get("finalization", {}).get("source_continuation_run_id")
        source_run = next(
            (run for run in cont_plan["continuation"]["runs"] if run.get("run_id") == source_run_id), None
        )
        if not isinstance(source_run, dict) or source_run.get("candidate") != candidate:
            raise ExportError("La corrida final no deriva del slot de continuación del mismo candidato")
        expected_final_run_id = (
            str(source_run_id).split("-cont-")[0] + f"-final-{final.get('continuation_id')}"
        )
        if slot.get("run_id") != expected_final_run_id or identity.get("run_id") != expected_final_run_id:
            raise ExportError("El run_id final no conserva el patrón de lineage de continuación")
        variable = {
            "run_id",
            "case_ids_hash",
            "case_fixture_hash",
            "execution_commit",
            "continuation",
            "finalization",
        }
        prior_base = {key: value for key, value in source_run["identity"].items() if key not in variable}
        final_base = {key: value for key, value in identity.items() if key not in variable}
        if canonical(prior_base) != canonical(final_base):
            raise ExportError("La finalización cambió modelo, prompt, contexto, herramientas o límites")
        if identity.get("finalization", {}).get("source_identity_hash") != source_run.get("identity_hash"):
            raise ExportError("La corrida final perdió su hash de identidad de origen")
        if run_hash not in final_identity.get("run_identity_hashes", []):
            raise ExportError("El ledger final no referencia el hash de identidad planeado")
        completed = actual_runs.get(str(slot.get("run_id")))
        if (
            not isinstance(completed, dict)
            or canonical(completed.get("identity")) != canonical(identity)
            or digest(completed.get("identity")) != run_hash
            or completed.get("complete") is not True
            or completed.get("spent_unknown") is not False
        ):
            raise ExportError("La corrida final no tiene cierre terminal verificable en el ledger")
        report_paths_list = slot.get("report_paths")
        summaries = completed.get("summary", {})
        report_path = Path(str(summaries.get("report_path", ""))).resolve()
        if not isinstance(report_paths_list, list) or report_paths_list != [str(report_path)]:
            raise ExportError("El plan final no conserva la ruta real del reporte del ledger")
        report, report_sha = read_json_with_hash(report_path, "reporte final")
        indexed, metadata, report_run_hash, report_campaign = report_cases(report, report_path)
        if (
            report.get("mode") != "live-evaluation"
            or report.get("probe_only") is not False
            or canonical(metadata["identity"]) != canonical(identity)
            or report_run_hash != run_hash
            or report.get("run_identity_hash") != run_hash
            or report_campaign != final_campaign_hash
            or list(indexed) != selected
            or report.get("case_count") != len(selected)
        ):
            raise ExportError("El reporte final no coincide con el ledger, identidad y casos autorizados")
        ledger_cases = completed.get("cases", [])
        if [row.get("case_id") for row in ledger_cases] != selected or any(
            indexed[row["case_id"]].get("model_turn_completed") is not row.get("model_turn_completed")
            for row in ledger_cases
        ):
            raise ExportError("Las filas del reporte final difieren del checkpoint terminal")
        final_specs[candidate] = {
            "path": report_path,
            "role": "finalization",
            "sha256": report_sha,
            "identity": identity,
            "identity_hash": run_hash,
            "campaign_identity_hash": final_campaign_hash,
            "case_ids": selected,
            "expected_case_ids": selected,
            "provenance": {
                "finalization_plan_sha256": plan_sha,
                "finalization_ledger_sha256": final_ledger_sha,
                "finalization_execution_commit": final.get("execution_commit"),
                "source_continuation_execution_commit": CONTINUATION_EXECUTION,
                "source_original_execution_commit": ORIGINAL_EXECUTION,
            },
        }
        final_chains[candidate].append(
            {
                "lineage_role": "finalization",
                "campaign_identity_hash": final_campaign_hash,
                "identity_hash": run_hash,
                "execution_commit": final.get("execution_commit"),
                "identity": identity,
            }
        )

    recovered_spec = {
        "path": derived_path,
        "role": "recovery",
        "sha256": derived_sha,
        "identity": low_continuation["identity"],
        "identity_hash": low_continuation["identity_hash"],
        "campaign_identity_hash": lineage["continuation_campaign_identity_hash"],
        "case_ids": [RECOVERED_CASE],
        "expected_case_ids": list(expected_case_ids),
        "provenance": {
            "recovery_sha256": source_hashes["recovery"],
            "recovery_report_sha256": derived_sha,
            "recovery_answer_sha256": recovery.get("answer_sha256"),
            "source_progress_sha256": source_hashes["sol_low_progress"],
            "source_continuation_plan_sha256": source_hashes["continuation_plan"],
            "source_continuation_ledger_sha256": source_hashes["continuation_ledger"],
            "human_review_required": True,
            "latency_ms": None,
            "tool_trace": "unavailable",
            "auto_graded": False,
            "tool_calls_inferred": False,
        },
    }
    report_paths[SOL_LOW].append(derived_path)
    lineage["fragments"][SOL_LOW].append(recovered_spec)
    lineage["continuation_fragments"] = lineage["fragments"]
    for candidate, spec in final_specs.items():
        report_paths[candidate].append(spec["path"])
        lineage["fragments"][candidate].append(spec)
    # Preserve lineage links for rows even when a run had no detailed report.
    lineage["identity_chains"] = final_chains
    for chain in final_chains.values():
        for entry in chain:
            if entry.get("execution_commit") not in {
                ORIGINAL_EXECUTION,
                CONTINUATION_EXECUTION,
                final.get("execution_commit"),
            }:
                raise ExportError("La cadena de identidades contiene un SHA de ejecución no aprobado")
    lineage.update(
        {
            "lineage_mode": "finalization",
            "finalization_plan_sha256": plan_sha,
            "finalization_campaign_identity_hash": final_campaign_hash,
            "finalization_execution_commit": final.get("execution_commit"),
            "finalization_ledger_sha256": final_ledger_sha,
            "recovery_sha256": source_hashes["recovery"],
            "progress_sha256": source_hashes["sol_low_progress"],
            "finalization_response_count_ceiling": 59,
        }
    )
    return report_paths, lineage
