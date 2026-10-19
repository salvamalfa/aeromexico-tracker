"""Accepted map counts keep operator/month identity and source meaning."""

from copy import deepcopy

import pytest

from src.web_export.flight_projection import cell_key, index_cells, project_network


def endpoint(code):
    return {"iata": code, "city": code, "name": code, "lat": 1, "lon": 2}


def cell(**changes):
    return {
        "carrier_key": "AEROMEXICO",
        "origin_iata": "MEX",
        "destination_iata": "BOG",
        "period_id": "2026M04",
        "kind": "observed",
        "departures": 5,
        "source_label": "Estados Unidos · BTS T-100",
        "source_hashes": ["a" * 64],
        "service_class_departures": {"F": 3, "L": 2},
        **changes,
    }


def network(cells):
    return {
        "period_label": "abril2026",
        "expected_months": ["2026M04"],
        "observed_months": ["2026M04"],
        "airports": [endpoint("MEX"), endpoint("BOG")],
        "routes": [
            {
                "market_key": "BOG<>MEX",
                "origin": endpoint("BOG"),
                "destination": endpoint("MEX"),
                "passengers": 23,
                "seats": 30,
                "load_factor": 0.7,
                "departures": 5,
                "previous": {"passengers": 20, "seats": 28, "load_factor": 0.6, "departures": 4},
                "monthly": [],
                "directions": [],
                "flight_components": cells,
            }
        ],
    }


def config(**changes):
    return {
        "colombia_replacements": [],
        "brazil_regular_cells": [],
        "sources": {"colombia": {"sha256": "b" * 64}},
        **changes,
    }


def test_regular_bts_excludes_nonregular_without_filling_retained_estimates():
    source = network([cell()])
    before = deepcopy(source)
    result = project_network(source, {"AEROMEXICO"}, ["2026M04"], config(), endpoint)
    route = result["routes"][0]
    assert route["departures"] == 3
    assert route["flight_components"][0]["service_class_departures"] == {"F": 3}
    assert route["flight_components"][0]["regularity"] == "regular"
    assert route["passengers"] == 23 and route["previous"]["passengers"] == 20
    assert route["previous"]["departures"] is None
    assert source == before


def test_zero_colombia_replaces_exact_estimate_and_negative_delta_is_applied():
    old = cell(kind="estimated", departures=5, source_label="Retained estimate", estimator_version="frozen")
    change = {
        **{k: old[k] for k in ("carrier_key", "origin_iata", "destination_iata", "period_id")},
        "departures": 0,
        "previous_kind": "estimated",
        "previous_departures": 5,
        "delta": -5,
    }
    result = project_network(
        network([old]), {"AEROMEXICO"}, ["2026M04"], config(colombia_replacements=[change]), endpoint
    )
    route = result["routes"][0]
    assert route["departures"] == 0
    assert len(route["flight_components"]) == 1
    assert route["flight_components"][0]["kind"] == "observed"
    bad = {**change, "previous_departures": 6}
    with pytest.raises(ValueError, match="old cell"):
        project_network(
            network([old]), {"AEROMEXICO"}, ["2026M04"], config(colombia_replacements=[bad]), endpoint
        )


def test_caa_and_scheduling_cannot_supply_represented_departures():
    observation = cell(source_label="Reino Unido · CAA")
    scheduled = cell(carrier_key="AEROMEXICO_GROUP", kind="scheduled", departures=50, source_label="AICM")
    result = project_network(
        network([observation, scheduled]), {"AEROMEXICO"}, ["2026M04"], config(), endpoint
    )
    route = result["routes"][0]
    assert route["departures"] is None
    assert [c["kind"] for c in route["flight_components"]] == ["scheduled"]
    assert route["flight_components"][0]["departures"] == 50


def test_brazil_needs_exact_operator_cell_count_and_source_proof():
    c = cell(source_label="Brasil · ANAC")
    proof = {
        **{k: c[k] for k in ("carrier_key", "origin_iata", "destination_iata", "period_id")},
        "departures": 5,
        "source_hash": "a" * 64,
        "source_locator": "record:1",
    }
    good = project_network(
        network([c]), {"AEROMEXICO"}, ["2026M04"], config(brazil_regular_cells=[proof]), endpoint
    )
    assert good["routes"][0]["departures"] == 5
    with pytest.raises(ValueError, match="ANAC regularity"):
        project_network(
            network([c]),
            {"AEROMEXICO"},
            ["2026M04"],
            config(brazil_regular_cells=[{**proof, "departures": 6}]),
            endpoint,
        )


@pytest.mark.parametrize(
    "other", [cell(), cell(kind="estimated"), cell(carrier_key="FOREIGN"), cell(period_id="2026M05")]
)
def test_operator_month_and_observed_estimate_overlap_are_rejected(other):
    with pytest.raises(ValueError):
        index_cells(network([cell(), other]), {"AEROMEXICO"}, ["2026M04"])


def test_cell_identity_keeps_operator_direction_and_month():
    c = cell()
    assert cell_key(c) != cell_key({**c, "carrier_key": "AEROMEXICO_CONNECT"})
    assert cell_key(c) != cell_key({**c, "origin_iata": "BOG", "destination_iata": "MEX"})
