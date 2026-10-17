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
    assert "assigned_slot_not_flown" in {route["operation_status"] for route in network["routes"]}
    for route in network["routes"]:
        if route.get("departures") is not None and str(route.get("operation_status", "")).startswith(
            "scheduled_"
        ):
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
    result = RouteTools(snapshot).invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "domestic",
            "period": "2026M06",
            "metric": "departures",
            "top_n": 5,
        },
    )
    assert result["rows"]
    assert all(row["value_kind"] == "estimated" for row in result["rows"])


def test_chat_query_and_shared_routes_preserve_mixed_flight_cell_kinds():
    from test_chat_route_tools import MemorySnapshot, _network, _paths, _route
    from src.conversational_analytics.tools._route_provenance import value_kind

    route = _route("JFK<>MEX", 100)
    route.update(
        departures=40,
        operation_status="mixed_observed_estimated_cells",
        passengers_estimated=True,
        capacity_estimated=True,
        load_factor_status="estimated",
        flight_components=[
            dict(
                carrier_key="AEROMEXICO",
                period_id="2026M04",
                kind="observed",
                departures=30,
                source_label="BTS T-100",
            ),
            dict(
                carrier_key="AEROMEXICO_CONNECT",
                period_id="2026M06",
                kind="estimated",
                departures=10,
                source_label="AeroDataBox",
            ),
            dict(
                carrier_key="AEROMEXICO_GROUP",
                period_id="2026M05",
                kind="scheduled",
                departures=20,
                source_label="AICM",
            ),
        ],
    )
    for metric in ("passengers", "seats", "load_factor"):
        assert value_kind({}, route, metric) == "estimated"
    tools = RouteTools(
        MemorySnapshot(
            _paths(
                {
                    (entity, "international", "2026Q2"): _network("2026Q2", [route])
                    for entity in ("AEROMEXICO_GROUP", "VIVA_AEROBUS")
                }
            )
        )
    )
    row = _route_query(tools, "JFK<>MEX", "departures")
    assert row["value"] == 40 and row["value_kind"] == "mixed"
    assert row["metric_provenance"]["component_totals"] == dict(observed=30, estimated=10, scheduled=20)
    assert row["metric_provenance"]["scheduled_excluded_from_value"] is True
    assert "AICM" not in row["metric_source_label"]
    shared = tools.invoke(
        "find_shared_routes",
        dict(
            entity_ids=["AEROMEXICO_GROUP", "VIVA_AEROBUS"],
            segment="international",
            period="2026Q2",
            metric="departures",
        ),
    )
    assert all(c["value_kind"] == "mixed" for c in shared["rows"][0]["carriers"].values())
    for kind in ("observed", "estimated", "scheduled"):
        assert (
            value_kind(
                {},
                dict(route, flight_components=[dict(route["flight_components"][0], kind=kind)]),
                "departures",
            )
            == kind
        )
