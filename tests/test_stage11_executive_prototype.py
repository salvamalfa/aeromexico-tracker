from __future__ import annotations

import math

import pytest

from src.dashboard.executive_summary import (
    EXECUTIVE_QUERY,
    load_executive_history,
)


@pytest.mark.local_data
def test_payload_uses_every_complete_comparable_backend_quarter(executive_payload) -> None:
    history = load_executive_history()
    payload = executive_payload
    assert payload["metadata"]["quarter_count"] == len(history) == 22
    assert payload["metadata"]["first_period"] == "2021Q1"
    assert payload["metadata"]["last_period"] == "2026Q2"
    assert [record["period_id"] for record in payload["records"]] == history[
        "period_id"
    ].tolist()
    assert "v_aeromexico_quarterly" in EXECUTIVE_QUERY


@pytest.mark.local_data
def test_payload_reconciles_latest_anchor_and_margin_formula(executive_payload) -> None:
    payload = executive_payload
    latest = payload["records"][-1]
    assert latest["period_id"] == "2026Q2"
    assert latest["passengers"] == 6_014_000.0
    assert math.isclose(latest["ask_km"], 14_896_088_064.000002)
    assert math.isclose(latest["load_factor_reported"], 0.849)
    assert math.isclose(latest["rask_cents_per_km"], 9.941939075797343)
    assert math.isclose(latest["cask_cents_per_km"], 9.50697924123121)
    assert math.isclose(
        latest["unit_margin_cents_per_km"],
        latest["rask_cents_per_km"] - latest["cask_cents_per_km"],
        abs_tol=1e-12,
    )


@pytest.mark.local_data
def test_qoq_yoy_and_typed_deltas_are_correct(executive_payload) -> None:
    payload = executive_payload
    latest = payload["views"]["2026Q2"]
    kpis = {item["key"]: item for item in latest["kpis"]}
    assert math.isclose(
        kpis["passengers"]["qoq"]["raw"], 6_014_000 / 5_791_000 - 1
    )
    assert math.isclose(
        kpis["passengers"]["yoy"]["raw"], 6_014_000 / 6_180_000 - 1
    )
    assert kpis["load_factor_reported"]["qoq"]["display"] == "+0.5 pp"
    assert kpis["load_factor_reported"]["yoy"]["display"] == "-0.8 pp"
    assert latest["margin_qoq"]["display"] == "-0.68 ¢ USD"
    assert latest["margin_yoy"]["display"] == "-1.18 ¢ USD"


@pytest.mark.local_data
def test_missing_comparables_are_explicit_not_zero(executive_payload) -> None:
    payload = executive_payload
    first = payload["views"]["2021Q1"]
    for kpi in first["kpis"]:
        assert kpi["qoq"] == {
            "available": False,
            "raw": None,
            "display": "No disponible",
            "direction": "na",
        }
        assert kpi["yoy"] == {
            "available": False,
            "raw": None,
            "display": "No disponible",
            "direction": "na",
        }
