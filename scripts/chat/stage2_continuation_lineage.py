"""Private offline verification of F2.9 stage-2 continuation lineage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

import re

SHA = re.compile(r"^[a-f0-9]{40}$")


def _path_from_plan(section: dict[str, Any], error_type: type[ValueError], key: str, label: str) -> Path:
    value = section.get(key)
    if not isinstance(value, str) or not value:
        raise error_type(f"El plan no incluye ruta privada para {label}")
    return Path(value).resolve()


def validate_continuation_inputs(
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
    allow_interrupted_active_run: bool = False,
    allow_preflight_source_plan: bool = False,
) -> tuple[dict[str, Sequence[Path]], dict[str, Any]]:
    """Load and verify the explicit source-to-continuation provenance chain."""
    plan, plan_sha = read_json_with_hash(plan_path, "continuation plan")
    if plan.get("schema_version") != 1 or plan.get("kind") != "f2_9_stage2_continuation_plan":
        raise ExportError("El archivo no es un plan de continuación stage2 compatible")
    live_plan = plan.get("mode") == "live-campaign" and plan.get("provider_calls_now") is None
    pinned_preflight = (
        allow_preflight_source_plan
        and plan.get("mode") == "offline-preflight-only"
        and plan.get("provider_calls_now") == 0
    )
    if not (live_plan or pinned_preflight):
        raise ExportError("El plan aún no tiene una continuación live registrada")
    source, continuation, billing = (
        plan.get("source"), plan.get("continuation"), plan.get("billing_reconciliation")
    )
    if not all(isinstance(item, dict) for item in (source, continuation, billing)):
        raise ExportError("El plan de continuación no conserva source, continuation y billing")

    source_ledger_path = _path_from_plan(source, ExportError, "ledger_path", "ledger fuente")
    source_report_path = _path_from_plan(source, ExportError, "report_path", "reporte fuente")
    continuation_ledger_path = _path_from_plan(continuation, ExportError, "ledger_path", "ledger de continuación")
    source_ledger, source_ledger_sha = read_json_with_hash(source_ledger_path, "ledger fuente")
    source_report, source_report_sha = read_json_with_hash(source_report_path, "reporte fuente")
    continuation_ledger, continuation_ledger_sha = read_json_with_hash(
        continuation_ledger_path, "ledger de continuación"
    )
    try:
        evidence_bytes = owner_evidence_path.read_bytes()
        evidence = json.loads(evidence_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ExportError("No se pudo leer la attestación privada de uso del dueño") from exc
    if not isinstance(evidence, dict):
        raise ExportError("La evidencia de uso del dueño debe ser un objeto JSON")
    evidence_sha = hashlib.sha256(evidence_bytes).hexdigest()

    source_identity = source_ledger.get("identity")
    source_campaign_hash = source_ledger.get("identity_hash")
    if not isinstance(source_identity, dict) or source_campaign_hash != digest(source_identity):
        raise ExportError("La identidad del ledger original no coincide con sus bytes")
    if source_ledger.get("status") != "stopped_unknown_spend" or source_ledger.get("spent_unknown") is not True:
        raise ExportError("El ledger fuente no es el piloto detenido con gasto desconocido")
    if source.get("campaign_identity_hash") != source_campaign_hash:
        raise ExportError("El plan no está ligado al hash del ledger original")
    if source.get("ledger_sha256") != source_ledger_sha:
        raise ExportError("El hash del ledger fuente no coincide con sus bytes")
    if source.get("report_sha256") != source_report_sha:
        raise ExportError("El hash del reporte fuente no coincide con sus bytes")
    if billing.get("source_ledger_sha256") != source_ledger_sha or billing.get("source_report_sha256") != source_report_sha:
        raise ExportError("La reconciliación de uso no está ligada a los bytes del piloto original")
    if billing.get("evidence_sha256") != evidence_sha or source.get("owner_evidence_sha256") != evidence_sha:
        raise ExportError("El hash de la evidencia de uso no coincide con sus bytes")
    if (
        billing.get("status") != "owner_confirmed_aggregate"
        or billing.get("usage_scope") != "daily_account_aggregate"
        or billing.get("individual_failed_call_usage") != "unknown"
        or billing.get("invoice_total_usd") is not None
    ):
        raise ExportError("La conciliación debe preservar agregado reportado y uso individual desconocido")
    owner_attestation = evidence.get("owner_attestation")
    evidence_source = evidence.get("source_identity")
    reconciliation = evidence.get("reconciliation")
    if not all(isinstance(item, dict) for item in (owner_attestation, evidence_source, reconciliation)):
        raise ExportError("La evidencia owner-reported no conserva attestación, fuente y conciliación")
    if (
        evidence.get("schema_version") != 1
        or evidence.get("kind") != "private_owner_usage_confirmation"
        or owner_attestation.get("source") != "owner_reported_OpenAI_Usage"
        or owner_attestation.get("aggregate_date") != "2026-10-10"
        or owner_attestation.get("model") != "gpt-6-luna"
        or owner_attestation.get("includes_failed_call") is not True
        or owner_attestation.get("external_usage_independently_verified") is not False
        or evidence_source.get("campaign_identity_hash") != source_campaign_hash
        or evidence_source.get("campaign_ledger_sha256") != source_ledger_sha
        or evidence_source.get("report_sha256") != source_report_sha
        or evidence_source.get("execution_commit") != source.get("execution_commit")
        or evidence_source.get("run_identity_hash") != source.get("run_identity_hash")
        or evidence_source.get("pilot_candidate_models_in_source_report") != ["gpt-6-luna@medium"]
        or evidence_source.get("source_report_model_entry_count") != 1
        or reconciliation.get("complete_responses") != 8
        or reconciliation.get("attempted_responses") != 9
        or reconciliation.get("failed_case") != "en_am_rask"
        or reconciliation.get("failed_case_individual_usage") is not None
        or reconciliation.get("failed_case_cost_estimate_usd") is not None
        or reconciliation.get("invoice_total_usd") is not None
        or reconciliation.get("aggregate_tokens_match_known_case_lower_bounds") is not True
        or reconciliation.get("known_completed_case_cost_estimate_usd") != source_ledger.get("known_spend_usd")
    ):
        raise ExportError("La evidencia owner-reported no corresponde a la ejecución fuente")
    tokens = (owner_attestation.get("input_tokens"), owner_attestation.get("output_tokens"))
    if tokens != (408_550, 7_065) or tuple(
        billing.get(key) for key in ("daily_aggregate_input_tokens", "daily_aggregate_output_tokens")
    ) != tokens:
        raise ExportError("Los tokens agregados no coinciden con la evidencia autorizada")

    fixture_bytes = fixture_path.read_bytes()
    fixture_sha = hashlib.sha256(fixture_bytes).hexdigest()
    if continuation.get("fixture_sha256") != fixture_sha:
        raise ExportError("El plan y el fixture congelado no coinciden por SHA-256")
    continuation_runs = continuation.get("runs")
    source_runs = source.get("runs")
    if not isinstance(source_runs, list) or not isinstance(continuation_runs, list):
        raise ExportError("El plan no conserva la identidad completa de las corridas")
    source_run_identities = source_identity.get("runs")
    source_run_hashes = source_identity.get("run_identity_hashes")
    if not isinstance(source_run_identities, list) or not isinstance(source_run_hashes, list):
        raise ExportError("El ledger fuente no conserva hashes de las cuatro corridas")
    source_by_id = {str(item.get("run_id")): item for item in source_run_identities if isinstance(item, dict)}
    source_hash_by_id = {str(item.get("run_id")): source_run_hashes[index]
                         for index, item in enumerate(source_run_identities) if isinstance(item, dict)}
    plan_source_by_id = {str(item.get("run_id")): item for item in source_runs if isinstance(item, dict)}
    if (
        len(source_by_id) != 4
        or set(source_by_id) != set(plan_source_by_id)
        or any(digest(identity) != source_hash_by_id[run_id] for run_id, identity in source_by_id.items())
    ):
        raise ExportError("El plan fuente no contiene exactamente los cuatro slots originales")
    source_completed = source_ledger.get("completed_runs", {})
    if not isinstance(source_completed, dict) or len(source_completed) != 1:
        raise ExportError("El ledger fuente no conserva sus corridas iniciadas")
    for run_id, identity in source_by_id.items():
        source_run = source_completed.get(run_id)
        plan_row = plan_source_by_id[run_id]
        rows = source_run.get("cases", []) if isinstance(source_run, dict) else []
        source_case_ids = [str(row.get("case_id", "")) for row in rows if isinstance(row, dict)]
        if (
            canonical(plan_row.get("identity")) != canonical(identity)
            or plan_row.get("identity_hash") != source_hash_by_id[run_id]
            or plan_row.get("started") != isinstance(source_run, dict)
            or plan_row.get("case_ids") != source_case_ids
        ):
            raise ExportError("El manifiesto de slots fuente diverge del ledger original")
        if identity.get("execution_commit") != source.get("execution_commit"):
            raise ExportError("El SHA fuente no coincide en todas las identidades originales")
    if source_report.get("campaign_identity_hash") != source_campaign_hash:
        raise ExportError("El reporte fuente no pertenece al campaign hash original")
    source_indexed, source_meta, source_identity_hash, source_report_campaign = report_cases(
        source_report, source_report_path
    )
    report_identity = source_meta["identity"]
    report_candidate = source_meta["model"].get("candidate")
    matching_source_runs = [run_id for run_id, identity in source_by_id.items()
                            if identity.get("candidate") == report_candidate]
    if (
        len(matching_source_runs) != 1
        or canonical(report_identity) != canonical(source_by_id[matching_source_runs[0]])
        or source_identity_hash != source_hash_by_id[matching_source_runs[0]]
        or source.get("run_identity_hash") != source_hash_by_id[matching_source_runs[0]]
        or source_report_campaign != source_campaign_hash
    ):
        raise ExportError("El reporte fuente no corresponde a la identidad original fijada")
    source_run = source_completed.get(matching_source_runs[0])
    if not isinstance(source_run, dict):
        raise ExportError("El reporte fuente no tiene slot real en el ledger original")
    if set(source_completed) != {matching_source_runs[0]}:
        raise ExportError("El piloto original debe conservar solo el slot Luna medium iniciado")
    source_report_rows = source_meta["model"].get("cases", [])
    source_checkpoint_rows = source_run.get("cases", [])
    if [row.get("case_id") for row in source_report_rows] != [row.get("case_id") for row in source_checkpoint_rows]:
        raise ExportError("Las filas del reporte fuente no coinciden con el checkpoint original")
    if any(
        report_row.get("model_turn_completed") is not checkpoint_row.get("model_turn_completed")
        or ("status" in checkpoint_row and report_row.get("status") != checkpoint_row.get("status"))
        for report_row, checkpoint_row in zip(source_report_rows, source_checkpoint_rows, strict=True)
    ):
        raise ExportError("El estado por caso del reporte fuente no coincide con el checkpoint original")
    failed_rows = [row for row in source_report_rows if row.get("model_turn_completed") is not True]
    full_case_ids = [case["id"] for case in fixture_cases(fixture)]
    attempted_source_ids = [str(row.get("case_id")) for row in source_report_rows]
    if (
        report_candidate != "gpt-6-luna@medium"
        or len(source_report_rows) != 9
        or attempted_source_ids != full_case_ids[:9]
        or sum(row.get("model_turn_completed") is True for row in source_report_rows) != 8
        or len(failed_rows) != 1
        or failed_rows[0].get("case_id") != "en_am_rask"
        or failed_rows[0].get("status") != "provider_error"
    ):
        raise ExportError("El reporte fuente debe conservar ocho respuestas y el fallo original sin replay")

    continuation_identity = continuation_ledger.get("identity")
    continuation_campaign_hash = continuation_ledger.get("identity_hash")
    if not isinstance(continuation_identity, dict) or continuation_campaign_hash != digest(continuation_identity):
        raise ExportError("La identidad del ledger de continuación no coincide con sus bytes")
    if continuation.get("source_campaign_identity_hash") != source_campaign_hash:
        raise ExportError("El plan de continuación no apunta a la campaña fuente")
    active_run_id = continuation_ledger.get("active_run_id")
    if allow_interrupted_active_run:
        if (
            continuation_ledger.get("status") != "running"
            or not isinstance(active_run_id, str)
            or active_run_id not in {run.get("run_id") for run in continuation_runs}
        ):
            raise ExportError("El ledger interrumpido no conserva su corrida activa planeada")
    elif active_run_id is not None or continuation_ledger.get("status") not in {
        "completed", "stopped_campaign_budget", "stopped_provider_error", "stopped_unknown_spend",
    }:
        raise ExportError("El ledger de continuación aún tiene una corrida activa o estado no exportable")
    if continuation_identity.get("budget_usd") != billing.get("remaining_budget_usd"):
        raise ExportError("El ledger de continuación no usa exactamente el presupuesto restante conciliado")
    planned_run_ids = [str(run.get("run_id")) for run in continuation_runs]
    planned_identities = [run.get("identity") for run in continuation_runs]
    planned_hashes = [run.get("identity_hash") for run in continuation_runs]
    actual_completed = continuation_ledger.get("completed_runs", {})
    if not isinstance(actual_completed, dict):
        raise ExportError("El ledger de continuación no conserva sus corridas iniciadas")
    if (
        continuation_identity.get("runs") != planned_identities
        or continuation_identity.get("run_identity_hashes") != planned_hashes
        or any(digest(identity) != declared_hash for identity, declared_hash in zip(planned_identities, planned_hashes, strict=True))
        or not set(actual_completed) <= set(planned_run_ids)
    ):
        raise ExportError("El ledger real no coincide exactamente con el plan de continuación")
    if allow_interrupted_active_run and active_run_id in actual_completed:
        raise ExportError("La corrida activa interrumpida también aparece como cerrada en el ledger")
    live_result = plan.get("live_result")
    if pinned_preflight and allow_interrupted_active_run:
        if live_result is not None:
            raise ExportError("El plan preflight interrumpido no debe afirmar una corrida live")
    elif not isinstance(live_result, dict) or live_result.get("identity_hash") != continuation_campaign_hash:
        raise ExportError("El plan no conserva el resultado del ledger de continuación por su hash")
    continuation_commit = continuation.get("execution_commit")
    if not isinstance(continuation_commit, str) or not SHA.fullmatch(continuation_commit):
        raise ExportError("El plan no fija un SHA de ejecución de continuación")
    if continuation_commit == source.get("execution_commit"):
        raise ExportError("La continuación debe conservar su SHA nuevo, distinto a la ejecución fuente")

    continuation_by_candidate: dict[str, dict[str, Any]] = {}
    identity_chains: dict[str, list[dict[str, Any]]] = {}
    for run in continuation_runs:
        identity = run.get("identity")
        if not isinstance(identity, dict) or run.get("identity_hash") != digest(identity):
            raise ExportError("Una identidad de continuación no coincide con su hash")
        candidate = identity.get("candidate")
        if candidate not in candidates or candidate in continuation_by_candidate:
            raise ExportError("El plan tiene candidatos faltantes o repetidos")
        source_run_id = identity.get("continuation", {}).get("source_run_id")
        original = source_by_id.get(str(source_run_id))
        if not isinstance(original, dict) or original.get("candidate") != candidate:
            raise ExportError("La corrida de continuación no está ligada a su candidato fuente")
        original_base = {key: value for key, value in original.items()
                         if key not in {"execution_commit", "run_id", "case_ids_hash"}}
        current_base = {key: value for key, value in identity.items()
                        if key not in {"execution_commit", "run_id", "case_ids_hash", "continuation"}}
        if canonical(original_base) != canonical(current_base):
            raise ExportError("La continuación cambió fixture, contexto, prompt, herramientas, límites o modelo")
        if (
            identity.get("execution_commit") != continuation_commit
            or identity.get("run_id") != f"{source_run_id}-cont-{continuation.get('continuation_id')}"
            or identity.get("case_fixture_hash") != digest(fixture_cases(fixture))
            or identity.get("data_version") != fixture.get("expected_versions", {}).get("data_version")
            or identity.get("semantic_version") != fixture.get("expected_versions", {}).get("semantic_version")
            or identity.get("stage") != 2
            or identity.get("prompt_variant") != "proposed"
            or identity.get("repetition") != 1
        ):
            raise ExportError("La identidad nueva no corresponde al plan congelado")
        selected_case_ids = list(run.get("case_ids", []))
        expected_continuation = identity.get("continuation", {})
        source_attempted = list(plan_source_by_id[str(source_run_id)].get("case_ids", []))
        if source_run_id == matching_source_runs[0] and set(selected_case_ids) & set(source_attempted):
            raise ExportError("La corrida Luna medium se traslapa con casos fuente ya intentados")
        if identity.get("case_ids_hash") != digest(selected_case_ids):
            raise ExportError("Los IDs de la corrida no coinciden con el plan de continuación")
        if source_run_id == matching_source_runs[0]:
            expected_selected = full_case_ids[len(source_attempted):]
            if (
                selected_case_ids != expected_selected
                or expected_continuation.get("skipped_case_ids") != source_attempted
                or expected_continuation.get("failed_case_id_skipped") != "en_am_rask"
            ):
                raise ExportError("La corrida Luna medium no excluye exactamente los nueve intentos fuente")
        elif (
            selected_case_ids != full_case_ids
            or expected_continuation.get("skipped_case_ids") != []
            or expected_continuation.get("failed_case_id_skipped") is not None
        ):
            raise ExportError("Una corrida sin intentos fuente no conserva los 15 casos originales")
        if expected_continuation.get("source_campaign_identity_hash") != source_campaign_hash:
            raise ExportError("La identidad nueva no apunta a la campaña fuente aprobada")
        continuation_by_candidate[candidate] = run
        source_id = str(source_run_id)
        identity_chains[candidate] = [
            {
                "lineage_role": "source",
                "campaign_identity_hash": source_campaign_hash,
                "identity_hash": source_hash_by_id[source_id],
                "execution_commit": source_by_id[source_id].get("execution_commit"),
                "identity": source_by_id[source_id],
            },
            {
                "lineage_role": "continuation",
                "campaign_identity_hash": continuation_campaign_hash,
                "identity_hash": run.get("identity_hash"),
                "execution_commit": continuation_commit,
                "identity": identity,
            },
        ]
    if set(continuation_by_candidate) != set(candidates):
        raise ExportError("El plan de continuación no incluye los cuatro candidatos")

    report_paths: dict[str, list[Path]] = {candidate: [] for candidate in candidates}
    fragments: dict[str, list[dict[str, Any]]] = {candidate: [] for candidate in candidates}
    for candidate in candidates:
        run = continuation_by_candidate[candidate]
        run_id = str(run["run_id"])
        if run_id not in actual_completed:
            continue
        actual = actual_completed[run_id]
        if (
            canonical(actual.get("identity")) != canonical(run.get("identity"))
            or digest(actual.get("identity")) != run.get("identity_hash")
            or (actual.get("identity_hash") is not None
                and actual.get("identity_hash") != run.get("identity_hash"))
        ):
            raise ExportError("El slot real de continuación no conserva su identidad y hash planeados")
        summary = actual.get("summary", {})
        report_path = Path(str(summary.get("report_path", ""))).resolve()
        if not report_path.is_file():
            raise ExportError("Falta el reporte detallado citado por el ledger de continuación")
        continuation_report, report_sha = read_json_with_hash(report_path, "reporte de continuación")
        indexed, metadata, identity_hash, campaign_hash = report_cases(continuation_report, report_path)
        if (
            continuation_report.get("mode") != "live-evaluation"
            or continuation_report.get("probe_only") is not False
            or canonical(metadata["identity"]) != canonical(run.get("identity"))
            or identity_hash != run.get("identity_hash")
            or continuation_report.get("run_identity_hash") != run.get("identity_hash")
            or (continuation_report.get("identity_hash") is not None
                and continuation_report.get("identity_hash") != run.get("identity_hash"))
            or campaign_hash != continuation_campaign_hash
        ):
            raise ExportError("El reporte de continuación no coincide con identidad/hash de corrida y campaña del ledger")
        expected_case_ids = list(run.get("case_ids", []))
        actual_case_rows = actual.get("cases", [])
        if [case_id for case_id in indexed if case_id in set(expected_case_ids)] != [
            row.get("case_id") for row in actual_case_rows
        ]:
            raise ExportError("El detalle por caso no coincide con el ledger real de continuación")
        if any(
            indexed[str(row.get("case_id"))].get("model_turn_completed") is not row.get("model_turn_completed")
            or ("status" in row and indexed[str(row.get("case_id"))].get("status") != row.get("status"))
            for row in actual_case_rows
        ):
            raise ExportError("El estado por caso del reporte no coincide con el ledger de continuación")
        if set(indexed) - set(expected_case_ids):
            raise ExportError("El reporte de continuación contiene IDs fuera de su plan")
        report_paths[candidate].append(report_path)
        fragments[candidate].append({
            "role": "continuation", "path": report_path, "sha256": report_sha,
            "identity": metadata["identity"], "identity_hash": identity_hash,
            "campaign_identity_hash": campaign_hash, "case_ids": list(indexed),
            "expected_case_ids": expected_case_ids,
            "ledger_run_id": run_id,
        })

    source_candidate = str(source_by_id[matching_source_runs[0]]["candidate"])
    report_paths[source_candidate].insert(0, source_report_path)
    fragments[source_candidate].insert(0, {
        "role": "source", "path": source_report_path, "sha256": source_report_sha,
        "identity": source_by_id[matching_source_runs[0]],
        "identity_hash": source_hash_by_id[matching_source_runs[0]],
        "campaign_identity_hash": source_campaign_hash,
        "case_ids": [str(row.get("case_id")) for row in source_report_rows],
        "expected_case_ids": full_case_ids,
    })
    if source_candidate != str(continuation_by_candidate[source_candidate]["identity"]["candidate"]):
        raise ExportError("El reporte fuente y su plan de continuación usan candidatos distintos")
    prompt_hashes = {item["identity"].get("prompt_content_hash") for chain in identity_chains.values() for item in chain}
    if len(prompt_hashes) != 1 or continuation.get("prompt_sha256") not in prompt_hashes:
        raise ExportError("El plan de continuación cambió el prompt efectivo")
    context_hash = digest([{"id": str(case.get("id", "")), "context": case.get("context", {})} for case in fixture_cases(fixture)])
    if continuation.get("context_sha256") != context_hash:
        raise ExportError("El contexto congelado no coincide con el plan de continuación")
    shared_identity_fields = ("data_version", "semantic_version", "source_fingerprint", "prompt_content_hash",
                              "tool_spec_hash", "limits", "text_verbosity")
    planned_identities = [chain[-1]["identity"] for chain in identity_chains.values()]
    reference = planned_identities[0]
    if any(any(identity.get(field) != reference.get(field) for field in shared_identity_fields)
           for identity in planned_identities[1:]):
        raise ExportError("Las corridas de continuación difieren en fixture, contexto, prompt, herramientas o límites")
    if (
        continuation.get("tool_specs_sha256") != reference.get("tool_spec_hash")
        or continuation.get("runtime_limits") != reference.get("limits")
        or any(identity.get("source_fingerprint") != reference.get("source_fingerprint") for identity in planned_identities)
    ):
        raise ExportError("El plan no conserva fixture, herramientas y límites congelados")
    lineage = {
        "plan_sha256": plan_sha,
        "source_campaign_identity_hash": source_campaign_hash,
        "source_execution_commit": source.get("execution_commit"),
        "source_ledger_sha256": source_ledger_sha,
        "source_report_sha256": source_report_sha,
        "owner_evidence_sha256": evidence_sha,
        "continuation_campaign_identity_hash": continuation_campaign_hash,
        "continuation_execution_commit": continuation_commit,
        "continuation_plan_mode": plan.get("mode"),
        "continuation_ledger_sha256": continuation_ledger_sha,
        "continuation_fragments": fragments,
        "fragments": fragments,
        "identity_chains": identity_chains,
        "source_case_ids": [str(row.get("case_id")) for row in source_report_rows],
    }
    return report_paths, lineage


