"""Pinned, offline-only provenance and budget helpers for F2.9 finalization."""

from __future__ import annotations

import hashlib
import json
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
        cache_write_input_multiplier=float(model["cache_write_input_multiplier"]),
    )
    return pricing.usage_cost_usd(input_tokens, output_tokens)


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
