import json
from pathlib import Path

from _published_flight_profiles import has_signed_flight_components
from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.tools.routes import RouteTools


def test_default_shared_route_result_fits_provider_budget_and_keeps_display_valid() -> None:
    tools = RouteTools(Snapshot(Path("site")))
    result = tools.invoke(
        "find_shared_routes",
        {
            "entity_ids": ["AEROMEXICO_GROUP", "VOLARIS", "VIVA_AEROBUS"],
            "segment": "domestic",
            "period": "2026Q2",
            "metric": "passengers",
            "top_n": 20,
        },
    )

    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    assert len(encoded.encode()) <= 16_000
    assert result["requested_top_n"] == 20
    assert result["applied_top_n"] == result["row_count"] == len(result["rows"])
    assert result["available_route_count"] >= result["row_count"]
    assert result["truncated"] is (result["row_count"] < result["available_route_count"])
    assert result["coverage"]
    assert result["carrier_metadata"]["AEROMEXICO_GROUP"]["label"]

    display = result["display"]
    assert display["title"] == (
        f"Rutas compartidas · 2026Q2 · {result['row_count']} de {result['available_route_count']} mostradas"
    )
    assert len(display["columns"]) == len({column["key"] for column in display["columns"]})
    keys = {column["key"] for column in display["columns"]}
    assert all(set(row) == keys for row in display["rows"])
    assert all(
        value is None or isinstance(value, (str, int, float, bool))
        for row in display["rows"]
        for value in row.values()
    )
    for row_index, row in enumerate(result["rows"]):
        assert "coverage" not in row
        for entity_id, carrier in row["carriers"].items():
            shown = display["rows"][row_index]
            assert shown[f"{entity_id}_value"] == carrier["value"]
            assert shown[f"{entity_id}_value_kind"] == carrier["value_kind"]
            source_label = result["carrier_metadata"][entity_id]["source_labels"][carrier["source_ref"]]
            assert shown[f"{entity_id}_source_label"]
            assert source_label


def test_shared_route_size_limit_reports_applied_and_available_counts() -> None:
    tools = RouteTools(Snapshot(Path("site")))
    result = tools.invoke(
        "find_shared_routes",
        {
            "entity_ids": ["AEROMEXICO_GROUP", "VOLARIS", "VIVA_AEROBUS"],
            "segment": "domestic",
            "period": "2026Q2",
            "metric": "passengers",
            "top_n": 20,
        },
    )
    assert result["available_route_count"] >= result["requested_top_n"]
    assert result["row_count"] <= result["requested_top_n"]
    assert result["applied_top_n"] == result["row_count"]
    if result["row_count"] < result["requested_top_n"]:
        assert result["truncated"] is True
        assert result["truncation_reason"] == "tool_result_size_limit"


def test_real_international_quarter_route_queries_fit_presented_tool_budget() -> None:
    import json
    from types import SimpleNamespace

    from src.conversational_analytics.presentation import DisplayRegistry
    from src.conversational_analytics.tools.registry import ToolRegistry

    snapshot = Snapshot(Path("site"))
    registry = ToolRegistry(snapshot, SimpleNamespace(enable_route_tools=True))
    available_routes = 102 if has_signed_flight_components(snapshot) else 75
    for top_n, comparison_period in ((None, None), (20, None), (None, "2026Q1"), (20, "2026Q1")):
        query = {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "international",
            "period": "2026Q2",
            "metric": "seats",
        }
        if comparison_period is not None:
            query["comparison_period"] = comparison_period
        if top_n is not None:
            query["top_n"] = top_n
        result = registry.invoke("query_routes", query)
        raw_bytes = len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode())
        enriched = DisplayRegistry().add_tool_result(result, "query_routes", "route-call")
        final_bytes = len(json.dumps(enriched, ensure_ascii=False, separators=(",", ":")).encode())
        expected = top_n or 10

        assert raw_bytes <= 15_000
        assert final_bytes <= 15_652
        assert result["requested_top_n"] == expected
        assert result["available_route_count"] == available_routes
        assert result["applied_top_n"] == len(result["rows"]) <= expected
        assert result["truncated"] is True
        assert result["truncation_reason"] == "tool_result_size_limit"
        assert result["display"]["title"].endswith(f"{available_routes} mostradas")
        assert len(result["display"]["rows"]) == len(result["rows"])
        assert result["rows"]
        assert all(row["metric_provenance"] for row in result["rows"])
        assert all(row["value"] is not None for row in result["rows"])
        assert all(row["value_kind"] in {"observed", "estimated", "scheduled"} for row in result["rows"])
        assert isinstance(result["coverage"]["2026Q2"]["complete"], bool)
        assert result["coverage"]["2026Q2"]["availability"] in {"complete", "partial"}
        if comparison_period is not None:
            assert all(row["comparison"] is not None for row in result["rows"])
            assert all(isinstance(row["comparison"]["available"], bool) for row in result["rows"])
        assert enriched["displays"][0]["display_id"] == result["display"]["display_id"]


def test_shared_route_queries_fit_presented_budget_and_display_contract() -> None:
    from types import SimpleNamespace

    from src.conversational_analytics.presentation import DisplayRegistry
    from src.conversational_analytics.tools.registry import ToolRegistry

    snapshot = Snapshot(Path("site"))
    registry = ToolRegistry(snapshot, SimpleNamespace(enable_route_tools=True))
    cases = (
        (["AEROMEXICO_GROUP", "VIVA_AEROBUS"], "2026M07"),
        (["AEROMEXICO_GROUP", "VOLARIS", "VIVA_AEROBUS"], "2026Q2"),
    )
    for entity_ids, period in cases:
        for metric in ("passengers", "seats", "departures"):
            for top_n in (None, 20):
                query = {
                    "entity_ids": entity_ids,
                    "segment": "domestic",
                    "period": period,
                    "metric": metric,
                }
                if top_n is not None:
                    query["top_n"] = top_n
                result = registry.invoke("find_shared_routes", query)
                enriched = DisplayRegistry().add_tool_result(result, "find_shared_routes", "shared-call")
                final_bytes = len(json.dumps(enriched, ensure_ascii=False, separators=(",", ":")).encode())
                assert final_bytes < 16_000
                assert len(result["display"]["columns"]) <= 12
                assert len(enriched["displays"]) == 1
                display = enriched["displays"][0]
                assert display["columns"]
                assert display["rows"]
                assert len(display["columns"]) <= 12
                assert all(len(row) == len(display["columns"]) for row in display["rows"])
                assert result["requested_top_n"] == (top_n or 10)
                assert result["row_count"] == result["applied_top_n"] == len(result["rows"])
                assert result["available_route_count"] >= result["row_count"]
                assert result["truncated"] is (result["row_count"] < result["available_route_count"])
                assert result["coverage"].keys() == set(entity_ids)
                for carrier_coverage in result["coverage"].values():
                    assert carrier_coverage["availability"] in {"complete", "partial"}
                    assert isinstance(carrier_coverage["expected_months"], list)
                    assert isinstance(carrier_coverage["observed_months"], list)
                    assert carrier_coverage["eligibility_reason"]
                assert set(result["carrier_metadata"]) == set(entity_ids)
                for row in result["rows"]:
                    assert set(row["carriers"]) == set(entity_ids)
                    assert isinstance(row["comparable"], bool)
                    assert isinstance(row["comparability_reason"], list)
                    for entity_id, carrier in row["carriers"].items():
                        assert carrier["value"] is not None
                        assert carrier["value_kind"] in {"observed", "estimated", "scheduled"}
                        source_ref = carrier["source_ref"]
                        source_labels = result["carrier_metadata"][entity_id]["source_labels"]
                        assert source_ref in source_labels
                        assert source_labels[source_ref]
                columns = {column["key"] for column in display["columns"]}
                for entity_id in entity_ids:
                    assert f"{entity_id}_value_kind" in columns
                    assert f"{entity_id}_source_label" in columns
                for row in display["rows"]:
                    for entity_id in entity_ids:
                        assert row[f"{entity_id}_value_kind"]
                        assert row[f"{entity_id}_source_label"]
                if len(entity_ids) == 3:
                    assert "coverage_summary" not in columns
                    assert "comparability_reason" in columns
