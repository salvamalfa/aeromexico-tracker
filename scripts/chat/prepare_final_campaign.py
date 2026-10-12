"""Offline-only F2.9 stage-3 campaign preflight.

This builder has no live execution path. It uses an explicit candidate profile,
the frozen 30-case business fixture, and the versioned price catalog to emit a
traceable plan. Provider calls and credential reads are always zero.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
DEFAULT_PROFILE = ROOT / "config/chat/f2_9_business_stage3_partial.json"
PUBLIC_CLOSEOUT = ROOT / "docs/chat/revision-fase-2/F2.9-cierre-etapa-2.json"
PUBLIC_CLOSEOUT_SHA256 = "bf03c82e52fcff3b89fbcf18794218300149ae6859950199a6fd90c56fdd522d"
EXPECTED_CASE_COUNT = 30
EXPECTED_CASE_HASH = "30fc0acfc5d9fee1ffffd3624209712dd8160806dae4d904c4310a8f53537640"
EXPECTED_MESSAGE_COUNT = 34
EXPECTED_PROFILE_STATUS = "offline_business_only_partial_preflight_pending_dependency_and_budget_gates"
EXPECTED_GATES = {
    "full_stage2_review_received": True,
    "business_fixture_hash_frozen_for_this_preflight": True,
    "f23_f24_f25_f26_f27_f28_integrated_and_reviewed": False,
    "30_case_gold_and_support_expectations_revalidated": False,
    "snapshot_and_semantic_versions_pinned_after_integration": False,
    "new_stage3_budget_approved_and_funded": False,
}


def _read_object(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"Se esperaba un objeto JSON: {path}")
    return value, hashlib.sha256(raw).hexdigest()


def _message_count(cases: list[dict[str, Any]]) -> int:
    count = 0
    for case in cases:
        turns = case.get("turns")
        if turns is None:
            turns = [case.get("question")]
        if not isinstance(turns, list) or not turns or any(
            not isinstance(turn, str) or not turn.strip() for turn in turns
        ):
            raise ValueError(f"Turnos inválidos en {case.get('id', '<sin id>')}")
        count += len(turns)
    return count


def _ceil_dollar(value: float) -> int:
    return math.ceil(value - 1e-10)


def _validate_measured_reference(profile: dict[str, Any]) -> dict[str, Any]:
    """Bind public stage-2 usage in a candidate profile to the pinned closeout."""
    closeout, closeout_hash = _read_object(PUBLIC_CLOSEOUT)
    if closeout_hash != PUBLIC_CLOSEOUT_SHA256:
        raise ValueError("El artefacto público de cierre F2.9 cambió; requiere revisión y nuevo pin")
    provenance = closeout.get("provenance")
    owner_choice = closeout.get("owner_choice")
    stage3 = closeout.get("stage3_plan")
    privacy = closeout.get("privacy")
    if not all(isinstance(item, dict) for item in (provenance, owner_choice, stage3, privacy)):
        raise ValueError("El cierre F2.9 fijado carece de provenance pública o límites de privacidad")
    expected_privacy = {
        "raw_answers_included": False,
        "alias_key_included": False,
        "question_level_ratings_included": False,
        "reviewer_notes_included": False,
    }
    if privacy != expected_privacy:
        raise ValueError("El cierre F2.9 no confirma exclusión de respuestas y datos de revisión")

    candidate = owner_choice.get("candidate")
    expected_hashes = {
        "final_report": provenance.get("sol_low_stage2_final_report_sha256"),
        "terminal_recovery": provenance.get("sol_low_recovered_turn_sha256"),
    }
    expected_tokens = {
        "completed_input_tokens": provenance.get("sol_low_measured_input_tokens"),
        "completed_output_tokens": provenance.get("sol_low_measured_output_tokens"),
    }
    for label, value in expected_hashes.items():
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError(f"El cierre F2.9 no contiene un SHA-256 válido para {label}")
    for label, value in expected_tokens.items():
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"El cierre F2.9 no contiene un total de tokens positivo para {label}")
    if (
        candidate != "gpt-6.1-sol@low"
        or stage3.get("candidate") != candidate
        or stage3.get("case_count") != EXPECTED_CASE_COUNT
        or stage3.get("user_messages_per_candidate") != EXPECTED_MESSAGE_COUNT
    ):
        raise ValueError("El cierre F2.9 no fija la selección y el alcance parcial de negocio esperados")

    reference = profile.get("measured_reference")
    if not isinstance(reference, dict):
        raise ValueError("El perfil no conserva measured_reference")
    if reference.get("stage") != "F2.9-stage-2" or reference.get("candidate") != candidate:
        raise ValueError("La procedencia de measured_reference no coincide con el cierre fijado")
    if reference.get("question_count") != 15:
        raise ValueError("La muestra medida debe conservar los 15 slots del cierre F2.9")
    for field, expected in expected_tokens.items():
        actual = reference.get(field)
        if isinstance(actual, bool) or not isinstance(actual, int) or actual <= 0:
            raise ValueError(f"{field} debe ser un total entero positivo de la fuente fijada")
        if actual != expected:
            raise ValueError(f"{field} no coincide con el total del cierre F2.9 fijado")
    hashes = reference.get("source_hashes")
    if not isinstance(hashes, dict) or set(hashes) != set(expected_hashes):
        raise ValueError("Los hashes de measured_reference no conservan las fuentes del cierre fijado")
    for name, expected in expected_hashes.items():
        actual = hashes.get(name)
        if not isinstance(actual, str) or not re.fullmatch(r"[0-9a-f]{64}", actual):
            raise ValueError(f"El SHA-256 de measured_reference no es válido: {name}")
        if actual != expected:
            raise ValueError(f"El SHA-256 de measured_reference no coincide con el cierre fijado: {name}")
    return reference


def build_plan(
    *,
    profile_path: Path,
    candidate_override: str | None = None,
    coverage_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile, profile_hash = _read_object(profile_path)
    fixture_path = ROOT / profile["fixture"]
    fixture, fixture_hash = _read_object(fixture_path)
    catalog_path = ROOT / "config/chat/models.json"
    catalog, catalog_hash = _read_object(catalog_path)
    candidate = candidate_override or profile.get("selected_candidate")
    model_name, separator, effort = str(candidate).partition("@")
    if not separator or not model_name or not effort:
        raise ValueError("El candidato debe usar el formato modelo@esfuerzo")
    model = catalog.get("models", {}).get(model_name)
    if not isinstance(model, dict) or effort not in model.get("reasoning_efforts", []):
        raise ValueError(f"Candidato no admitido por el catálogo: {candidate}")
    if profile.get("stage") != "F2.9-stage-3" or profile.get("cohort") != "business":
        raise ValueError("El perfil no corresponde a la campaña de negocio de F2.9 etapa 3")
    if profile.get("campaign_id") != "f2-9-stage-3-business-partial-v1":
        raise ValueError("El perfil no identifica la campaña parcial de negocio fijada")
    if profile.get("case_scope") != "owner_approved_30_business_cases_only":
        raise ValueError("El perfil debe limitarse a los 30 casos de negocio aprobados")
    if profile.get("safety_scope") != (
        "excluded_by_explicit_owner_direction; no prompt-injection cases are added "
        "or represented as validated"
    ):
        raise ValueError("El perfil debe declarar la exclusión explícita de la cohorte safety")
    if profile.get("safety_prompt_injection_cases") is not False:
        raise ValueError("Este preflight no debe añadir casos de prompt injection")
    if profile.get("status") != EXPECTED_PROFILE_STATUS:
        raise ValueError("El perfil debe mantener el estado pendiente de la campaña parcial")
    if profile.get("gates") != EXPECTED_GATES:
        raise ValueError("El preflight offline solo admite las puertas pendientes fijadas para esta campaña")
    repetitions = profile.get("run_repetitions")
    if isinstance(repetitions, bool) or not isinstance(repetitions, int) or repetitions < 1:
        raise ValueError("run_repetitions debe ser un entero positivo")
    if repetitions != 1:
        raise ValueError("este perfil solo admite la única repetición presupuestada")
    expected_limits = {
        "max_message_chars": 8_000,
        "max_tool_calls": 16,
        "max_tool_result_bytes": 16_000,
        "max_turn_seconds": 180,
    }
    if profile.get("limits") != expected_limits:
        raise ValueError("El perfil debe conservar los límites runtime fijados para la campaña")
    if fixture_hash != EXPECTED_CASE_HASH:
        raise ValueError("El fixture de negocio cambió; requiere revisión y nuevo pin")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or len(cases) != EXPECTED_CASE_COUNT:
        raise ValueError("Se requieren los 30 casos de negocio aprobados")
    ids = [case.get("id") for case in cases]
    if any(not isinstance(case_id, str) for case_id in ids) or len(set(ids)) != EXPECTED_CASE_COUNT:
        raise ValueError("El fixture tiene IDs de caso ausentes o duplicados")
    if fixture.get("status") != "OWNER_APPROVED":
        raise ValueError("El fixture de negocio no conserva la aprobación del dueño")
    messages = _message_count(cases)
    if messages != EXPECTED_MESSAGE_COUNT:
        raise ValueError("Cambió el número de mensajes; requiere actualizar la estimación")

    reference = _validate_measured_reference(profile)
    estimate = profile["estimate"]
    if reference.get("candidate") != candidate:
        raise ValueError("El candidato seleccionado no coincide con la muestra medida")
    if reference.get("question_count") != 15:
        raise ValueError("La muestra medida debe contener 15 casos stage 2")
    hashes = reference["source_hashes"]
    if estimate.get("input_rate_basis") != "cache-write rate, conservatively charged; no cached-input credit":
        raise ValueError("El presupuesto debe excluir créditos por caché y usar la tarifa conservadora")
    if model.get("cache_write_usd_per_million") != estimate.get("input_rate_usd_per_million"):
        raise ValueError("La tarifa de entrada del perfil no coincide con el catálogo")
    if model.get("output_usd_per_million") != estimate.get("output_rate_usd_per_million"):
        raise ValueError("La tarifa de salida del perfil no coincide con el catálogo")
    margin = estimate.get("margin_fraction")
    if isinstance(margin, bool) or not isinstance(margin, (int, float)) or margin != 0.35:
        raise ValueError("La estimación requiere un margen explícito de 35%")

    input_tokens = reference["completed_input_tokens"] * messages / reference["question_count"]
    output_tokens = reference["completed_output_tokens"] * messages / reference["question_count"]

    # Recreate the deterministic offline tool aggregate used for the estimate.
    # This measures schema and tool-result bytes only; it never contacts a model.
    from src.conversational_analytics.data.snapshot import Snapshot
    from src.conversational_analytics.evaluation_stage3_coverage import (
        _canonical_hash,
        _Tools,
        derive_stage3_coverage,
    )
    from src.conversational_analytics.providers._openai_prompt import (
        R2_PROMPT_PATH,
        R2_PROMPT_SHA256,
        load_system_instructions,
        prompt_sha256,
    )
    from src.conversational_analytics.tools.business_metrics import business_metric_tool_specs
    from src.conversational_analytics.tools.evidence import evidence_tool_specs
    from src.conversational_analytics.tools.routes import ROUTE_TOOL_SPECS

    coverage = coverage_report or derive_stage3_coverage(
        snapshot_root=ROOT / "site", fixture_path=fixture_path, profile_path=profile_path
    )
    metrics_coverage = coverage
    if not isinstance(metrics_coverage.get("cases"), list):
        metrics_coverage = derive_stage3_coverage(
            snapshot_root=ROOT / "site", fixture_path=fixture_path, profile_path=profile_path
        )
    tool_calls = [call for case in metrics_coverage["cases"] for call in case.get("calls", [])]
    serialized_results = [
        json.dumps(call.get("result"), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        for call in tool_calls
    ]
    serialized_arguments = [
        json.dumps(call.get("arguments"), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        for call in tool_calls
    ]
    messages_per_campaign = messages * repetitions
    tool_call_count = len(tool_calls)
    # Each user message and each tool continuation is a modeled provider request.
    # The highest observed offline call count is used as the conservative proxy.
    modeled_provider_requests = messages_per_campaign + tool_call_count

    snapshot = Snapshot(ROOT / "site")
    tools = _Tools(snapshot)
    current_tool_specs = (
        tools.registry.tool_specs() + ROUTE_TOOL_SPECS + business_metric_tool_specs() + evidence_tool_specs()
    )
    current_tool_schema_json = json.dumps(
        current_tool_specs, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    current_tool_schema_bytes = len(current_tool_schema_json.encode("utf-8"))
    current_tool_schema_sha = _canonical_hash(current_tool_specs)
    r1_prompt = load_system_instructions()
    r2_prompt = R2_PROMPT_PATH.read_text(encoding="utf-8").strip()
    r2_prompt_sha = prompt_sha256(r2_prompt)
    if r2_prompt_sha != R2_PROMPT_SHA256:
        raise ValueError("El prompt R2 propuesto no coincide con su hash fijado")

    historical_tool_schema_bytes = 3_306
    bytes_per_token_proxy_range = (3, 4)
    prompt_delta_bytes = len(r2_prompt.encode("utf-8")) - len(r1_prompt.encode("utf-8"))
    tool_schema_delta_bytes = current_tool_schema_bytes - historical_tool_schema_bytes
    context_delta_bytes_per_request = prompt_delta_bytes + tool_schema_delta_bytes
    coverage_tool_schema_sha = metrics_coverage["runtime_capabilities"]["tool_specs_sha256"]
    if context_delta_bytes_per_request <= 0 or current_tool_schema_sha != coverage_tool_schema_sha:
        raise ValueError("La medición del contexto actual no coincide con los pins de cobertura")
    context_delta_input_tokens_range = [
        math.ceil(context_delta_bytes_per_request * modeled_provider_requests / bytes_per_token)
        for bytes_per_token in (bytes_per_token_proxy_range[1], bytes_per_token_proxy_range[0])
    ]
    projected_input_tokens_range = [
        math.ceil(input_tokens + delta) for delta in context_delta_input_tokens_range
    ]
    input_rate = float(estimate["input_rate_usd_per_million"])
    output_rate = float(estimate["output_rate_usd_per_million"])
    costs_before_margin = [
        (projected_input * input_rate + output_tokens * output_rate) / 1_000_000
        for projected_input in projected_input_tokens_range
    ]
    costs_after_margin = [cost * (1 + margin) for cost in costs_before_margin]
    proposed_cost_range = [round(value, 4) for value in costs_after_margin]
    reserve_usd = float(_ceil_dollar(costs_after_margin[1]))
    base_cost = costs_before_margin[1]
    campaign_identity = dict(metrics_coverage["campaign_identity"])
    campaign_identity["reserve_usd"] = reserve_usd
    campaign_identity_json = json.dumps(
        campaign_identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    campaign_sha256 = hashlib.sha256(
        campaign_identity_json.encode("utf-8")
    ).hexdigest()
    return {
        "stage": "F2.9-stage-3",
        "mode": "offline_preflight_only",
        "status": profile.get("status"),
        "candidate": candidate,
        "campaign_id": profile["campaign_id"],
        "campaign_sha256": campaign_sha256,
        "cohort": "business_only_partial_stage3",
        "safety_scope": profile["safety_scope"],
        "case_count": len(cases),
        "messages_per_candidate": messages,
        "repetitions": repetitions,
        "coverage_summary": {
            "counts": metrics_coverage["counts"],
            "provider_calls": 0,
            "credentials_read": False,
            "snapshot_data_version": metrics_coverage["pins"]["data_version"],
            "snapshot_semantic_version": metrics_coverage["pins"]["semantic_version"],
            "execution_commit": metrics_coverage["campaign_identity"]["execution_commit"],
        },
        "limits": expected_limits,
        "prompt_injection_cases_added": 0,
        "source_hashes": {
            "profile": profile_hash,
            "business_fixture": fixture_hash,
            "model_catalog": catalog_hash,
            "public_stage2_closeout": PUBLIC_CLOSEOUT_SHA256,
            "active_prompt_r1": prompt_sha256(r1_prompt),
            "required_prompt_r2": r2_prompt_sha,
            "tool_specs": current_tool_schema_sha,
            "snapshot_manifest": metrics_coverage["pins"]["snapshot_manifest_sha256"],
            "derived_coverage": metrics_coverage["campaign_identity"]["derived_coverage_sha256"],
            **hashes,
        },
        "measured_reference": {
            "question_count": reference["question_count"],
            "input_tokens": reference["completed_input_tokens"],
            "output_tokens": reference["completed_output_tokens"],
            "input_rate_usd_per_million": estimate["input_rate_usd_per_million"],
            "input_rate_basis": estimate["input_rate_basis"],
            "output_rate_usd_per_million": estimate["output_rate_usd_per_million"],
            "pricing_as_of": model.get("pricing_as_of"),
        },
        "projection": {
            "basis": (
                "stage2_measured_usage_scaled_to_34_messages_plus_current_prompt_and_tool_schema_context_delta"
            ),
            "projected_input_tokens": projected_input_tokens_range[1],
            "projected_input_tokens_range": projected_input_tokens_range,
            "projected_output_tokens": math.ceil(output_tokens),
            "cost_before_margin_usd": round(base_cost, 6),
            "cost_before_margin_usd_range": [round(value, 6) for value in costs_before_margin],
            "cost_after_margin_usd_range": proposed_cost_range,
            "proposed_cost_upper_usd": round(costs_after_margin[1], 4),
            "proposed_reserve_usd": reserve_usd,
            "safety_margin_fraction": margin,
            "context_delta": {
                "prompt_r1_effective_utf8_bytes": len(r1_prompt.encode("utf-8")),
                "prompt_r1_sha256": prompt_sha256(r1_prompt),
                "prompt_r2_proposed_utf8_bytes": len(r2_prompt.encode("utf-8")),
                "prompt_r2_sha256": r2_prompt_sha,
                "prompt_delta_utf8_bytes_per_request": prompt_delta_bytes,
                "historical_tool_schema_utf8_bytes": historical_tool_schema_bytes,
                "historical_tool_schema_sha256": (
                    "1ff0d3a35647f7a0c2fc956884a4d267b0148065ccd3e2469139463f859bea19"
                ),
                "historical_execution_commit": "a3704be6ab9dacd8c481caff7caf3278fe861e90",
                "current_tool_schema_utf8_bytes": current_tool_schema_bytes,
                "current_tool_schema_sha256": current_tool_schema_sha,
                "tool_schema_delta_utf8_bytes_per_request": tool_schema_delta_bytes,
                "total_delta_utf8_bytes_per_request": context_delta_bytes_per_request,
                "modeled_provider_requests": modeled_provider_requests,
                "tool_calls": tool_call_count,
                "tool_result_serialized_utf8_bytes": sum(map(len, serialized_results)),
                "tool_arguments_serialized_utf8_bytes": sum(map(len, serialized_arguments)),
                "largest_tool_result_utf8_bytes": max(map(len, serialized_results), default=0),
                "bytes_per_token_proxy_range": list(bytes_per_token_proxy_range),
                "input_token_delta_range": context_delta_input_tokens_range,
                "estimation_note": (
                    "3–4 UTF-8 bytes/token proxy; no tokenizer or provider usage was queried. "
                    "Tool result sizes are an aggregate and are not converted into billed tokens."
                ),
            },
            "funds_to_have_available_if_zero_verified_balance_usd": reserve_usd,
            "owner_approval_required": True,
            "invoice_or_hard_cap": False,
            "funding_status": "not_approved; account_balance_unknown",
        },
        "gates": profile.get("gates", {}),
        "provider_calls_now": 0,
        "credentials_read": False,
        "live_execution_available": False,
        "must_recompute_after_dependency_integration": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight offline partial F2.9 business stage-3 campaign")
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument(
        "--candidate",
        choices=("gpt-6-luna@medium", "gpt-6-luna@max", "gpt-6.1-sol@low", "gpt-6.1-sol@medium"),
        help="override explícito del candidato indicado en el perfil",
    )
    args = parser.parse_args()
    try:
        plan = build_plan(profile_path=args.profile.resolve(), candidate_override=args.candidate)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
