"""Pinned, offline-only provenance and budget helpers for F2.9 finalization."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any


def read_pinned_sources(paths: dict[str, Path], approved: dict[str, str]) -> dict[str, bytes]:
    """Read every source once and reject any non-approved bytes before parsing."""
    if set(paths) != set(approved):
        raise ValueError("El conjunto de fuentes privadas no coincide con los pins aprobados")
    raw = {label: path.read_bytes() for label, path in paths.items()}
    for label, data in raw.items():
        if hashlib.sha256(data).hexdigest() != approved[label]:
            raise ValueError(f"SHA-256 no aprobado para fuente privada: {label}")
    return raw


def parse_pinned_object(raw: bytes, label: str) -> dict[str, Any]:
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"La fuente privada debe ser un objeto JSON: {label}")
    return value


def conservative_usage_cost(input_tokens: int, output_tokens: int, catalog: dict[str, Any]) -> float:
    """Price confirmed usage at cache-write input rates; never use cached-token discounts."""
    from src.conversational_analytics.config import ChatConfig

    model = catalog["models"]["gpt-6.1-sol"]
    pricing = ChatConfig(
        provider="openai",
        model="gpt-6.1-sol",
        estimated_input_cost_per_million=float(model["input_usd_per_million"]),
        estimated_output_cost_per_million=float(model["output_usd_per_million"]),
        long_context_threshold_input_tokens=int(model["long_context_threshold_input_tokens"]),
        long_context_input_multiplier=float(model["long_context_input_multiplier"]),
        long_context_output_multiplier=float(model["long_context_output_multiplier"]),
        cache_write_input_multiplier=float(model["cache_write_input_multiplier"]),
    )
    return pricing.usage_cost_usd(input_tokens, output_tokens)


def empirical_reservation_assumption(
    reports: list[dict[str, Any]],
    recovered_usage: tuple[int, int],
    catalog: dict[str, Any],
    *,
    request_count: int,
    safety_margin: float = 0.35,
) -> dict[str, Any]:
    """Price a pilot-only admission forecast from complete prior usage plus a margin."""
    if request_count != 29 or not math.isfinite(safety_margin) or not 0 < safety_margin <= 0.5:
        raise ValueError("La reserva empírica requiere 29 slots y margen entre 0 y 50%")
    samples: list[tuple[int, int]] = []
    incomplete_count = 0
    candidate_counts: dict[str, int] = {}
    for report in reports:
        models = report.get("models", [])
        if len(models) != 1:
            raise ValueError("La muestra de presupuesto debe contener un modelo por reporte")
        candidate = models[0].get("candidate")
        if candidate not in {"gpt-6-luna@medium", "gpt-6-luna@max"}:
            raise ValueError("La muestra histórica contiene un candidato no autorizado")
        for row in models[0].get("cases", []):
            if row.get("model_turn_completed") is not True or row.get("usage_complete") is not True:
                incomplete_count += 1
                continue
            input_tokens, output_tokens = row.get("input_tokens"), row.get("output_tokens")
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in (input_tokens, output_tokens)
            ):
                raise ValueError("Una respuesta completa no conserva conteos de tokens válidos")
            samples.append((input_tokens, output_tokens))
            candidate_counts[candidate] = candidate_counts.get(candidate, 0) + 1
    if len(samples) != 29 or incomplete_count != 1:
        raise ValueError("La reserva requiere exactamente 29 respuestas históricas completas")
    if candidate_counts != {"gpt-6-luna@medium": 14, "gpt-6-luna@max": 15}:
        raise ValueError("La mezcla histórica no coincide con las 14 respuestas Luna medium y 15 max")
    recovered_input, recovered_output = recovered_usage
    if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in recovered_usage):
        raise ValueError("El uso recuperado no conserva conteos de tokens válidos")
    samples.append((recovered_input, recovered_output))
    candidate_counts["gpt-6.1-sol@low"] = 1
    sample_count = len(samples)
    input_sum = sum(row[0] for row in samples)
    output_sum = sum(row[1] for row in samples)
    mean_input = math.ceil(input_sum / sample_count)
    mean_output = math.ceil(output_sum / sample_count)
    reserved_input = math.ceil(mean_input * (1 + safety_margin))
    reserved_output = math.ceil(mean_output * (1 + safety_margin))
    per_case = conservative_usage_cost(reserved_input, reserved_output, catalog)
    rates = catalog["models"]["gpt-6.1-sol"]
    return {
        "basis": "f2_9_empirical_pilot_estimate_not_hard_cap",
        "budget_guaranteed": False,
        "input_tokens_per_turn": reserved_input,
        "output_tokens_per_turn": reserved_output,
        "historical_sample_count": sample_count,
        "historical_candidate_counts": candidate_counts,
        "historical_input_tokens": input_sum,
        "historical_output_tokens": output_sum,
        "mean_input_tokens_rounded_up": mean_input,
        "mean_output_tokens_rounded_up": mean_output,
        "safety_margin_fraction": safety_margin,
        "per_case_estimated_reservation_usd": per_case,
        "planned_request_count": request_count,
        "planned_batch_estimated_reservation_usd": per_case * request_count,
        "unit_prices_usd_per_million": {
            "input_normal": float(rates["input_usd_per_million"]),
            "input_cache_write": float(rates["cache_write_usd_per_million"]),
            "output": float(rates["output_usd_per_million"]),
        },
        "long_context_threshold_input_tokens": int(rates["long_context_threshold_input_tokens"]),
        "long_context_input_multiplier": float(rates["long_context_input_multiplier"]),
        "long_context_output_multiplier": float(rates["long_context_output_multiplier"]),
        "price_basis": "separate Sol input at cache-write rate and output at catalog rate; no cache credit",
        "note": (
            "Heterogeneous descriptive sample (14 Luna medium, 15 Luna max, 1 recovered Sol low); "
            "mean plus 35% planning margin is an operational estimate, not a hard cap. Usage beyond it "
            "can stop the campaign or exceed the authorized reserve."
        ),
    }


def final_case_partition(case_ids: tuple[str, ...]) -> dict[str, list[str] | str]:
    """Declare every finalization slot, replacement, recovery skip, and omission."""
    if len(case_ids) != 15 or len(set(case_ids)) != 15:
        raise ValueError("La finalización requiere los 15 IDs únicos del fixture congelado")
    return {
        "replacement_case_ids": list(case_ids[:13]),
        "never_attempted_case_ids": [case_ids[14]],
        "recovered_case_id_skipped": case_ids[13],
        "sol_low_case_ids": [*case_ids[:13], case_ids[14]],
        "sol_medium_case_ids": list(case_ids),
    }


def validate_terminal_recovery(
    recovery: dict[str, Any], *, expected_source: dict[str, Any], expected_case_id: str
) -> tuple[str, int, int]:
    """Validate the already-completed GET artifact, returning answer only to caller."""
    source = recovery.get("source")
    provider = recovery.get("provider")
    usage = recovery.get("usage")
    answer = recovery.get("answer")
    evaluation = recovery.get("evaluation")
    if not all(isinstance(item, dict) for item in (source, provider, usage, answer, evaluation)):
        raise ValueError("La evidencia terminal está incompleta")
    if any(source.get(key) != value for key, value in expected_source.items()):
        raise ValueError("La evidencia terminal no coincide con la corrida fijada")
    if (
        source.get("case_id") != expected_case_id
        or provider.get("turn_status") != "completed"
        or provider.get("session_status") != "idle"
        or provider.get("session_idle") is not True
        or provider.get("turn_identity_verified") is not True
        or recovery.get("request_controls", {}).get("side_effecting_requests") != 0
        or usage.get("usage_complete") is not True
        or (usage.get("input_tokens"), usage.get("output_tokens")) != (137_951, 499)
        or answer.get("present") is not True
        or answer.get("selected_assistant_message_count") != 1
        or not isinstance(answer.get("text"), str)
        or not answer["text"].strip()
        or hashlib.sha256(answer["text"].encode()).hexdigest() != answer.get("sha256")
        or evaluation.get("transport_recovered") is not True
        or evaluation.get("latency_valid") is not False
        or evaluation.get("auto_graded") is not False
        or evaluation.get("auto_approved") is not False
        or evaluation.get("tool_calls_inferred") is not False
    ):
        raise ValueError("La recuperación no prueba un único turno terminado sin replay")
    return answer["text"], 137_951, 499


def derived_recovery_report(
    *,
    run_identity: dict[str, Any],
    campaign_identity_hash: str,
    answer: str,
    input_tokens: int,
    output_tokens: int,
    recovery_sha256: str,
    progress_sha256: str,
    continuation_plan_sha256: str,
    answer_sha256: str,
    recovery_case_id: str,
) -> dict[str, Any]:
    """Create a one-row private lineage report; do not grade or infer tool trace."""
    identity = json.loads(json.dumps(run_identity))
    candidate = identity.get("candidate")
    if not isinstance(candidate, str):
        raise ValueError("El plan fuente no conserva candidato en la identidad")
    model_name = identity.get("model")
    effort = identity.get("reasoning_effort")
    identity_hash = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    report = {
        "mode": "live-evaluation",
        "probe_only": False,
        "run_status": "recovered_partial",
        "case_count": 1,
        "candidate_models": [candidate],
        "run_identity": identity,
        "run_identity_hash": identity_hash,
        "campaign_identity_hash": campaign_identity_hash,
        "data_version": identity.get("data_version"),
        "semantic_version": identity.get("semantic_version"),
        "estimated_cost_usd": None,
        "known_estimated_cost_usd": None,
    }
    report["derived_lineage"] = {
        "kind": "single_terminal_turn_recovery",
        "source_progress_sha256": progress_sha256,
        "continuation_plan_sha256": continuation_plan_sha256,
        "recovery_sha256": recovery_sha256,
        "answer_sha256": answer_sha256,
        "runtime_stream_stall": True,
        "tool_trace": "unavailable",
        "human_review_required": True,
    }
    recovered_row = {
        "case_id": recovery_case_id,
        "candidate": candidate,
        "model": model_name,
        "reasoning_effort": effort,
        "run_identity": identity,
        "model_turn_completed": True,
        "provider_turn_started": True,
        "usage_complete": True,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_seconds": None,
        "response": answer,
        "turn_responses": [answer],
        "turn_count": 1,
        "provider_request_count": 1,
        "provider_tool_call_count": None,
        "tool_calls": None,
        "provider_event_ids": [],
        "provider_turn_ids": [],
        "session_id": None,
        "status": "recovered_terminal_turn",
        "quality": {
            "evaluated": False,
            "passed": None,
            "automatic_grade_type": None,
            "requires_blinded_human_rubric": True,
            "human_rubric_status": "pending_owner_review",
        },
        "recovery_metadata": {
            "transport_recovered": True,
            "latency_valid": False,
            "tool_trace": "unavailable",
            "tool_calls_inferred": False,
            "auto_graded": False,
            "auto_approved": False,
            "continuation_plan_sha256": continuation_plan_sha256,
            "source_progress_sha256": progress_sha256,
            "recovery_sha256": recovery_sha256,
            "answer_sha256": answer_sha256,
        },
    }
    report["models"] = [
        {
            "candidate": candidate,
            "model": model_name,
            "reasoning_effort": effort,
            "run_identity": identity,
            "cases": [recovered_row],
            "case_count": 1,
            "estimated_cost_usd": None,
            "known_estimated_cost_usd": None,
            "spent_unknown": False,
        }
    ]
    return report
