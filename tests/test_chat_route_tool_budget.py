import json
from pathlib import Path

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

    assert len(json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()) <= 16_000
    assert result["requested_top_n"] == 20
    assert result["applied_top_n"] == result["row_count"] == len(result["rows"])
    assert result["available_route_count"] >= result["row_count"]
    assert result["truncated"] is (result["row_count"] < result["available_route_count"])
    assert result["coverage"]
    assert result["carrier_metadata"]["AEROMEXICO_GROUP"]["label"]

    display = result["display"]
    assert display["title"] == (
        f"Rutas compartidas · 2026Q2 · {result['row_count']} de "
        f"{result['available_route_count']} mostradas"
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
