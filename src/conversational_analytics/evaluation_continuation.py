"""Offline preparation for a no-replay continuation with aggregate usage evidence."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

from .evaluation_campaign import (
    CAMPAIGN_CANDIDATES,
    STAGE2_EXPECTED_CASE_IDS,
    STAGE2_RESERVE_USD,
    _canonical,
    _digest,
    campaign_run_id,
)

STAGE2_APPROVED_MODEL_CATALOG_SHA256 = "9744c985f051c898a8af6e8d3c8766c6885e77d8a13d55b72e30427b15468d4c"


def _validate_source_report(
    report: Mapping[str, Any],
    *,
    source_run: Mapping[str, Any],
    source_run_identity_hash: str,
    attempted_case_ids: Sequence[str],
    known_spend_usd: float,
) -> tuple[int, int]:
    """Bind the detailed source report to the partial ledger and its lower bounds."""
    if report.get("run_identity_hash") != source_run_identity_hash:
        raise ValueError("El reporte no está ligado a la identidad original de la corrida")
    if _canonical(report.get("run_identity", {})) != _canonical(source_run.get("identity", {})):
        raise ValueError("La identidad del reporte difiere de la corrida fallida del ledger")
    if report.get("case_count") != len(STAGE2_EXPECTED_CASE_IDS) or report.get("run_status") == "completed":
        raise ValueError("El reporte no conserva el estado parcial de la corrida original")
    if report.get("campaign_identity_hash") is None:
        raise ValueError("El reporte no conserva la identidad de campaña")
    models = report.get("models")
    if not isinstance(models, list) or len(models) != 1 or not isinstance(models[0], Mapping):
        raise ValueError("El reporte fuente debe contener un solo modelo Luna-medium")
    model = models[0]
    identity = source_run.get("identity", {})
    if report.get("candidate_models") != [identity.get("candidate")]:
        raise ValueError("El reporte no identifica únicamente el candidato Luna-medium")
    for key in ("candidate", "model", "reasoning_effort", "run_identity"):
        if key == "run_identity":
            matches = _canonical(model.get(key, {})) == _canonical(identity)
        else:
            matches = model.get(key) == identity.get(key)
        if not matches:
            raise ValueError(f"El reporte fuente cambió el candidato/modelo/esfuerzo: {key}")
    if model.get("spent_unknown") is not True:
        raise ValueError("El reporte no conserva el gasto desconocido de la corrida fallida")
    rows = model.get("cases")
    if not isinstance(rows, list) or [str(row.get("case_id", "")) for row in rows] != list(
        attempted_case_ids
    ):
        raise ValueError("Las filas del reporte no coinciden en orden con los casos intentados del ledger")
    complete_rows = rows[:-1]
    failed_row = rows[-1]
    input_tokens = 0
    output_tokens = 0
    known_cost = 0.0
    for row in complete_rows:
        if row.get("model_turn_completed") is not True or row.get("usage_complete") is not True:
            raise ValueError("El reporte no conserva ocho respuestas y usos completos")
        for key in ("input_tokens", "output_tokens"):
            value = row.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("Una respuesta completa no conserva tokens explícitos")
        cost = row.get("estimated_cost_usd")
        if (
            isinstance(cost, bool)
            or not isinstance(cost, (int, float))
            or not math.isfinite(cost)
            or cost < 0
        ):
            raise ValueError("Una respuesta completa no conserva costo estimado válido")
        input_tokens += row["input_tokens"]
        output_tokens += row["output_tokens"]
        known_cost += float(cost)
    if (
        failed_row.get("status") != "provider_error"
        or failed_row.get("model_turn_completed") is not False
        or failed_row.get("usage_complete") is not False
        or failed_row.get("input_tokens") is not None
        or failed_row.get("output_tokens") is not None
        or failed_row.get("estimated_cost_usd") is not None
    ):
        raise ValueError("La fila fallida debe conservar uso y costo individuales desconocidos")
    if not math.isclose(known_cost, known_spend_usd, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("Los costos de las ocho filas completas no suman el gasto conocido del ledger")
    if not math.isclose(
        float(report.get("known_estimated_cost_usd", -1)), known_spend_usd, rel_tol=0.0, abs_tol=1e-9
    ):
        raise ValueError("El total conocido del reporte no coincide con el ledger")
    totals = model.get("token_totals")
    if not isinstance(totals, Mapping):
        raise ValueError("El reporte no conserva los totales de tokens conocidos")
    if (
        totals.get("usage_complete_case_count") != 8
        or totals.get("turn_count") != 9
        or totals.get("known_input_tokens_lower_bound") != input_tokens
        or totals.get("known_output_tokens_lower_bound") != output_tokens
    ):
        raise ValueError("Los totales de tokens no concilian con las ocho filas completas")
    return input_tokens, output_tokens


def prepare_stage2_continuation(
    planned_runs: Sequence[Mapping[str, Any]],
    source_state: Mapping[str, Any],
    *,
    usage_reconciliation: Mapping[str, Any],
    evidence_bytes: bytes | None,
    source_ledger_bytes: bytes | None,
    source_ledger_sha256: str,
    source_report_bytes: bytes | None,
    source_report_sha256: str,
    model_catalog_bytes: bytes,
    model_catalog: Mapping[str, Any],
) -> dict[str, Any]:
    """Select only unused slots, preserving the source ledger and reports.

    The failed slot is excluded along with every other started slot. A root
    The owner-reported daily aggregate binds to the original campaign artifacts,
    while usage and cost for the individual failed turn stay unknown. This
    function performs no provider reads or writes. SHA-256 checks bind supplied
    bytes but do not prove their external provenance.
    """
    if source_state.get("status") != "stopped_unknown_spend" or source_state.get("spent_unknown") is not True:
        raise ValueError("La continuación requiere un ledger stage2 detenido por gasto desconocido")
    if source_state.get("active_run_id") is not None:
        raise ValueError("La corrida original conserva un run activo; no se prepara continuación")
    if source_state.get("budget_usd") != STAGE2_RESERVE_USD:
        raise ValueError("El ledger original no corresponde a la reserva stage2 autorizada")
    source_identity = source_state.get("identity")
    if not isinstance(source_identity, Mapping) or source_state.get("identity_hash") != _digest(
        source_identity
    ):
        raise ValueError("La identidad del ledger original no es íntegra")
    if not isinstance(source_ledger_bytes, bytes) or not source_ledger_bytes:
        raise ValueError("Falta el artefacto privado del ledger original")
    if hashlib.sha256(source_ledger_bytes).hexdigest() != source_ledger_sha256:
        raise ValueError("El hash del artefacto del ledger no coincide")
    try:
        source_ledger_artifact = json.loads(source_ledger_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("El ledger privado debe ser JSON UTF-8 válido") from error
    ledger_view = dict(source_state)
    ledger_view.pop("source_ledger_sha256", None)
    if source_ledger_artifact != ledger_view:
        raise ValueError("El artefacto privado no representa el ledger suministrado")
    if source_identity.get("budget_usd") != STAGE2_RESERVE_USD:
        raise ValueError("La identidad original no fija el presupuesto stage2 completo")

    by_run_id = {str(run.get("run_id")): run for run in planned_runs}
    expected_ids = {campaign_run_id(2, candidate, "proposed", 1) for candidate in CAMPAIGN_CANDIDATES}
    if len(by_run_id) != 4 or set(by_run_id) != expected_ids:
        raise ValueError("La continuación requiere los cuatro slots stage2 originales")
    source_runs = source_identity.get("runs")
    source_hashes = source_identity.get("run_identity_hashes")
    if (
        not isinstance(source_runs, list)
        or not isinstance(source_hashes, list)
        or len(source_runs) != 4
        or len(source_hashes) != 4
    ):
        raise ValueError("El ledger original no conserva las cuatro identidades stage2")
    source_by_id = {
        str(identity.get("run_id")): identity for identity in source_runs if isinstance(identity, Mapping)
    }
    if set(source_by_id) != set(by_run_id):
        raise ValueError("El conjunto original de slots no coincide con el plan actual")
    if any(_digest(identity) != source_hashes[index] for index, identity in enumerate(source_runs)):
        raise ValueError("Los hashes de run del ledger original no coinciden")
    case_ids = list(STAGE2_EXPECTED_CASE_IDS)
    for run_id, planned in by_run_id.items():
        identity = planned.get("identity")
        if not isinstance(identity, Mapping) or _digest(identity) != planned.get("identity_hash"):
            raise ValueError("La identidad planificada no coincide con su hash")
        commit = identity.get("execution_commit")
        if (
            not isinstance(commit, str)
            or len(commit) != 40
            or any(char not in "0123456789abcdef" for char in commit)
        ):
            raise ValueError("La identidad planificada debe fijar el SHA de ejecución")
        if list(planned.get("case_ids", [])) != case_ids or identity.get("case_ids_hash") != _digest(
            case_ids
        ):
            raise ValueError("Los IDs planeados no coinciden con la cohorte congelada")
        historical = dict(source_by_id[run_id])
        current = dict(identity)
        historical.pop("execution_commit", None)
        current.pop("execution_commit", None)
        if _canonical(historical) != _canonical(current):
            raise ValueError("El plan stage2 actual no coincide con la fuente de la corrida original")

    completed = source_state.get("completed_runs")
    if not isinstance(completed, Mapping) or not completed:
        raise ValueError("El ledger original no registra slots ya iniciados")
    started_ids = {str(run_id) for run_id in completed}
    if not started_ids <= set(by_run_id):
        raise ValueError("El ledger original contiene un slot fuera del plan stage2")
    incomplete = [(run_id, run) for run_id, run in completed.items() if not run.get("complete")]
    if len(incomplete) != 1:
        raise ValueError("La fuente debe contener exactamente un slot incompleto")
    failed_run_id, failed_run = incomplete[0]
    if failed_run.get("stopped_reason") != "provider_error" or failed_run.get("spent_unknown") is not True:
        raise ValueError("El slot incompleto no es un fallo terminal con gasto desconocido")
    if _canonical(failed_run.get("identity", {})) != _canonical(source_by_id[failed_run_id]):
        raise ValueError("La identidad del slot fallido no coincide con el ledger original")
    failed_case_rows = failed_run.get("cases", [])
    recorded_case_ids = [str(case.get("case_id", "")) for case in failed_case_rows]
    original_case_ids = list(by_run_id[failed_run_id]["case_ids"])
    if len(recorded_case_ids) != 9 or recorded_case_ids != original_case_ids[:9]:
        raise ValueError("Los casos guardados no son un prefijo exacto del slot fallido")
    if (
        sum(
            case.get("model_turn_completed") is True and case.get("usage_complete") is True
            for case in failed_case_rows
        )
        != 8
    ):
        raise ValueError("La corrida parcial debe contener ocho respuestas con uso completo")
    failed_cases = [
        case
        for case in failed_case_rows
        if case.get("status") == "provider_error" and case.get("usage_complete") is False
    ]
    if len(failed_cases) != 1 or recorded_case_ids[-1:] != [str(failed_cases[0].get("case_id", ""))]:
        raise ValueError("La fuente no identifica exactamente un caso fallido sin uso completo")
    failed_case_id = str(failed_cases[0].get("case_id", ""))

    for run_id, run in completed.items():
        if run_id == failed_run_id:
            continue
        source_run_identity = source_by_id[run_id]
        if _canonical(run.get("identity", {})) != _canonical(source_run_identity):
            raise ValueError("La corrida completa no está ligada a su identidad original")
        expected_run_hash = source_hashes[
            next(index for index, identity in enumerate(source_runs) if identity.get("run_id") == run_id)
        ]
        if run.get("identity_hash") != expected_run_hash:
            raise ValueError("La corrida completa no conserva el hash de identidad original")
        if run.get("complete") is not True:
            raise ValueError("La corrida marcada completa no tiene estado completo")
        rows = run.get("cases", [])
        if [str(case.get("case_id", "")) for case in rows] != case_ids:
            raise ValueError("Una corrida completa no contiene los 15 IDs congelados, en orden")
        if any(
            case.get("model_turn_completed") is not True or case.get("usage_complete") is not True
            for case in rows
        ):
            raise ValueError("Una corrida completa contiene respuesta o uso incompleto")
        cost = run.get("known_estimated_cost_usd")
        if (
            isinstance(cost, bool)
            or not isinstance(cost, (int, float))
            or not math.isfinite(cost)
            or cost < 0
        ):
            raise ValueError("Una corrida completa no conserva costo conocido válido")

    # Pin the full catalog to the exact Git blob used for the frozen campaign.
    # The identity's prices below also cross-check candidate rates.
    if hashlib.sha256(model_catalog_bytes).hexdigest() != STAGE2_APPROVED_MODEL_CATALOG_SHA256:
        raise ValueError("El archivo de tarifas no coincide con el catálogo del commit autorizado")
    try:
        catalog_from_bytes = json.loads(model_catalog_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("El catálogo debe ser JSON UTF-8 válido") from error
    if catalog_from_bytes != model_catalog:
        raise ValueError("El catálogo parseado no coincide con los bytes fijados")
    prices = source_identity.get("prices")
    if not isinstance(prices, Mapping):
        raise ValueError("La campaña original no conserva las tarifas autorizadas")
    for run in by_run_id.values():
        candidate = run["identity"]["candidate"]
        model = run["identity"]["model"]
        pricing = model_catalog.get("models", {}).get(model)
        expected_prices = prices.get(candidate)
        if (
            not isinstance(pricing, Mapping)
            or not isinstance(expected_prices, list)
            or len(expected_prices) != 2
            or expected_prices
            != [pricing.get("input_usd_per_million"), pricing.get("output_usd_per_million")]
        ):
            raise ValueError("Las tarifas del catálogo no coinciden con las fijadas por la campaña")

    if not isinstance(source_report_bytes, bytes) or not source_report_bytes:
        raise ValueError("Falta el reporte privado de la campaña original")
    if hashlib.sha256(source_report_bytes).hexdigest() != source_report_sha256:
        raise ValueError("El hash del reporte privado no coincide")
    try:
        source_report = json.loads(source_report_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("El reporte privado debe ser JSON UTF-8 válido") from error
    if not isinstance(source_report, Mapping):
        raise ValueError("El reporte privado no es un objeto")
    source_report_identity_hash = source_report.get("campaign_identity_hash")
    if source_report_identity_hash != source_state["identity_hash"]:
        raise ValueError("El reporte privado no pertenece a la campaña original")
    failed_identity_hash = source_hashes[
        next(index for index, identity in enumerate(source_runs) if identity.get("run_id") == failed_run_id)
    ]
    source_lower_bound_tokens = _validate_source_report(
        source_report,
        source_run=failed_run,
        source_run_identity_hash=failed_identity_hash,
        attempted_case_ids=recorded_case_ids,
        known_spend_usd=float(source_state["known_spend_usd"]),
    )

    if not isinstance(evidence_bytes, bytes) or not evidence_bytes:
        raise ValueError("Falta la attestación privada de uso agregado del dueño")
    evidence_hash = hashlib.sha256(evidence_bytes).hexdigest()
    if usage_reconciliation.get("evidence_sha256") != evidence_hash:
        raise ValueError("El hash de evidencia no coincide con los bytes privados recibidos")
    try:
        evidence = json.loads(evidence_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("La evidencia privada debe ser un objeto JSON UTF-8 válido") from error
    if not isinstance(evidence, Mapping):
        raise ValueError("La evidencia privada no es un objeto de uso")

    if usage_reconciliation.get("status") != "owner_confirmed_aggregate":
        raise ValueError("Solo se acepta la attestación agregada confirmada por el dueño")
    if usage_reconciliation.get("source_campaign_identity_hash") != source_state["identity_hash"]:
        raise ValueError("La attestación no pertenece a la campaña original")
    owner = evidence.get("owner_attestation")
    source_evidence = evidence.get("source_identity")
    spend_evidence = evidence.get("reconciliation")
    if (
        not isinstance(owner, Mapping)
        or not isinstance(source_evidence, Mapping)
        or not isinstance(spend_evidence, Mapping)
    ):
        raise ValueError("La evidencia privada no conserva attestación, fuente y spend")
    if owner.get("source") != "owner_reported_OpenAI_Usage":
        raise ValueError("La evidencia no identifica el Usage agregado reportado por el dueño")
    if owner.get("aggregate_date") != "2026-10-10" or owner.get("model") != "gpt-6-luna":
        raise ValueError("La evidencia no corresponde al día y modelo reportados")
    if owner.get("includes_failed_call") is not True:
        raise ValueError("La evidencia no confirma cobertura de la llamada fallida")
    if not owner.get("exact_question") or not owner.get("exact_owner_answer"):
        raise ValueError("La attestación privada no conserva la confirmación owner-reported")
    if owner.get("external_usage_independently_verified") is not False:
        raise ValueError("El uso owner-reported no debe presentarse como verificación externa")
    for key, expected in (
        ("campaign_identity_hash", source_state["identity_hash"]),
        ("campaign_ledger_sha256", source_ledger_sha256),
        ("report_sha256", source_report_sha256),
        ("run_identity_hash", failed_identity_hash),
        ("execution_commit", failed_run.get("identity", {}).get("execution_commit")),
    ):
        if source_evidence.get(key) != expected:
            raise ValueError(f"La attestación no está ligada a la fuente original: {key}")
    if source_report.get("run_identity_hash") != failed_identity_hash:
        raise ValueError("El reporte no está ligado a la identidad original de la corrida")
    if (
        usage_reconciliation.get("source_ledger_sha256") != source_ledger_sha256
        or usage_reconciliation.get("source_report_sha256") != source_report_sha256
    ):
        raise ValueError("La reconciliación no está ligada a los bytes originales")
    if (
        spend_evidence.get("failed_case_cost_estimate_usd") is not None
        or spend_evidence.get("invoice_total_usd") is not None
        or spend_evidence.get("failed_case_individual_usage") is not None
    ):
        raise ValueError("La attestación no debe afirmar importe exacto de factura o fallo")
    if (
        spend_evidence.get("known_completed_case_cost_estimate_usd") != source_state.get("known_spend_usd")
        or spend_evidence.get("attempted_responses") != 9
        or spend_evidence.get("complete_responses") != 8
        or spend_evidence.get("aggregate_tokens_match_known_case_lower_bounds") is not True
    ):
        raise ValueError("La attestación no conserva el estimado conocido original")
    token_keys = ("input_tokens", "output_tokens")
    tokens = tuple(owner.get(key) for key in token_keys)
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in tokens):
        raise ValueError("El agregado requiere tokens de entrada/salida enteros no negativos")
    expected_tokens = (408_550, 7_065)
    if tokens != expected_tokens:
        raise ValueError("Los tokens agregados no coinciden con la confirmación registrada")
    if source_lower_bound_tokens != tokens:
        raise ValueError("El agregado diario no concilia con los lower bounds de ocho respuestas conocidas")

    model = "gpt-6-luna"
    pricing = model_catalog.get("models", {}).get(model)
    if not isinstance(pricing, Mapping):
        raise ValueError("Falta el modelo/tarifa versionada del agregado")
    # Daily aggregate tokens have no per-request shape, so never apply a
    # long-context threshold or multiplier to them. Use the frozen cache-write
    # rate as a conservative aggregate estimate, without assigning it to a turn.
    input_multiplier = float(pricing["cache_write_input_multiplier"])
    aggregate_cost = (
        tokens[0] * float(pricing["input_usd_per_million"]) * input_multiplier
        + tokens[1] * float(pricing["output_usd_per_million"])
    ) / 1_000_000
    prior_spend = source_state.get("known_spend_usd")
    if (
        isinstance(prior_spend, bool)
        or not isinstance(prior_spend, (int, float))
        or not math.isfinite(prior_spend)
        or prior_spend < 0
    ):
        raise ValueError("El gasto conocido original no es válido")
    spend_rows = [row.get("known_estimated_cost_usd") for row in completed.values()]
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value < 0
        for value in spend_rows
    ) or not math.isclose(sum(spend_rows), float(prior_spend), rel_tol=0.0, abs_tol=1e-9):
        raise ValueError("El gasto conocido no coincide con las corridas guardadas")
    # The daily aggregate includes the source campaign's known turns. Taking
    # the maximum avoids counting those tokens twice while preserving a lower
    # bound at least as high as the known source spend.
    accounted_spend = max(float(prior_spend), aggregate_cost)
    if accounted_spend >= STAGE2_RESERVE_USD:
        raise ValueError("No queda presupuesto stage2 tras reconciliar el turno fallido")

    complete_ids = {str(run_id) for run_id, run in completed.items() if run.get("complete") is True}
    source_cases = [case for run in completed.values() for case in run.get("cases", [])]
    source_completed_responses = sum(bool(case.get("model_turn_completed")) for case in source_cases)
    source_unresolved_failures = sum(
        case.get("status") == "provider_error" and case.get("usage_complete") is False
        for case in source_cases
    )
    selected_specs: list[tuple[str, list[str], list[str] | None]] = []
    for run_id, planned in by_run_id.items():
        if run_id in complete_ids:
            continue
        if run_id == failed_run_id:
            attempted_ids = list(recorded_case_ids)
            eligible_case_ids = list(planned["case_ids"])[len(attempted_ids) :]
            if eligible_case_ids:
                selected_specs.append((run_id, eligible_case_ids, attempted_ids))
        else:
            selected_specs.append((run_id, list(planned["case_ids"]), None))
    if not selected_specs:
        raise ValueError("No quedan slots stage2 sin iniciar")
    completed_run_ids = sorted(complete_ids)
    selected_slots = [
        {"source_run_id": run_id, "case_ids": case_ids} for run_id, case_ids, _ in selected_specs
    ]
    continuation_id = _digest(
        {
            "source_campaign_identity_hash": source_state["identity_hash"],
            "accounted_spend_usd": accounted_spend,
            "selected_slots": selected_slots,
        }
    )[:16]
    continuation_runs = []
    for source_run_id, case_ids, attempted_ids in selected_specs:
        run = deepcopy(dict(by_run_id[source_run_id]))
        identity = dict(run["identity"])
        continued_run_id = f"{source_run_id}-cont-{continuation_id}"
        identity["run_id"] = continued_run_id
        identity["case_ids_hash"] = _digest(case_ids)
        identity["continuation"] = {
            "continuation_id": continuation_id,
            "source_campaign_identity_hash": source_state["identity_hash"],
            "accounted_spend_usd": accounted_spend,
            "source_run_id": source_run_id,
            "skipped_case_ids": attempted_ids or [],
            "failed_case_id_skipped": failed_case_id if source_run_id == failed_run_id else None,
            "completed_run_ids_excluded": completed_run_ids,
        }
        run["identity"] = identity
        run["identity_hash"] = _digest(identity)
        run.update(identity)
        run["prompt"] = str(by_run_id[source_run_id]["prompt"])
        run["case_ids"] = case_ids
        run["case_count"] = len(case_ids)
        run["user_message_count"] = len(case_ids)
        continuation_runs.append(run)
    return {
        "continuation_id": continuation_id,
        "source_campaign_identity_hash": source_state["identity_hash"],
        "source_ledger_sha256": source_ledger_sha256,
        "source_report_sha256": source_report_sha256,
        "evidence_sha256": evidence_hash,
        "source_execution_commit": next(iter(source_by_id.values())).get("execution_commit"),
        "source_runs": [
            {
                "run_id": run_id,
                "candidate": source_by_id[run_id].get("candidate"),
                "identity": source_by_id[run_id],
                "identity_hash": source_hashes[
                    next(
                        index
                        for index, identity in enumerate(source_runs)
                        if identity.get("run_id") == run_id
                    )
                ],
                "started": run_id in completed,
                "case_ids": [
                    str(case.get("case_id", "")) for case in completed.get(run_id, {}).get("cases", [])
                ],
            }
            for run_id in sorted(source_by_id)
        ],
        "failed_run_id": failed_run_id,
        "failed_case_id": failed_case_id,
        "reconciled_failed_case_cost_usd": None,
        "daily_aggregate_estimated_cost_usd": aggregate_cost,
        "daily_aggregate_input_tokens": tokens[0],
        "daily_aggregate_output_tokens": tokens[1],
        "daily_aggregate_usage_scope": "daily_account_aggregate",
        "failed_case_usage": "unknown",
        "accounted_spend_usd": accounted_spend,
        "remaining_budget_usd": STAGE2_RESERVE_USD - accounted_spend,
        "completed_run_ids_excluded": completed_run_ids,
        "skipped_case_ids": list(recorded_case_ids),
        "case_count": sum(len(run["case_ids"]) for run in continuation_runs),
        "source_completed_response_count": source_completed_responses,
        "source_unresolved_failure_count": source_unresolved_failures,
        "candidate_case_slot_count": sum(len(run["case_ids"]) for run in planned_runs),
        "response_count_ceiling_if_continuation_completes": source_completed_responses
        + sum(len(run["case_ids"]) for run in continuation_runs),
        "runs": continuation_runs,
    }
