"""Cell precedence preserves operator, month, direction, zero, and flight class."""

import duckdb
import pandas as pd
import pytest

from src.dashboard.flight_cells import apply_flight_cells, international_cells, resolve_cells
from src.dashboard.route_entities import AEROMEXICO_ROUTES, INDUSTRY_ROUTES, VIVA_ROUTES


def cell(
    carrier="AEROMEXICO", origin="MEX", dest="JFK", month="2026M04", kind="observed", count=10, source=None
):
    return dict(
        carrier_key=carrier,
        origin_iata=origin,
        destination_iata=dest,
        period_id=month,
        kind=kind,
        departures=count,
        source_label=source or kind,
        source_hashes=[],
    )


def endpoint(iata):
    return dict(iata=iata, city=iata, name=iata, lat=1.0, lon=1.0, country="US" if iata == "JFK" else "MX")


def test_exact_operator_direction_month_and_explicit_zero_precedence():
    source = [
        cell(count=0),
        cell(kind="estimated", count=99),
        cell(dest="LAX", kind="estimated", count=8),
        cell(origin="JFK", dest="MEX", kind="estimated", count=9),
        cell(month="2026M06", kind="estimated", count=11),
        cell(carrier="AEROMEXICO_CONNECT", kind="estimated", count=12),
        cell(carrier="VOLARIS", kind="estimated", count=13),
    ]
    selected = resolve_cells(source)
    assert len(selected) == 6
    assert sum(c["departures"] for c in selected) == 53
    assert (
        next(
            c
            for c in selected
            if c["carrier_key"] == "AEROMEXICO"
            and c["period_id"] == "2026M04"
            and c["origin_iata"] == "MEX"
            and c["destination_iata"] == "JFK"
        )["departures"]
        == 0
    )
    with pytest.raises(ValueError, match="Duplicate"):
        resolve_cells([cell(), cell()])


def test_schedule_does_not_add_to_observed_or_estimated_cell():
    selected = resolve_cells(
        [
            cell(),
            cell(carrier="AEROMEXICO_GROUP", kind="scheduled", count=100),
            cell(carrier="AEROMEXICO_GROUP", month="2026M06", kind="scheduled", count=20),
        ]
    )
    assert [(c["kind"], c["departures"]) for c in selected] == [("observed", 10), ("scheduled", 20)]
    network = dict(routes=[])
    apply_flight_cells(network, selected, endpoint)
    route = network["routes"][0]
    assert route["departures"] == 10
    assert sum(c["departures"] for c in route["flight_components"] if c["kind"] == "scheduled") == 20
    assert len(route["directions"]) == 1  # Never invent a return.


def test_partial_quarter_and_connect_are_mixed_not_observed():
    selected = resolve_cells(
        [
            cell(),
            cell(month="2026M05", count=20),
            cell(month="2026M06", kind="estimated", count=30),
            cell(carrier="AEROMEXICO_CONNECT", month="2026M06", count=5),
        ]
    )
    network = dict(routes=[])
    apply_flight_cells(network, selected, endpoint)
    route = network["routes"][0]
    assert route["operation_status"] == "mixed_observed_estimated_cells"
    assert route["departures"] == 65
    assert sum(d["departures"] for d in route["directions"]) == 65
    assert route["previous"]["departures"] is None
    assert route["observed_months"] == ["2026M04", "2026M05", "2026M06"]
    assert route["estimated_months"] == ["2026M06"]


def test_reader_preserves_bts_classes_and_default_us_policy():
    with duckdb.connect() as connection:
        connection.execute(
            "CREATE TABLE dim_route(route_key VARCHAR, origin_iata VARCHAR, dest_iata VARCHAR)"
        )
        connection.execute("INSERT INTO dim_route VALUES ('MEX-JFK','MEX','JFK')")
        connection.execute(
            "CREATE TABLE fact_route_traffic(route_key VARCHAR, period_id VARCHAR, carrier_key VARCHAR, service_class VARCHAR, departures_performed DOUBLE, source_hash VARCHAR)"
        )
        connection.execute(
            "INSERT INTO fact_route_traffic VALUES ('MEX-JFK','2026M04','AEROMEXICO','F',10,'abc'), ('MEX-JFK','2026M04','AEROMEXICO','L',2,'abc'), ('MEX-JFK','2026M04','AEROMEXICO_CONNECT','F',3,'abc')"
        )
        estimates = pd.DataFrame(
            [
                dict(
                    period_id="2026M04",
                    carrier_key="VIVA_AEROBUS",
                    origin_iata="MEX",
                    destination_iata="JFK",
                    departures_estimated=4,
                ),
                dict(
                    period_id="2026M06",
                    carrier_key="VIVA_AEROBUS",
                    origin_iata="MEX",
                    destination_iata="JFK",
                    departures_estimated=7,
                ),
            ]
        )
        off = international_cells(connection, ["2026M04", "2026M06"], INDUSTRY_ROUTES, estimates, endpoint)
        assert sum(c["departures"] for c in off) == 15
        assert off[0]["service_class_departures"] == {"F": 10, "L": 2}
        on = international_cells(
            connection, ["2026M04", "2026M06"], INDUSTRY_ROUTES, estimates, endpoint, include_us=True
        )
        assert sum(c["departures"] for c in on) == 26
        assert set(AEROMEXICO_ROUTES.t100_carriers) == {"AEROMEXICO", "AEROMEXICO_CONNECT"}
        assert VIVA_ROUTES.t100_carriers == ("VIVA_AEROBUS",)
        with pytest.raises(ValueError, match="Duplicate retained frequency"):
            international_cells(
                connection,
                ["2026M04", "2026M06"],
                INDUSTRY_ROUTES,
                pd.concat([estimates, estimates]),
                endpoint,
                include_us=True,
            )


def test_unknown_is_not_zero_and_negative_or_nonfinite_counts_rejected():
    assert resolve_cells([cell(count=None), cell(kind="estimated", count=2)])[0]["departures"] == 2
    for value in (-1, float("inf")):
        with pytest.raises(ValueError, match="Invalid"):
            resolve_cells([cell(count=value)])


def test_entity_export_fills_missing_us_cells_only_under_opt_in(monkeypatch):
    from src.dashboard import entity_routes
    from src.dashboard.flights_html import integration_flight_payload

    monkeypatch.setattr(entity_routes, "load_route_capacity", lambda *args: pd.DataFrame())
    with duckdb.connect() as c:
        c.execute(
            "CREATE TABLE dim_airport(airport_iata VARCHAR,name VARCHAR,city VARCHAR,country VARCHAR,latitude DOUBLE,longitude DOUBLE)"
        )
        c.execute("INSERT INTO dim_airport VALUES ('MEX','MEX','MEX','MX',1,1),('JFK','JFK','JFK','US',2,2)")
        c.execute("CREATE TABLE dim_route(route_key VARCHAR, origin_iata VARCHAR, dest_iata VARCHAR)")
        c.execute("INSERT INTO dim_route VALUES ('MEX-JFK','MEX','JFK')")
        c.execute(
            "CREATE TABLE fact_route_traffic(route_key VARCHAR,period_id VARCHAR,carrier_key VARCHAR,service_class VARCHAR,departures_performed DOUBLE)"
        )
        c.execute(
            "INSERT INTO fact_route_traffic VALUES ('MEX-JFK','2026M04','VIVA_AEROBUS','F',0),('MEX-JFK','2026M05','VIVA_AEROBUS','F',5),('MEX-JFK','2026M04','VOLARIS','F',1000)"
        )
        c.execute(
            "CREATE TABLE fact_route_carrier_international_estimate(period_id VARCHAR,market_key VARCHAR,origin_iata VARCHAR,destination_iata VARCHAR,carrier_key VARCHAR,passengers_estimated DOUBLE,passengers_estimated_low DOUBLE,passengers_estimated_high DOUBLE,departures_estimated DOUBLE,estimator_version VARCHAR)"
        )
        c.execute(
            "INSERT INTO fact_route_carrier_international_estimate VALUES ('2026M04','JFK<>MEX','MEX','JFK','VIVA_AEROBUS',10,8,12,100,'retained'),('2026M06','JFK<>MEX','MEX','JFK','VIVA_AEROBUS',10,8,12,7,'retained'),('2026M06','JFK<>MEX','JFK','MEX','VIVA_AEROBUS',10,8,12,3,'retained')"
        )
        network = dict(
            period_label="Q2",
            expected_months=["2026M04", "2026M05", "2026M06"],
            observed_months=["2026M04", "2026M05"],
            routes=[
                dict(
                    market_key="JFK<>MEX",
                    origin=endpoint("MEX"),
                    destination=endpoint("JFK"),
                    passengers=100,
                    seats=150,
                    load_factor=2 / 3,
                    departures=5,
                    directions=[
                        dict(
                            origin_iata="MEX", destination_iata="JFK", passengers=100, seats=150, departures=5
                        )
                    ],
                    previous=dict(passengers=None, seats=None, departures=None),
                )
            ],
        )
        off = entity_routes.entity_international_networks(c, {"2026Q2": network}, VIVA_ROUTES)
        assert off["2026Q2"]["routes"][0]["departures"] == 5
        on = entity_routes.entity_international_networks(
            c, {"2026Q2": network}, VIVA_ROUTES, include_existing_us_estimates=True
        )
        route = on["2026Q2"]["routes"][0]
        assert route["departures"] == 15 and route["passengers"] == 100
        assert route["operation_status"] == "mixed_observed_estimated_cells"
        assert [x["departures"] for x in route["flight_components"] if x["kind"] == "observed"] == [0, 5]
        normalized = integration_flight_payload(
            dict(
                schema_version="flight_dashboard_payload_v1",
                metadata={},
                quarters=[],
                monthly_passengers={},
                route_network={"world_geometry": {}},
                route_networks={},
                international_networks=on,
            )
        )["route_networks"]["2026Q2"]["routes"][0]
        assert normalized["flight_components"] == route["flight_components"]
        assert normalized["departures"] == 15

        admitted = {("VIVA_AEROBUS", "2026M06", "MEX", "JFK")}
        filtered = entity_routes.entity_international_networks(
            c,
            {"2026Q2": network},
            VIVA_ROUTES,
            include_existing_us_estimates=True,
            allowed_us_estimate_cells=admitted,
        )["2026Q2"]["routes"][0]
        assert filtered["departures"] == 12
        assert len(filtered["directions"]) == 1
        assert [
            (x["period_id"], x["origin_iata"], x["departures"])
            for x in filtered["flight_components"]
            if x["kind"] == "estimated"
        ] == [("2026M06", "MEX", 7)]
        blocked = entity_routes.entity_international_networks(
            c,
            {"2026Q2": network},
            VIVA_ROUTES,
            include_existing_us_estimates=True,
            allowed_us_estimate_cells=set(),
        )["2026Q2"]["routes"][0]
        assert blocked["departures"] == 5 and all(
            x["kind"] == "observed" for x in blocked["flight_components"]
        )
        disabled = entity_routes.entity_international_networks(
            c, {"2026Q2": network}, VIVA_ROUTES, allowed_us_estimate_cells=admitted
        )["2026Q2"]["routes"][0]
        assert disabled["departures"] == 5


def test_explicit_zero_return_blocks_estimate_without_drawing_a_return():
    selected = resolve_cells(
        [
            cell(count=10),
            cell(origin="JFK", dest="MEX", count=0),
            cell(origin="JFK", dest="MEX", kind="estimated", count=99),
        ]
    )
    network = dict(routes=[])
    apply_flight_cells(network, selected, endpoint)
    route = network["routes"][0]
    assert route["departures"] == 10
    assert len(route["flight_components"]) == 2
    assert [(d["origin_iata"], d["destination_iata"], d["departures"]) for d in route["directions"]] == [
        ("MEX", "JFK", 10)
    ]
