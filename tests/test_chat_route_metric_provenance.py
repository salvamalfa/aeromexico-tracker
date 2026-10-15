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


def test_published_international_metric_provenance_is_component_specific() -> None:
    tools = RouteTools(Snapshot(Path("site")))
    expected = {
        "LAX<>MEX": ("observed", "observed", "observed"),
        "GUA<>MEX": ("estimated", "scheduled", "estimated"),
        "CDG<>MTY": ("estimated", "scheduled", "estimated"),
    }
    for market, kinds in expected.items():
        rows = {
            metric: _route_query(tools, market, metric)
            for metric in ("passengers", "departures", "load_factor")
        }
        assert tuple(rows[metric]["value_kind"] for metric in rows) == kinds
        assert all(row["metric_source_label"] for row in rows.values())
        assert rows["load_factor"]["value"] <= 100

        if market in {"GUA<>MEX", "CDG<>MTY"}:
            seats = _route_query(tools, market, "seats")
            assert seats["value_kind"] == "estimated"
            assert "AICM" not in seats["metric_source_label"]
            assert "OMA" not in seats["metric_source_label"]
            provenance = seats["capacity_provenance"]
            assert provenance["method"] == "captured_schedule_x_operator_aircraft_configuration_v1"
            assert provenance["version"] == "v1"
            assert "Aeromexico aircraft seat-capacity reference" in provenance["inputs"]

    gua_passengers = _route_query(tools, "GUA<>MEX", "passengers")
    assert gua_passengers["metric_source_label"].startswith("AFAC + AeroDataBox")


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


def test_attributed_market_counts_are_never_observed_company_flights():
    from src.conversational_analytics.tools._route_provenance import metric_provenance, value_kind

    route = {"departures": 90, "operation_status": "carrier_inferred_market_observed", "source_label": "AFAC"}
    assert value_kind({}, route, "departures") == "estimated"
    provenance = metric_provenance({}, route, "departures", "AEROMEXICO_GROUP")
    assert provenance["method"] == "market_total_attribution_not_observed_carrier_operations"


def test_frozen_domestic_flight_estimates_remain_queryable_without_relabelling_as_observed():
    import json

    snapshot = Snapshot(Path("site"))
    relative = "data/v1/flights/domestic/2026M06.json"
    # No policy removes route passengers, frequencies or their historical provenance.
    assert snapshot.payload(relative) == json.loads((Path("site") / relative).read_text())
    result = RouteTools(snapshot).invoke("query_routes", {
        "entity_id": "AEROMEXICO_GROUP", "segment": "domestic", "period": "2026M06",
        "metric": "departures", "top_n": 5,
    })
    assert result["rows"]
    assert all(row["value_kind"] == "estimated" for row in result["rows"])
