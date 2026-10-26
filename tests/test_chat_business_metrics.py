from __future__ import annotations

from pathlib import Path

import pytest

from scripts.chat.build_business_metrics_proposal import (
    _preferred_sources,
    _source_priority,
    _sources_have_compatible_usd_basis,
    build_proposal,
)
from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.tools.business_metrics import (
    BUSINESS_METRIC_TOOL_NAMES,
    aggregate_quarters,
    aggregate_weighted_ratio,
    business_metric_tool_specs,
    deterministic_query,
    dispatch_business_metric_tool,
    get_business_metric_definition,
    metric_proposals,
)

FIXTURE = Path(__file__).parent / "fixtures/chat/site"


def test_year_and_half_year_sum_only_complete_quarter_periods() -> None:
    records = [
        {"period_id": f"2025Q{quarter}", "value": value}
        for quarter, value in enumerate((10, 20, 30, 40), start=1)
    ]

    year = aggregate_quarters(records, "2025")
    first_half = aggregate_quarters(records, "2025H1")

    assert year["availability"] == "available"
    assert year["value"] == 100
    assert year["included_periods"] == ["2025Q1", "2025Q2", "2025Q3", "2025Q4"]
    assert first_half["value"] == 30
    assert first_half["expected_periods"] == ["2025Q1", "2025Q2"]


def test_missing_quarter_is_not_zero_or_a_partial_annual_total() -> None:
    result = aggregate_quarters(
        [
            {"period_id": "2025Q1", "value": 10},
            {"period_id": "2025Q2", "value": None},
            {"period_id": "2025Q3", "value": 30},
            {"period_id": "2025Q4", "value": 40},
        ],
        "2025",
    )

    assert result["availability"] == "incomplete"
    assert result["value"] is None
    assert result["missing_periods"] == ["2025Q2"]
    assert result["included_periods"] == ["2025Q1", "2025Q3", "2025Q4"]


def test_conflicting_duplicate_quarter_is_not_silently_overwritten() -> None:
    result = aggregate_quarters(
        [
            {"period_id": "2025Q1", "value": 10},
            {"period_id": "2025Q1", "value": 11},
            {"period_id": "2025Q2", "value": 20},
        ],
        "2025H1",
    )

    assert result["availability"] == "source_conflict"
    assert result["value"] is None
    assert result["conflicting_periods"] == ["2025Q1"]


def test_unit_ratios_use_denominator_weight_instead_of_simple_mean() -> None:
    result = aggregate_weighted_ratio(
        [
            {"period_id": "2025Q1", "value": 10, "weight": 1},
            {"period_id": "2025Q2", "value": 20, "weight": 3},
        ],
        "2025H1",
    )

    assert result["availability"] == "available"
    assert result["value"] == pytest.approx(17.5)
    assert result["value"] != pytest.approx(15)
    assert result["denominator_sum"] == 4


def test_load_factor_query_returns_ask_weighted_percent_from_fraction_inputs() -> None:
    snapshot = Snapshot(FIXTURE)
    quarter = deterministic_query(snapshot, "load_factor", "AEROMEXICO", "2026Q2")
    first_half = deterministic_query(snapshot, "load_factor", "AEROMEXICO", "2026H1")
    records = snapshot.payload("data/v1/executive.json")["entities"]["AEROMEXICO"]["records"]
    q1, q2 = records[0], records[1]
    expected_h1 = (
        (q1["load_factor"] * q1["ask_km"] + q2["load_factor"] * q2["ask_km"])
        / (q1["ask_km"] + q2["ask_km"])
        * 100
    )

    assert quarter["unit"] == "percent"
    assert quarter["value"] == pytest.approx(84.9)
    assert first_half["value"] == pytest.approx(expected_h1)
    assert first_half["value"] != pytest.approx(0.848)
    assert first_half["numerator_sum"] == pytest.approx(
        (q1["load_factor"] * q1["ask_km"] + q2["load_factor"] * q2["ask_km"]) * 100
    )


def test_reading_q3_context_cannot_relabel_q2_financial_observations() -> None:
    snapshot = Snapshot(FIXTURE)
    q2 = deterministic_query(snapshot, "load_factor", "AEROMEXICO", "2026Q2")
    q3 = deterministic_query(snapshot, "load_factor", "AEROMEXICO", "2026Q3")
    assert q2["availability"] == "available"
    assert q3["availability"] == "incomplete"
    assert q3["value"] is None
    assert q3["missing_periods"] == ["2026Q3"]
    assert q3["included_periods"] == []


def test_closed_financial_candidate_gate_never_returns_a_value() -> None:
    result = deterministic_query(Snapshot(FIXTURE), "total_revenue", "AEROMEXICO", "2025")
    candidate = next(
        item for item in metric_proposals()["candidate_metrics"] if item["id"] == "total_revenue"
    )

    assert result["approval_gate"] == "closed"
    assert result["availability"] == "approval_required"
    assert result["value"] is None
    assert candidate["site_chat_coverage"].startswith("none;")


def test_standalone_specs_and_dispatch_keep_candidates_behind_closed_gate() -> None:
    snapshot = Snapshot(FIXTURE)
    specs = business_metric_tool_specs()
    definition = get_business_metric_definition("total_revenue")
    result = dispatch_business_metric_tool(
        snapshot,
        "query_business_metrics",
        {"metric_id": "total_revenue", "entity_id": "AEROMEXICO", "period": "2025"},
    )

    assert tuple(spec["name"] for spec in specs) == BUSINESS_METRIC_TOOL_NAMES
    assert definition["approval_gate"] == "closed"
    assert definition["production_enabled"] is False
    assert result["value"] is None
    assert result["approval_gate"] == "closed"


def test_gold_proposal_is_review_only_and_aggregates_complete_year_from_quarters() -> None:
    proposal = build_proposal()
    rows = {(row["metric_id"], row["entity_id"], row["period"]): row for row in proposal["rows"]}
    quarter_rows = [rows[("total_revenue", "AEROMEXICO", f"2025Q{quarter}")] for quarter in range(1, 5)]
    annual = rows[("total_revenue", "AEROMEXICO", "2025")]

    assert proposal["metadata"]["production_enabled"] is False
    assert proposal["metadata"]["approval_status"] == "owner_review_required_nonproduction_candidate"
    assert all(row["approval_status"] == proposal["metadata"]["approval_status"] for row in proposal["rows"])
    assert all(row["availability"] == "available" for row in quarter_rows)
    assert annual["value"] == pytest.approx(sum(row["value"] for row in quarter_rows))
    assert annual["aggregation"] == "deterministic_sum_of_selected_quarter_value_usd"
    assert annual["source_references"]
    assert annual["value"] == pytest.approx(5_361_000_000)
    assert all(ref["url"].startswith("https://") and ref["sha256"] for ref in annual["source_references"])
    audited = {
        row["metric_id"]: row["value"]
        for row in proposal["rows"]
        if row["entity_id"] == "AEROMEXICO" and row["period"] == "2025" and row["availability"] == "available"
    }
    assert audited["operating_costs"] == pytest.approx(4_433_000_000)
    assert audited["fuel_expense"] == pytest.approx(1_138_000_000)
    assert audited["operating_income"] == pytest.approx(927_900_000)
    q2_2026 = next(
        row
        for row in proposal["rows"]
        if row["metric_id"] == "total_revenue"
        and row["entity_id"] == "AEROMEXICO"
        and row["period"] == "2026Q2"
    )
    assert q2_2026["any_preliminary"] is True
    current_check = q2_2026["source_references"][0]["current_identity_check"]
    assert current_check["status"] == "byte_identity_mismatch_factual_values_match"
    assert current_check["current_bytes"] == 230386


def test_unlisted_gold_source_uses_wildcard_priority_before_lower_ranked_known_source() -> None:
    priorities = {"*": 2, "bmv_xbrl": 5}
    new_source = {"source_system": "future_public_source", "value_usd": 10}
    lower_ranked = {"source_system": "bmv_xbrl", "value_usd": 11}

    assert _source_priority()["*"] == 2
    assert _preferred_sources([lower_ranked, new_source], priorities) == [new_source]


def test_currency_conversion_and_normalized_unit_must_be_explicit() -> None:
    mxn = {
        "unit_normalized": "usd",
        "currency": "MXN",
        "fx_rate_used": 0.058,
        "fx_rate_type": "quarter_average",
    }
    assert _sources_have_compatible_usd_basis([mxn])
    assert not _sources_have_compatible_usd_basis([{**mxn, "fx_rate_used": None}])
    assert not _sources_have_compatible_usd_basis([{**mxn, "unit_normalized": "USD millions"}])


def test_company_passenger_query_uses_public_snapshot_and_marks_partial_year_missing() -> None:
    snapshot = Snapshot(FIXTURE)
    result = deterministic_query(snapshot, "company_passengers", "AEROMEXICO", "2025H1")

    assert result["availability"] == "incomplete"
    assert result["value"] is None
    assert result["missing_periods"] == ["2025Q1", "2025Q2"]
    assert result["included_periods"] == []
    assert result["source_references"][0]["url"].endswith("executive.json")


def test_published_rask_uses_ask_weight_and_reports_denominator() -> None:
    result = deterministic_query(Snapshot(FIXTURE), "rask_cents_per_km", "AEROMEXICO", "2026Q1")
    source = Snapshot(FIXTURE).payload("data/v1/executive.json")["entities"]["AEROMEXICO"]["records"][0]
    assert result["availability"] == "available"
    assert result["value"] == source["rask_cents_per_km"]
    assert result["denominator"] == "ask_km"
    assert result["denominator_sum"] == source["ask_km"]


@pytest.mark.parametrize("period", ["2025Q5", "2025M01", "2025H3", "2025Q1-Q4"])
def test_unsupported_aggregation_periods_are_rejected(period: str) -> None:
    with pytest.raises(ValueError, match="period debe tener formato"):
        aggregate_quarters([], period)
