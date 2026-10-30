from pathlib import Path

from _published_flight_profiles import (
    LEGACY_SCHEDULED_DEPARTURES,
    LEGACY_SHARED_PASSENGERS,
    MOVEMENT_COUNTS_2026Q2,
    MOVEMENT_SCHEDULED_DEPARTURES,
    MOVEMENT_SHARED_TOTALS_2026Q2,
    has_recorded_movements,
    has_regular_map_projection,
    has_signed_flight_components,
)

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
    components = has_signed_flight_components(tools.snapshot)
    frequency_kind = "estimated" if components else "scheduled"
    expected = {
        "LAX<>MEX": ("observed", "observed", "observed"),
        "GUA<>MEX": ("estimated", frequency_kind, "estimated"),
        "CDG<>MTY": ("estimated", frequency_kind, "estimated"),
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
    components = has_signed_flight_components(tools.snapshot)
    network, _ = tools._load("AEROMEXICO_GROUP", "international", "2026Q2")
    scheduled = [
        route
        for route in network["routes"]
        if (
            route.get("flight_components")
            and all(cell["kind"] == "scheduled" for cell in route["flight_components"])
        )
        or (
            not route.get("flight_components")
            and (
                route["operation_status"].startswith("scheduled_")
                or route["operation_status"] == "assigned_slot_not_flown"
            )
        )
    ]
    regular = has_regular_map_projection(tools.snapshot)
    expected = (
        MOVEMENT_SCHEDULED_DEPARTURES
        if has_recorded_movements(tools.snapshot)
        else {"MEX<>SNA": None if regular else 182}
        if components
        else LEGACY_SCHEDULED_DEPARTURES
    )
    assert {route["market_key"]: route["departures"] for route in scheduled} == expected
    for route in scheduled:
        assert bool(route.get("flight_components")) is components
        assert route["operation_status"] == (
            "scheduled_from_dated_release" if route["market_key"] == "CDG<>MTY" else "assigned_slot_not_flown"
        )
        if regular and expected[route["market_key"]] is None:
            # Programming remains explicit evidence, never a performed-flight
            # headline or a queryable departure value. Capacity stays distinct.
            assert sum(cell["departures"] for cell in route["flight_components"]) == 182
            result = tools.invoke(
                "query_routes",
                dict(
                    entity_id="AEROMEXICO_GROUP",
                    segment="international",
                    period="2026Q2",
                    metric="departures",
                    origin_iata="MEX",
                    destination_iata="SNA",
                    top_n=1,
                ),
            )
            assert result["rows"] == [] and result["missing_route_count"] == 1
            assert route["seats"] is None  # Preserve the original missing capacity.
            continue
        row = _route_query(tools, route["market_key"], "departures")
        assert row["value_kind"] == "scheduled"
        assert row["value"] == expected[route["market_key"]]
        if components:
            assert row["value"] == sum(cell["departures"] for cell in route["flight_components"])


def test_signed_movement_contract_keeps_literal_counts_separate_from_queryable_flights():
    tools = RouteTools(Snapshot(Path("site")))
    if not has_recorded_movements(tools.snapshot):
        return  # The three frozen older editions do not carry this typed metric.
    network, _ = tools._load("AEROMEXICO_GROUP", "international", "2026Q2")
    movements = {r["market_key"]: r for r in network["routes"] if r.get("recorded_movements")}
    assert {
        key: row["recorded_movements"]["count"] for key, row in movements.items()
    } == MOVEMENT_COUNTS_2026Q2
    for market, row in movements.items():
        movement = row["recorded_movements"]
        assert movement["count"] == sum(c["operations"] for c in movement["components"])
        assert movement["provisional"] is True
        assert movement["official_classification_confirmed"] is False
        assert movement["agent_eligible"] is False
        assert movement["traffic_code"] == "I" and movement["flight_type_code"] == "S"
        assert "No equivalen a salidas" in movement["definition"]
        assert all("Aerocivil" not in c["source_label"] for c in row["flight_components"])
        if market == "BOG<>TGZ":
            assert row["operation_status"] == "recorded_movements_provisional"
            assert row["flight_components"] == []
            for metric in ("departures", "seats", "passengers", "load_factor"):
                assert row[metric] is None
                result = tools.invoke(
                    "query_routes",
                    dict(
                        entity_id="AEROMEXICO_GROUP",
                        segment="international",
                        period="2026Q2",
                        metric=metric,
                        origin_iata="BOG",
                        destination_iata="TGZ",
                        top_n=1,
                    ),
                )
                assert result["rows"] == [] and result["missing_route_count"] == 1
        else:
            scheduled = _route_query(tools, market, "departures")
            assert scheduled["value"] == MOVEMENT_SCHEDULED_DEPARTURES[market]
            assert scheduled["value_kind"] == "scheduled"
            assert "AICM" in scheduled["metric_source_label"]
            assert "Aerocivil" not in scheduled["metric_source_label"]


def test_signed_profiles_preserve_frozen_versions_and_reject_unknown_contracts():
    from types import SimpleNamespace

    import pytest
    from _published_flight_profiles import (
        COMPONENT_FLIGHTS,
        LEGACY_FLIGHTS,
        MOVEMENT_FLIGHTS,
        REGULAR_MAP_FLIGHTS,
    )

    for digest, expected in (
        (LEGACY_FLIGHTS, (False, False, False)),
        (COMPONENT_FLIGHTS, (True, False, False)),
        (REGULAR_MAP_FLIGHTS, (True, True, False)),
        (MOVEMENT_FLIGHTS, (True, True, True)),
    ):
        snapshot = SimpleNamespace(manifest={"contracts": {"flights.schema.json": digest}})
        assert (
            has_signed_flight_components(snapshot),
            has_regular_map_projection(snapshot),
            has_recorded_movements(snapshot),
        ) == expected
    unknown = SimpleNamespace(manifest={"contracts": {"flights.schema.json": "0" * 64}})
    for select in (has_signed_flight_components, has_regular_map_projection, has_recorded_movements):
        with pytest.raises(AssertionError, match="Review published-route expectations"):
            select(unknown)


def test_legacy_scheduled_statuses_keep_capacity_estimated():
    from src.conversational_analytics.tools._route_provenance import value_kind

    for status in ("scheduled_from_dated_release", "scheduled_authority", "assigned_slot_not_flown"):
        route = {"operation_status": status, "capacity_estimated": True, "departures": 20, "seats": 2000}
        assert value_kind({}, route, "departures") == "scheduled"
        assert value_kind({}, route, "seats") == "estimated"


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


def test_queries_the_signed_public_snapshot_without_private_inputs() -> None:
    tools = RouteTools(Snapshot(Path("site")))
    components = has_signed_flight_components(tools.snapshot)
    result = tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "domestic",
            "period": "2026M07",
            "metric": "passengers",
            "top_n": 3,
        },
    )
    assert result["rows"]
    assert result["rows"][0]["value_kind"] == "estimated"
    assert result["data_version"] == tools.snapshot.version
    assert result["sources"][0]["url"].endswith("domestic/2026M07.json")

    international = tools.invoke(
        "query_routes",
        {
            "entity_id": "AEROMEXICO_GROUP",
            "segment": "international",
            "period": "2026Q2",
            "metric": "passengers",
            "top_n": 3,
        },
    )
    assert international["rows"]
    # Calendar completeness does not certify worldwide or historical evidence coverage.
    expected_months = ["2026M04", "2026M05", "2026M06"] if components else ["2026M04", "2026M05"]
    assert international["coverage"]["2026Q2"]["complete"] is components
    assert international["coverage"]["2026Q2"]["observed_months"] == expected_months
    assert international["coverage"]["2026Q2"]["agent_eligible"] is False
    assert {row["value_kind"] for row in international["rows"]} <= {"observed", "estimated", "scheduled"}
    assert all(row["source_label"] and row["operation_status"] for row in international["rows"])

    shared = tools.invoke(
        "find_shared_routes",
        {
            "entity_ids": ["AEROMEXICO_GROUP", "VIVA_AEROBUS"],
            "segment": "domestic",
            "period": "2026M07",
            "top_n": 3,
        },
    )
    assert shared["rows"]
    assert all(row["carriers"]["AEROMEXICO_GROUP"]["value"] > 0 for row in shared["rows"])
    assert all(row["carriers"]["VIVA_AEROBUS"]["value"] > 0 for row in shared["rows"])

    international_shared = tools.invoke(
        "find_shared_routes",
        {
            "entity_ids": ["AEROMEXICO_GROUP", "VOLARIS", "VIVA_AEROBUS"],
            "segment": "international",
            "period": "2026Q2",
            "top_n": 20,
        },
    )
    assert international_shared["rows"]
    assert all(coverage["complete"] is components for coverage in international_shared["coverage"].values())
    assert all(
        coverage["observed_months"] == expected_months
        for coverage in international_shared["coverage"].values()
    )
    assert all(coverage["agent_eligible"] is False for coverage in international_shared["coverage"].values())
    assert all(row["comparable"] is components for row in international_shared["rows"])
    assert all(
        row["comparability_reason"] == ([] if components else ["coverage_incomplete"])
        for row in international_shared["rows"]
    )
    if not components:
        assert {
            row["market_key"]: tuple(
                row["carriers"][entity]["value"] for entity in ("AEROMEXICO_GROUP", "VOLARIS", "VIVA_AEROBUS")
            )
            for row in international_shared["rows"]
        } == LEGACY_SHARED_PASSENGERS
        assert all(row["combined_value"] is None for row in international_shared["rows"])
    else:
        assert all(
            row["combined_value"] == sum(carrier["value"] for carrier in row["carriers"].values())
            for row in international_shared["rows"]
        )
        expected_combined = {
            "GDL<>LAX": 212017,
            "LAX<>MEX": 190570,
            "MEX<>ORD": 141042,
            "GDL<>ORD": 104189,
            "IAH<>MEX": 99090,
            "LAS<>MEX": 88760,
            "MEX<>SAT": 64284,
        }
        if has_recorded_movements(tools.snapshot):
            # Coverage/provisional provenance grew; retain the same byte budget
            # and prove that truncation did not remove the underlying passengers.
            expected_combined = {
                k: v for k, v in MOVEMENT_SHARED_TOTALS_2026Q2.items() if k not in {"MEX<>SAT", "GDL<>IAH"}
            }
            assert international_shared["available_route_count"] == 8
            assert international_shared["applied_top_n"] == 6
            assert international_shared["requested_top_n"] == 20
            assert international_shared["truncated"] is True
            assert international_shared["truncation_reason"] == "tool_result_size_limit"
            networks = [
                tools._load(entity, "international", "2026Q2")[0]
                for entity in (
                    "AEROMEXICO_GROUP",
                    "VOLARIS",
                    "VIVA_AEROBUS",
                )
            ]
            values = [
                {r["market_key"]: r["passengers"] for r in n["routes"] if r["passengers"] is not None}
                for n in networks
            ]
            common = values[0].keys() & values[1].keys() & values[2].keys()
            assert {key: sum(v[key] for v in values) for key in common} == MOVEMENT_SHARED_TOTALS_2026Q2
        assert {
            row["market_key"]: row["combined_value"] for row in international_shared["rows"]
        } == expected_combined
    assert len(international_shared["display"]["columns"]) <= 12
    assert "combined_value" not in [column["key"] for column in international_shared["display"]["columns"]]
