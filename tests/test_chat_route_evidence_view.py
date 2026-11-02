"""The map's observed NA view is applied before tool ranking and comparisons."""

import copy
import json
from pathlib import Path

import pytest
from test_chat_route_tools import MemorySnapshot, _network, _paths, _route

from src.conversational_analytics.tools._route_view import observed_north_america_view, route_region
from src.conversational_analytics.tools.registry import ToolRegistry
from src.conversational_analytics.tools.routes import RouteTools


def _mixed_network():
    mixed = _route("MEX<>JFK", 300)
    mixed["flight_components"] = [
        dict(
            kind=kind,
            departures=count,
            source_label=source,
            period_id="2026M07",
            origin_iata="MEX",
            destination_iata="JFK",
            carrier_key="AEROMEXICO",
        )
        for kind, count, source in [
            ("observed", 100, "BTS T-100"),
            ("estimated", 200, "AeroDataBox"),
            ("scheduled", 50, "Programación"),
        ]
    ]
    mixed["departures"] = 300
    mixed["recorded_movements"] = {"count": 77}
    estimated = _route("MEX<>YVR", 1000)
    estimated["departures"] = 1000
    europe = _route("MEX<>CDG", 80)
    europe["departures"] = 80
    return _network("2026Q3", [mixed, estimated, europe])


def test_projection_uses_observed_components_drops_unobserved_na_and_keeps_other_regions():
    network = _mixed_network()
    before = copy.deepcopy(network)
    view = observed_north_america_view(network)
    assert [(row["market_key"], row["departures"]) for row in view["routes"]] == [
        ("MEX<>JFK", 100),
        ("MEX<>CDG", 80),
    ]
    observed = view["routes"][0]
    assert observed["passengers"] is None and observed["seats"] is None
    assert observed["source_label"] == "BTS T-100"
    assert observed["directions"] == [{"origin_iata": "MEX", "destination_iata": "JFK", "departures": 100}]
    assert "recorded_movements" not in observed
    assert network == before


def test_registry_applies_validated_context_before_top_n_without_mutating_the_snapshot():
    network = _mixed_network()
    before = copy.deepcopy(network)
    registry = object.__new__(ToolRegistry)
    registry.snapshot = MemorySnapshot(_paths({("AEROMEXICO_GROUP", "international", "2026Q3"): network}))
    registry._active_tool_names = {"query_routes"}
    arguments = {
        "entity_id": "AEROMEXICO_GROUP",
        "segment": "international",
        "period": "2026Q3",
        "metric": "departures",
        "top_n": 1,
    }
    context = {
        "tab": "flights",
        "period": "2026Q3",
        "card_id": "route-flow-map",
        "filters": {"network_mode": "international", "flight_evidence": "north_america_observed"},
    }
    baseline = registry.invoke("query_routes", arguments)
    selected = registry.invoke("query_routes", arguments, context)
    assert baseline["rows"][0]["market_key"] == "MEX<>YVR"
    assert selected["rows"][0]["market_key"] == "MEX<>JFK"
    assert selected["rows"][0]["value"] == 100
    assert selected["rows"][0]["value_kind"] == "observed"
    assert selected["available_route_count"] == 2
    assert selected["query"]["flight_evidence"] == "north_america_observed"
    assert "sólo vuelos observados" in selected["flight_evidence_scope"]
    assert network == before
    context["filters"]["region"] = "norteamerica"
    selected = registry.invoke("query_routes", arguments, context)
    assert selected["available_route_count"] == 1


@pytest.mark.parametrize("entity", ["AEROMEXICO_GROUP", "INDUSTRY", "VOLARIS", "VIVA_AEROBUS"])
@pytest.mark.parametrize("period", ["2026Q2", "2026Q3"])
def test_real_retained_networks_keep_only_observed_na_flights_and_original_other_regions(entity, period):
    prefix = "flights" if entity == "AEROMEXICO_GROUP" else f"flights/entities/{entity}"
    path = f"data/v1/{prefix}/international/{period}.json"
    source = json.loads((Path(__file__).parents[1] / "site" / path).read_text(encoding="utf-8"))
    snapshot = MemorySnapshot({path: source})
    before = copy.deepcopy(source)
    full = RouteTools(snapshot, evidence_view="north_america_observed")._load(
        entity, "international", period
    )[0]
    na = RouteTools(snapshot, evidence_view="north_america_observed", region="norteamerica")._load(
        entity, "international", period
    )[0]
    assert full is not None and na is not None
    originals = {route["market_key"]: route for route in source["routes"]}
    for route in full["routes"]:
        if route_region(route) != "norteamerica":
            assert route == originals[route["market_key"]]
        elif route.get("flight_components"):
            expected = [
                row
                for row in originals[route["market_key"]]["flight_components"]
                if row["kind"] == "observed"
            ]
            assert route["flight_components"] == expected
            assert route["departures"] == sum(row["departures"] for row in expected)
            assert len(expected) > 0
        else:
            assert route["operation_status"] == "operated_observed" or "T-100" in route.get(
                "source_label", ""
            )
    assert all(route_region(route) == "norteamerica" for route in na["routes"])
    assert {row["market_key"] for row in na["routes"]} == {
        row["market_key"] for row in full["routes"] if route_region(row) == "norteamerica"
    }
    assert source == before
    # Independent totals produced by the real TypeScript consumer over the
    # same retained payloads, including the mixed-component split.
    expected_totals = {
        "AEROMEXICO_GROUP": {"2026Q2": 6954, "2026Q3": 367},
        "INDUSTRY": {"2026Q2": 21630, "2026Q3": 6251},
        "VOLARIS": {"2026Q2": 11029, "2026Q3": 4287},
        "VIVA_AEROBUS": {"2026Q2": 3647, "2026Q3": 1597},
    }
    assert sum(row.get("departures") or 0 for row in na["routes"]) == expected_totals[entity][period]


def test_cross_language_frontend_receipt_when_available():
    receipt = Path(__file__).parents[1] / "tmp/north-america-observed/frontend-receipt.json"
    if not receipt.is_file():
        pytest.skip("Optional local browser-consumer parity evidence not present")
    root = Path(__file__).parents[1] / "site"
    for case in json.loads(receipt.read_text(encoding="utf-8")):
        if case["region"] not in {None, "norteamerica"}:
            continue
        entity = "AEROMEXICO_GROUP" if case["entity"] == "AEROMEXICO" else case["entity"]
        prefix = "flights" if entity == "AEROMEXICO_GROUP" else f"flights/entities/{entity}"
        path = f"data/v1/{prefix}/international/{case['period']}.json"
        snapshot = MemorySnapshot({path: json.loads((root / path).read_text(encoding="utf-8"))})
        projected = RouteTools(snapshot, evidence_view="north_america_observed", region=case["region"])._load(
            entity, "international", case["period"]
        )[0]
        actual = [
            {
                "market_key": row["market_key"],
                "departures": row.get("departures"),
                "components": [
                    {"kind": c["kind"], "departures": c["departures"], "source": c["source_label"]}
                    for c in row.get("flight_components", [])
                ],
            }
            for row in projected["routes"]
        ]
        assert sorted(actual, key=lambda row: row["market_key"]) == sorted(
            case["routes"], key=lambda row: row["market_key"]
        )
