from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.tools.registry import ToolRegistry

FIXTURE = Path(__file__).parent / "fixtures/chat/site"


def test_explicit_query_arguments_are_not_replaced_by_dashboard_defaults() -> None:
    tools = ToolRegistry(Snapshot(FIXTURE))
    result = tools.invoke(
        "query_metrics",
        {"metric_ids": ["load_factor"], "entity_ids": ["AEROMEXICO"], "periods": ["2026Q2"]},
        context={"period": "2026Q1", "entity": "VOLARIS"},
    )

    assert [(row["metric_id"], row["entity_id"], row["period"]) for row in result["rows"]] == [
        ("load_factor", "AEROMEXICO", "2026Q2")
    ]


def test_unavailable_explicit_period_stays_missing_instead_of_falling_back() -> None:
    tools = ToolRegistry(Snapshot(FIXTURE))
    result = tools.invoke(
        "query_metrics",
        {"metric_ids": ["load_factor"], "entity_ids": ["AEROMEXICO"], "periods": ["2026Q3"]},
        context={"period": "2026Q2", "entity": "AEROMEXICO"},
    )

    assert len(result["rows"]) == 1
    row = result["rows"][0]
    assert (row["metric_id"], row["entity_id"], row["period"]) == (
        "load_factor",
        "AEROMEXICO",
        "2026Q3",
    )
    assert row["availability"] == "missing"
    assert row["value"] is None


def test_company_and_afac_passenger_queries_keep_distinct_provenance_and_grain() -> None:
    tools = ToolRegistry(Snapshot(FIXTURE))
    company = tools.invoke("get_metric_definition", {"metric_id": "company_passengers"})["metric"]
    afac = tools.invoke("get_metric_definition", {"metric_id": "afac_passengers"})["metric"]
    company_result = tools.invoke(
        "query_metrics",
        {"metric_ids": [company["id"]], "entity_ids": ["AEROMEXICO"], "periods": ["2026Q2"]},
    )
    afac_result = tools.invoke(
        "query_metrics",
        {
            "metric_ids": [afac["id"]],
            "entity_ids": ["AEROMEXICO"],
            "periods": ["2026Q2"],
            "segment": "total",
        },
        context={"filters": {"segment": "domestic"}},
    )

    assert company["source"] != afac["source"]
    assert company["period_grains"] == ["quarter"]
    assert afac["period_grains"] == ["month", "quarter"]
    company_row = company_result["rows"][0]
    afac_row = afac_result["rows"][0]
    assert company_row["metric_id"] == company["id"]
    assert afac_row["metric_id"] == afac["id"]
    assert company_row["unit"] == afac_row["unit"] == "passengers"
    assert company_row.get("segment") is None
    assert afac_row["segment"] == "total"
    assert company_result["references"] and afac_result["references"]
    assert {urlparse(ref["url"]).hostname for ref in company_result["references"]} != {
        urlparse(ref["url"]).hostname for ref in afac_result["references"]
    }
