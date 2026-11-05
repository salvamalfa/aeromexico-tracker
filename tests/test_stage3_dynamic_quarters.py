"""Synthetic quarter changes exercise current coverage, without approving native future data."""

import pytest

from src.conversational_analytics.evaluation_stage3_scenarios import (
    _derived_calculations,
    _scenario_calls,
)


@pytest.mark.parametrize("current", ["2026Q3", "2027Q1"])
@pytest.mark.parametrize(
    "case,metric,entities",
    [
        ("N03", "cask_cents_per_km", ["AEROMEXICO", "VOLARIS"]),
        ("N07", "market_share", ["AEROMEXICO", "VOLARIS"]),
        ("N11", "load_factor", ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"]),
    ],
)
def test_current_comparisons_derive_only_from_the_queried_quarters(current, case, metric, entities):
    prior = f"{int(current[:4]) - 1}{current[4:]}"
    periods = {
        "economic_quarters": [prior, current], "market_quarters": [prior, current],
        "market_months": [], "flight": {},
    }
    calls, _ = _scenario_calls(case, periods)
    selected = [current] if case == "N03" else [prior, current]
    assert calls[0] == ("query_metrics", {
        "metric_ids": [metric], "entity_ids": entities, "periods": selected,
        **({"segment": "domestic"} if case == "N07" else {}),
    })
    rows = [
        {"metric_id": metric, "entity_id": entity, "period": period,
         "value": 0.3 + i * 0.01 + j * 0.05, "availability": "available"}
        for i, entity in enumerate(entities) for j, period in enumerate(selected)
    ]
    result = _derived_calculations(case, list(reversed(rows)))
    assert len(result) == (1 if case == "N03" else len(entities))
    for calculation in result:
        if case == "N03":
            assert calculation["period"] == current
            assert calculation["value"] == pytest.approx(-0.01)
            assert calculation["unit"] == "USD_cents_per_ASK_km"
        else:
            assert calculation["periods"] == [prior, current]
            assert calculation["value"] == pytest.approx(5.0)
            assert calculation["unit"] == "percentage_points"
    # Extra quarters cannot silently select a different numeric comparison.
    assert _derived_calculations(case, rows + [dict(rows[0], period="1999Q4")]) == []
    assert _derived_calculations(case, [dict(row, value=float("nan")) for row in rows]) == []
    if case != "N03":
        incoherent = [dict(row, period="2025Q4") if row["period"] == prior else row for row in rows]
        assert _derived_calculations(case, incoherent) == []


@pytest.mark.parametrize(
    "current,label", [("2026Q3", "3T25 frente a 3T26"), ("2027Q1", "1T26 frente a 1T27")]
)
def test_scope_label_follows_the_exact_annual_quarters_or_declares_the_missing_comparator(current, label):
    prior = f"{int(current[:4]) - 1}{current[4:]}"
    periods = {
        "economic_quarters": [], "market_quarters": [prior, current],
        "market_months": [], "flight": {},
    }
    calls, limitation = _scenario_calls("N08", periods)
    assert calls[0][1]["periods"] == [prior, current]
    assert label in limitation
    periods["market_quarters"] = [current]
    calls, limitation = _scenario_calls("N08", periods)
    assert calls[0][1]["periods"] == [current]
    assert "Falta un trimestre equivalente" in limitation
    periods["economic_quarters"] = [prior, current]
    calls, limitation = _scenario_calls("N24", periods)
    queries = [arguments for tool, arguments in calls if tool == "query_metrics"]
    assert queries == [
        {"metric_ids": ["company_passengers"], "entity_ids": ["AEROMEXICO", "VOLARIS"],
         "periods": selected}
        for selected in ([current], [prior, current])
    ]
    assert f"aspecto de {current[-1]}T{current[2:4]}" in limitation
