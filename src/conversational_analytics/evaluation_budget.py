"""Offline, fixture-driven token cost estimates for phase 2 evaluations.

This module never creates a provider client or records a bill. It models each
input token once at either the normal or cached-input rate and keeps cache-write
usage unknown until a provider confirms it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any


# Output ranges include reasoning tokens. Prices and capabilities come from the
# versioned config/chat/models.json catalog; do not copy rates into this module.
CANDIDATES: dict[str, dict[str, Any]] = {
    "gpt-6-luna@medium": {
        "model": "gpt-6-luna", "effort": "medium",
        "output_per_user_message": (3_000, 6_000),
    },
    "gpt-6-luna@max": {
        "model": "gpt-6-luna", "effort": "max",
        "output_per_user_message": (10_000, 25_000),
    },
    "gpt-6.1-sol@low": {
        "model": "gpt-6.1-sol", "effort": "low",
        "output_per_user_message": (1_000, 3_000),
    },
    "gpt-6.1-sol@medium": {
        "model": "gpt-6.1-sol", "effort": "medium",
        "output_per_user_message": (3_000, 8_000),
    },
}


def specs_from_model_catalog(
    model_catalog: Mapping[str, Mapping[str, Any]],
    candidate_profiles: Mapping[str, Mapping[str, Any]] = CANDIDATES,
) -> dict[str, dict[str, Any]]:
    """Join output planning ranges to the authoritative model price catalog."""
    result = {}
    for candidate, profile in candidate_profiles.items():
        model = profile["model"]
        effort = profile["effort"]
        if model not in model_catalog:
            raise ValueError(f"El catálogo no contiene {model}")
        catalog = model_catalog[model]
        efforts = catalog.get("reasoning_efforts", [])
        if effort not in efforts:
            raise ValueError(f"El catálogo no acepta {candidate}")
        result[candidate] = {
            **profile,
            "input": catalog["input_usd_per_million"],
            "cached_input": catalog["cached_input_usd_per_million"],
            "cache_write": catalog["cache_write_usd_per_million"],
            "output": catalog["output_usd_per_million"],
            "long_context_threshold_input_tokens": catalog.get("long_context_threshold_input_tokens"),
            "long_context_input_multiplier": catalog.get("long_context_input_multiplier", 1.0),
            "long_context_output_multiplier": catalog.get("long_context_output_multiplier", 1.0),
            "pricing_as_of": catalog.get("pricing_as_of"),
        }
    return result


def _finite_number(value: Any, label: str, *, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} debe ser numérico")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"{label} debe ser finito y >= {minimum}")
    return result


def _positive_range(value: Sequence[int], label: str) -> tuple[int, int]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 2:
        raise ValueError(f"{label} debe tener mínimo y máximo")
    low, high = value
    for part in (low, high):
        if isinstance(part, bool) or not isinstance(part, int) or part <= 0:
            raise ValueError(f"{label} debe contener enteros positivos")
    if low > high:
        raise ValueError(f"{label} tiene mínimo mayor que máximo")
    return low, high


def user_message_count(cases: Sequence[Mapping[str, Any]]) -> int:
    """Count user turns represented by selected fixture cases."""
    total = 0
    for case in cases:
        turns = case.get("turns")
        if turns is None:
            turns = [case.get("question")]
        if not isinstance(turns, list) or not turns or any(not isinstance(turn, str) or not turn.strip() for turn in turns):
            raise ValueError(f"Caso {case.get('id', '<sin id>')} tiene turns inválidos")
        total += len(turns)
    return total


def estimate_stage(
    selected_cases: Sequence[Mapping[str, Any]],
    candidate_run_multipliers: Mapping[str, int],
    *,
    input_tokens_per_user_message: Sequence[int] = (60_000, 100_000),
    cache_hit_rate: float = 0.0,
    candidate_specs: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Estimate one stage from selected cases and candidate repetition plans.

    ``candidate_run_multipliers`` is the number of times each selected case is
    run for a candidate (for example, two prompt versions or a repeat). This
    yields case counts, input message counts and output counts from fixtures,
    including each explicit user turn in a multi-turn case.
    """
    if not selected_cases:
        raise ValueError("selected_cases no puede estar vacío")
    if not candidate_run_multipliers:
        raise ValueError("candidate_run_multipliers no puede estar vacío")
    input_low, input_high = _positive_range(input_tokens_per_user_message, "input_tokens_per_user_message")
    hit_rate = _finite_number(cache_hit_rate, "cache_hit_rate")
    if hit_rate > 1:
        raise ValueError("cache_hit_rate debe estar entre 0 y 1")

    messages_per_case_run = user_message_count(selected_cases)
    results = []
    for candidate, multiplier in candidate_run_multipliers.items():
        if candidate not in candidate_specs:
            raise ValueError(f"Tarifas no registradas para {candidate}")
        if isinstance(multiplier, bool) or not isinstance(multiplier, int) or multiplier <= 0:
            raise ValueError(f"El multiplicador de {candidate} debe ser entero positivo")
        spec = candidate_specs[candidate]
        normal = _finite_number(spec.get("input"), f"{candidate}.input")
        cached = _finite_number(spec.get("cached_input"), f"{candidate}.cached_input")
        output_rate = _finite_number(spec.get("output"), f"{candidate}.output")
        write_rate = _finite_number(spec.get("cache_write"), f"{candidate}.cache_write")
        if min(normal, cached, output_rate, write_rate) <= 0:
            raise ValueError(f"Las tarifas de {candidate} deben ser positivas")
        output_low, output_high = _positive_range(
            spec.get("output_per_user_message"), f"{candidate}.output_per_user_message"
        )
        case_runs = len(selected_cases) * multiplier
        input_messages = messages_per_case_run * multiplier
        input_tokens = (input_messages * input_low, input_messages * input_high)
        output_tokens = (input_messages * output_low, input_messages * output_high)
        effective_input_rate = normal * (1 - hit_rate) + cached * hit_rate
        cost = (
            input_tokens[0] * effective_input_rate + output_tokens[0] * output_rate,
            input_tokens[1] * effective_input_rate + output_tokens[1] * output_rate,
        )
        results.append({
            "candidate": candidate,
            "model": spec.get("model"),
            "reasoning_effort": spec.get("effort"),
            "case_runs": case_runs,
            "user_messages": input_messages,
            "estimated_input_tokens_range": list(input_tokens),
            "modeled_output_plus_reasoning_tokens_range": list(output_tokens),
            "rates_usd_per_million": {
                "input": normal, "cached_input": cached,
                "cache_write": write_rate, "output": output_rate,
            },
            "estimated_cost_usd_range": [round(cost[0] / 1_000_000, 4), round(cost[1] / 1_000_000, 4)],
            "long_context_pricing": {
                "threshold_input_tokens": spec.get("long_context_threshold_input_tokens"),
                "input_multiplier": spec.get("long_context_input_multiplier"),
                "output_multiplier": spec.get("long_context_output_multiplier"),
                "applied": False,
                "reason": "Per-request input size is not measured; the range models aggregate user-message usage.",
            },
            "pricing_as_of": spec.get("pricing_as_of"),
            "cache_hit_rate_scenario": hit_rate,
            "cache_write_usage": "unknown; not priced as zero",
            "billing_status": "modelled estimate; no provider usage or invoice",
        })
    return {
        "mode": "offline_modelled_estimate",
        "selected_case_count": len(selected_cases),
        "user_messages_per_case_run": messages_per_case_run,
        "input_tokens_range_per_user_message": [input_low, input_high],
        "cache_hit_rate_scenario": hit_rate,
        "candidate_estimates": results,
    }
