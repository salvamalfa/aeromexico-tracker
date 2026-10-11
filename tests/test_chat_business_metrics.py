from __future__ import annotations

from pathlib import Path

import pytest

from scripts.chat.build_business_metrics_proposal import (
    _preferred_sources,
    _source_priority,
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
    assert all(ref["public_artifact"] for ref in annual["source_references"])


def test_unlisted_gold_source_uses_wildcard_priority_before_lower_ranked_known_source() -> None:
    priorities = {"*": 2, "bmv_xbrl": 5}
    new_source = {"source_system": "future_public_source", "value_usd": 10}
    lower_ranked = {"source_system": "bmv_xbrl", "value_usd": 11}

    assert _source_priority()["*"] == 2
    assert _preferred_sources([lower_ranked, new_source], priorities) == [new_source]


def test_company_passenger_query_uses_public_snapshot_and_marks_partial_year_missing() -> None:
    snapshot = Snapshot(FIXTURE)
    result = deterministic_query(snapshot, "company_passengers", "AEROMEXICO", "2025H1")

    assert result["availability"] == "incomplete"
    assert result["value"] is None
    assert result["missing_periods"] == ["2025Q1", "2025Q2"]
    assert result["included_periods"] == []
    assert result["source_references"][0]["url"].endswith("executive.json")


@pytest.mark.parametrize("period", ["2025Q5", "2025M01", "2025H3", "2025Q1-Q4"])
def test_unsupported_aggregation_periods_are_rejected(period: str) -> None:
    with pytest.raises(ValueError, match="period debe tener formato"):
        aggregate_quarters([], period)
