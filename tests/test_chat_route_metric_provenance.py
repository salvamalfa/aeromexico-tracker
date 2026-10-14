from pathlib import Path

from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.tools.routes import RouteTools


def _route_query(tools: RouteTools, market: str, metric: str) -> dict:
    origin, destination = market.split("<>")
    return tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "international",
            "period": "2026Q2",
            "metric": metric,
            "origin_iata": origin,
            "destination_iata": destination,
            "top_n": 1,
        },
    )["rows"][0]


def test_published_international_metrics_preserve_observed_values_and_remove_enrichment() -> None:
    tools = RouteTools(Snapshot(Path("site")))
    for metric in ("passengers", "departures", "seats", "load_factor"):
        assert _route_query(tools, "LAX<>MEX", metric)["value_kind"] == "observed"
    for market in ("GUA<>MEX", "CDG<>MTY"):
        assert _route_query(tools, market, "departures")["value_kind"] == "scheduled"
        origin, destination = market.split("<>")
        for metric in ("passengers", "seats", "load_factor"):
            result = tools.invoke("query_routes", {
                "entity_id": "AEROMEXICO_GROUP", "segment": "international", "period": "2026Q2",
                "metric": metric, "origin_iata": origin, "destination_iata": destination, "top_n": 1,
            })
            assert result["rows"] == []


def test_published_scheduled_statuses_classify_departures_not_capacity() -> None:
    tools = RouteTools(Snapshot(Path("site")))
    network, _ = tools._load("AEROMEXICO_GROUP", "international", "2026Q2")
    scheduled = {
        route["operation_status"]
        for route in network["routes"]
        if str(route.get("operation_status", "")).startswith("scheduled_")
    }
    assert "scheduled_from_dated_release" in scheduled
    assert "assigned_slot_not_flown" in {
        route["operation_status"] for route in network["routes"]
    }
    for route in network["routes"]:
        if route.get("departures") is not None and str(route.get("operation_status", "")).startswith("scheduled_"):
            row = _route_query(tools, route["market_key"], "departures")
            assert row["value_kind"] == "scheduled"
            if route.get("capacity_estimated"):
                assert _route_query(tools, route["market_key"], "seats")["value_kind"] == "estimated"
