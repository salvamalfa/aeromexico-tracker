from __future__ import annotations

import pytest

from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.evaluation_live_reservation import (
    case_reservation_cost,
    reservation_assumption,
)


def _config() -> ChatConfig:
    return ChatConfig(
        provider="openai",
        model="gpt-6.1-sol",
        max_tool_calls=16,
        max_message_chars=8_000,
        max_tool_result_bytes=16_000,
        estimated_input_cost_per_million=2.0,
        estimated_output_cost_per_million=10.0,
        long_context_threshold_input_tokens=272_000,
        long_context_input_multiplier=2.0,
        long_context_output_multiplier=1.5,
        cache_write_input_multiplier=1.25,
    )


def test_default_live_reservation_keeps_generic_higher_rate_policy() -> None:
    config = _config()
    assumption = reservation_assumption(config, None)

    assert assumption["input_tokens_per_turn"] == 140_000
    assert assumption["output_tokens_per_turn"] == 32_000
    assert assumption["pricing_method"] == "generic_higher_token_rate_reservation"
    assert case_reservation_cost(config, assumption, 1) == pytest.approx(2.58)


def test_pilot_override_prices_input_and_output_separately() -> None:
    config = _config()
    assumption = {
        "basis": "f2_9_empirical_pilot_estimate_not_hard_cap",
        "input_tokens_per_turn": 68_570,
        "output_tokens_per_turn": 2_073,
        "historical_sample_count": 30,
        "historical_candidate_counts": {
            "gpt-6-luna@medium": 14,
            "gpt-6-luna@max": 15,
            "gpt-6.1-sol@low": 1,
        },
        "planned_request_count": 29,
        "safety_margin_fraction": 0.35,
        "per_case_estimated_reservation_usd": 0.192155,
        "planned_batch_estimated_reservation_usd": 5.572495,
        "budget_guaranteed": False,
    }

    assert case_reservation_cost(config, assumption, 1) == pytest.approx(0.192155)
    assert 29 * case_reservation_cost(config, assumption, 1) == pytest.approx(5.572495)
    assert case_reservation_cost(config, assumption, 1) < case_reservation_cost(
        config, reservation_assumption(config, None), 1
    )


def test_empirical_override_rejects_claim_of_hard_guarantee() -> None:
    assumption = {
        "basis": "f2_9_empirical_pilot_estimate_not_hard_cap",
        "input_tokens_per_turn": 68_570,
        "output_tokens_per_turn": 2_073,
        "historical_sample_count": 30,
        "historical_candidate_counts": {
            "gpt-6-luna@medium": 14,
            "gpt-6-luna@max": 15,
            "gpt-6.1-sol@low": 1,
        },
        "planned_request_count": 29,
        "safety_margin_fraction": 0.35,
        "per_case_estimated_reservation_usd": 0.192155,
        "planned_batch_estimated_reservation_usd": 5.572495,
        "budget_guaranteed": True,
    }

    with pytest.raises(ValueError, match="margen o estimación"):
        reservation_assumption(_config(), assumption)


def test_empirical_override_rejects_different_margin_with_same_token_reservation() -> None:
    assumption = {
        "basis": "f2_9_empirical_pilot_estimate_not_hard_cap",
        "input_tokens_per_turn": 68_570,
        "output_tokens_per_turn": 2_073,
        "historical_sample_count": 30,
        "historical_candidate_counts": {
            "gpt-6-luna@medium": 14,
            "gpt-6-luna@max": 15,
            "gpt-6.1-sol@low": 1,
        },
        "planned_request_count": 29,
        "safety_margin_fraction": 0.25,
        "per_case_estimated_reservation_usd": 0.192155,
        "planned_batch_estimated_reservation_usd": 5.572495,
        "budget_guaranteed": False,
    }

    with pytest.raises(ValueError, match="margen o estimación"):
        reservation_assumption(_config(), assumption)
