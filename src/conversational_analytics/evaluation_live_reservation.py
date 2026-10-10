"""Reservation policies for live campaign admission."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .config import ChatConfig
from .evaluation_live_support import (
    _RESERVATION_INPUT_TOKENS_PER_CASE_FLOOR,
    _RESERVATION_OUTPUT_TOKENS_PER_CASE_FLOOR,
)


def reservation_assumption(config: ChatConfig, override: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return reportable admission assumptions; defaults preserve production policy."""
    if override is None:
        return {
            "input_tokens_per_turn": max(
                _RESERVATION_INPUT_TOKENS_PER_CASE_FLOOR,
                config.max_tool_calls * (config.max_message_chars // 4 + config.max_tool_result_bytes // 4),
            ),
            "output_tokens_per_turn": max(
                _RESERVATION_OUTPUT_TOKENS_PER_CASE_FLOOR, config.max_tool_calls * 2_000
            ),
            "pricing_method": "generic_higher_token_rate_reservation",
            "note": (
                "reserva operativa por mensaje con piso de 140k input y 10k output, valorados con tarifa "
                "conservadora de cache-write/salida y multiplicadores long-context. Una solicitud puede "
                "excederla; gasto desconocido detiene la campaña y bloquea replay"
            ),
        }
    if override.get("basis") != "f2_9_empirical_pilot_estimate_not_hard_cap":
        raise ValueError("La política de reserva empírica no está aprobada para esta campaña")
    for key in ("input_tokens_per_turn", "output_tokens_per_turn", "planned_request_count"):
        value = override.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError("La política de reserva empírica contiene límites inválidos")
    margin = override.get("safety_margin_fraction")
    per_case = override.get("per_case_estimated_reservation_usd")
    expected_unit_cost = config.usage_cost_usd(
        override["input_tokens_per_turn"], override["output_tokens_per_turn"]
    )
    if (
        config.model != "gpt-6.1-sol"
        or override.get("historical_sample_count") != 30
        or override.get("historical_candidate_counts") != {
            "gpt-6-luna@medium": 14,
            "gpt-6-luna@max": 15,
            "gpt-6.1-sol@low": 1,
        }
        or override.get("planned_request_count") != 29
        or override.get("input_tokens_per_turn") != 68_570
        or override.get("output_tokens_per_turn") != 2_073
        or isinstance(margin, bool)
        or not isinstance(margin, (int, float))
        or not math.isfinite(margin)
        or margin != 0.35
        or isinstance(per_case, bool)
        or not isinstance(per_case, (int, float))
        or not math.isfinite(per_case)
        or per_case <= 0
        or not math.isclose(per_case, expected_unit_cost, rel_tol=0, abs_tol=1e-12)
        or not math.isclose(
            float(override.get("planned_batch_estimated_reservation_usd", -1)),
            expected_unit_cost * 29,
            rel_tol=0,
            abs_tol=1e-9,
        )
        or override.get("budget_guaranteed") is not False
    ):
        raise ValueError("La reserva empírica no conserva margen o estimación válidos")
    return dict(override)


def case_reservation_cost(config: ChatConfig, assumption: Mapping[str, Any], turn_count: int) -> float:
    if isinstance(turn_count, bool) or not isinstance(turn_count, int) or turn_count < 1:
        raise ValueError("El caso debe contener al menos un turno")
    inputs = assumption["input_tokens_per_turn"]
    outputs = assumption["output_tokens_per_turn"]
    if assumption.get("basis") == "f2_9_empirical_pilot_estimate_not_hard_cap":
        per_turn = config.usage_cost_usd(inputs, outputs)
    else:
        per_turn = config.reservation_cost_usd(inputs + outputs)
    return turn_count * per_turn
