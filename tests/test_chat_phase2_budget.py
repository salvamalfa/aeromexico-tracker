"""Meaningful fixture-driven checks for offline F2.9 budget estimates."""

import copy
import math

import pytest

from src.conversational_analytics.evaluation_budget import (
    CANDIDATES,
    estimate_stage,
    specs_from_model_catalog,
    user_message_count,
)


LUNA = "gpt-6-luna@medium"

MODEL_CATALOG = {
    "gpt-6-luna": {
        "reasoning_efforts": ["medium", "max"],
        "input_usd_per_million": 0.10,
        "cached_input_usd_per_million": 0.01,
        "cache_write_usd_per_million": 0.125,
        "output_usd_per_million": 0.50,
        "long_context_threshold_input_tokens": 272_000,
        "long_context_input_multiplier": 2.0,
        "long_context_output_multiplier": 1.5,
        "pricing_as_of": "2026-10-08",
    },
    "gpt-6.1-sol": {
        "reasoning_efforts": ["low", "medium"],
        "input_usd_per_million": 2.0,
        "cached_input_usd_per_million": 0.10,
        "cache_write_usd_per_million": 2.50,
        "output_usd_per_million": 10.0,
        "long_context_threshold_input_tokens": 272_000,
        "long_context_input_multiplier": 2.0,
        "long_context_output_multiplier": 1.5,
        "pricing_as_of": "2026-10-08",
    },
}
SPECS = specs_from_model_catalog(MODEL_CATALOG)


def test_followup_turn_increases_input_and_output_estimates() -> None:
    base = [{"id": "N24", "turns": ["Pregunta", "Seguimiento", "Cierre"]}]
    followup = copy.deepcopy(base)
    followup[0]["turns"].append("Otro seguimiento")

    base_result = estimate_stage(base, {LUNA: 1}, input_tokens_per_user_message=(100, 100), candidate_specs=SPECS)
    followup_result = estimate_stage(followup, {LUNA: 1}, input_tokens_per_user_message=(100, 100), candidate_specs=SPECS)
    base_row = base_result["candidate_estimates"][0]
    followup_row = followup_result["candidate_estimates"][0]

    assert followup_row["user_messages"] == base_row["user_messages"] + 1
    assert followup_row["estimated_input_tokens_range"][0] == base_row["estimated_input_tokens_range"][0] + 100
    assert followup_row["modeled_output_plus_reasoning_tokens_range"][0] == base_row["modeled_output_plus_reasoning_tokens_range"][0] + 3_000
    assert followup_row["estimated_cost_usd_range"][0] > base_row["estimated_cost_usd_range"][0]


def test_selected_fixture_size_drives_case_and_token_estimates() -> None:
    cases = [{"id": "N01", "question": "Uno"}, {"id": "N02", "question": "Dos"}]
    first = estimate_stage(cases, {LUNA: 2}, input_tokens_per_user_message=(100, 200), candidate_specs=SPECS)
    cases.append({"id": "N03", "turns": ["Inicio", "Seguimiento"]})
    changed = estimate_stage(cases, {LUNA: 2}, input_tokens_per_user_message=(100, 200), candidate_specs=SPECS)
    row_before, row_after = first["candidate_estimates"][0], changed["candidate_estimates"][0]

    assert row_before["case_runs"] == 4
    assert row_after["case_runs"] == 6
    assert row_before["user_messages"] == 4
    assert row_after["user_messages"] == 8
    assert changed["selected_case_count"] == 3


def test_cache_write_usage_remains_unknown_not_zero() -> None:
    estimate = estimate_stage([{"id": "N01", "question": "Pregunta"}], {LUNA: 1}, candidate_specs=SPECS)
    row = estimate["candidate_estimates"][0]

    assert row["rates_usd_per_million"]["cache_write"] == MODEL_CATALOG["gpt-6-luna"]["cache_write_usd_per_million"]
    assert row["cache_write_usage"].startswith("unknown")
    assert row["billing_status"] == "modelled estimate; no provider usage or invoice"


@pytest.mark.parametrize("cache_hit_rate", [math.nan, math.inf, -0.01, 1.01])
def test_rejects_invalid_cache_hit_rates(cache_hit_rate: float) -> None:
    with pytest.raises(ValueError):
        estimate_stage([{"id": "N01", "question": "Pregunta"}], {LUNA: 1}, cache_hit_rate=cache_hit_rate, candidate_specs=SPECS)


@pytest.mark.parametrize("token_range", [(0, 100), (200, 100), (1, math.inf), (1.5, 2)])
def test_rejects_invalid_token_ranges(token_range: tuple) -> None:
    with pytest.raises(ValueError):
        estimate_stage([{"id": "N01", "question": "Pregunta"}], {LUNA: 1}, input_tokens_per_user_message=token_range, candidate_specs=SPECS)


@pytest.mark.parametrize("rate", [math.nan, math.inf, -0.01, 0, "0.10"])
def test_rejects_invalid_model_rates(rate: object) -> None:
    catalog = copy.deepcopy(MODEL_CATALOG)
    catalog["gpt-6-luna"]["input_usd_per_million"] = rate
    specs = specs_from_model_catalog(catalog)
    with pytest.raises(ValueError):
        estimate_stage([{"id": "N01", "question": "Pregunta"}], {LUNA: 1}, candidate_specs=specs)


def test_turn_count_uses_turns_or_single_question() -> None:
    assert user_message_count([
        {"id": "single", "question": "Uno"},
        {"id": "multi", "turns": ["Dos", "Seguimiento"]},
    ]) == 3


def test_candidates_and_efforts_are_checked_against_authoritative_catalog() -> None:
    catalog = {"gpt-6-luna": MODEL_CATALOG["gpt-6-luna"]}
    with pytest.raises(ValueError, match="no contiene"):
        specs_from_model_catalog(catalog)
    with pytest.raises(ValueError, match="no acepta"):
        specs_from_model_catalog(catalog, {"gpt-6-luna@high": {**CANDIDATES[LUNA], "effort": "high"}})
