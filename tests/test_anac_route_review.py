"""Verified Brazilian operations reach Industry without leaking into peers."""

from copy import deepcopy

import duckdb
import pytest

from scripts.build_anac_route_review import checked_months, resolve_revision
from src.dashboard.entity_routes import entity_international_networks
from src.dashboard.route_entities import INDUSTRY_ROUTES, VIVA_ROUTES, VOLARIS_ROUTES


@pytest.mark.parametrize("quarter", ["2025Q3", "2026Q4", "2026M09", "2026Q5"])
def test_review_rejects_quarters_outside_certified_availability(quarter):
    with pytest.raises(ValueError):
        checked_months(quarter, "2026M09")


def test_review_cannot_preserve_a_removed_anac_market_as_observed():
    stale = dict(source_label="Brasil · ANAC", origin_iata="MEX", destination_iata="GRU")
    network = {"routes": [{"flight_components": [stale]}]}
    with pytest.raises(ValueError, match="removes a market"):
        resolve_revision(network, [])


def test_industry_retains_anac_operator_cells_and_temporal_coverage():
    with duckdb.connect() as connection:
        connection.execute(
            "CREATE TABLE dim_airport(airport_iata VARCHAR, name VARCHAR, city VARCHAR, "
            "country VARCHAR, latitude DOUBLE, longitude DOUBLE)"
        )
        connection.execute(
            "INSERT INTO dim_airport VALUES ('MEX','Mexico','Mexico','MX',19,-99),"
            "('GRU','Guarulhos','Sao Paulo','BR',-23,-46)"
        )
        connection.execute(
            "CREATE TABLE fact_international_route_observations(source_system VARCHAR,operator_icao VARCHAR,"
            "observation_scope VARCHAR,period_id VARCHAR,origin_iata VARCHAR,dest_iata VARCHAR,"
            "departures DOUBLE,source_hash VARCHAR)"
        )
        connection.execute(
            "INSERT INTO fact_international_route_observations VALUES "
            "('anac','AMX','carrier_route','2026M07','MEX','GRU',31,'original'),"
            "('anac','AMX','carrier_route','2026M08','MEX','GRU',32,'original'),"
            "('anac','AMX','carrier_route','2026M09','GRU','MEX',30,'original'),"
            "('aerocivil','AMX','carrier_route','2026M09','MEX','GRU',999,'not-anac'),"
            "('anac','VOI','carrier_route','2026M09','MEX','GRU',999,'not-amx')"
        )
        template = {
            "2026Q3": dict(
                period_label="3T26",
                expected_months=["2026M07", "2026M08", "2026M09"],
                observed_months=[],
                routes=[],
                airports=[],
                eligibility_reason="Retrospective source",
            )
        }
        result = entity_international_networks(connection, deepcopy(template), INDUSTRY_ROUTES)["2026Q3"]
        assert len(result["routes"]) == 1
        route = result["routes"][0]
        assert route["departures"] == 93
        assert route["operation_status"] == "operated_observed"
        assert route["passengers"] is None
        assert {cell["carrier_key"] for cell in route["flight_components"]} == {"AEROMEXICO"}
        assert {cell["source_label"] for cell in route["flight_components"]} == {"Brasil · ANAC"}
        assert result["coverage_by_source"]["Brasil · ANAC"] == ["2026M07", "2026M08", "2026M09"]
        for entity in (VIVA_ROUTES, VOLARIS_ROUTES):
            peer = entity_international_networks(connection, deepcopy(template), entity)["2026Q3"]
            assert peer["routes"] == []


def test_real_anac_review_preserves_bts_and_all_other_components():
    """Optional local evidence: compare actual generated files, no fixtures posing as capture."""
    import json
    from pathlib import Path

    import pytest

    root = Path("tmp/source-updates/public-refresh-20261101/anac-map-review-final")
    if not (root / "receipt.json").is_file():
        pytest.skip("Real public-source capture is local private evidence")
    for prefix in ("flights", "flights/entities/INDUSTRY"):
        before = json.loads((Path("site/data/v1") / prefix / "international/2026Q3.json").read_bytes())
        after = json.loads((root / "data/v1" / prefix / "international/2026Q3.json").read_bytes())

        def components(payload):
            return sorted(
                (
                    json.dumps(cell, sort_keys=True)
                    for route in payload["routes"]
                    for cell in route.get("flight_components", [])
                    if cell["source_label"] != "Brasil · ANAC"
                )
            )

        # Source updates supersede an estimated cell only where the new source
        # observes the same operator, direction and month.
        new_cells = {
            (c["carrier_key"], c["origin_iata"], c["destination_iata"], c["period_id"])
            for r in after["routes"]
            for c in r.get("flight_components", [])
            if c["source_label"] == "Brasil · ANAC"
        }
        unaffected = deepcopy(before)
        for route in unaffected["routes"]:
            route["flight_components"] = [
                c
                for c in route.get("flight_components", [])
                if (c["carrier_key"], c["origin_iata"], c["destination_iata"], c["period_id"])
                not in new_cells
            ]
        assert components(unaffected) == components(after)
        assert after["coverage_by_source"]["Estados Unidos · BTS T-100"] == ["2026M07"]
        assert after["coverage_by_source"]["Brasil · ANAC"] == ["2026M07", "2026M08", "2026M09"]
        anac = [
            c
            for r in after["routes"]
            for c in r.get("flight_components", [])
            if c["source_label"] == "Brasil · ANAC"
        ]
        assert all(c["kind"] == "observed" for c in anac)
        assert sum(c["departures"] for c in anac) > 0
