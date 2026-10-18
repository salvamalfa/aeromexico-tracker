"""A retained zero blocks fallback without creating a never-flown BTS market."""

import pytest

from src.dashboard.flight_cells import apply_flight_cells, resolve_cells
from test_flight_cells import cell, endpoint

BTS = "Estados Unidos · BTS T-100"


def test_new_bts_market_with_only_zero_observations_is_not_materialized():
    components = resolve_cells([cell(count=0, source=BTS), cell(month="2026M05", count=0, source=BTS)])
    network = dict(routes=[])
    apply_flight_cells(network, components, endpoint)
    assert network["routes"] == []
    assert len(components) == 2 and sum(c["departures"] for c in components) == 0


def test_zero_observation_blocks_same_cell_estimate_without_reviving_a_market():
    components = resolve_cells([cell(count=0, source=BTS), cell(kind="estimated", count=99)])
    assert len(components) == 1 and components[0]["kind"] == "observed"
    network = dict(routes=[])
    apply_flight_cells(network, components, endpoint)
    assert network["routes"] == []
    assert components[0]["departures"] == 0


@pytest.mark.parametrize(
    "positive",
    [cell(month="2026M05", count=7, source=BTS), cell(carrier="AEROMEXICO_CONNECT", count=7, source=BTS)],
)
def test_zero_is_retained_when_another_month_or_operator_has_positive_flights(positive):
    components = resolve_cells([cell(count=0, source=BTS), positive])
    network = dict(routes=[])
    apply_flight_cells(network, components, endpoint)
    assert len(network["routes"]) == 1
    route = network["routes"][0]
    assert route["departures"] == 7
    assert sorted(c["departures"] for c in route["flight_components"]) == [0, 7]
    assert sum(d["departures"] for d in route["directions"]) == 7


@pytest.mark.parametrize(
    "scheduled",
    [
        cell(carrier="VOLARIS", kind="scheduled", count=20, source="slots"),
        cell(month="2026M05", kind="scheduled", count=20, source="slots"),
    ],
)
def test_zero_operated_count_does_not_remove_separate_positive_programming(scheduled):
    components = resolve_cells([cell(count=0, source=BTS), scheduled])
    network = dict(routes=[])
    apply_flight_cells(network, components, endpoint)
    assert len(network["routes"]) == 1
    route = network["routes"][0]
    assert route["departures"] == 0  # Programming does not become operated flights.
    assert sum(c["departures"] for c in route["flight_components"] if c["kind"] == "scheduled") == 20
    assert any(c["kind"] == "observed" and c["departures"] == 0 for c in route["flight_components"])
    assert network["coverage_by_source"]["slots"] == [scheduled["period_id"]]


def test_existing_market_and_its_other_metrics_are_preserved_with_explicit_zero():
    route = dict(
        market_key="JFK<>MEX",
        origin=endpoint("MEX"),
        destination=endpoint("JFK"),
        passengers=123,
        seats=456,
        departures=0,
        directions=[],
        previous=dict(departures=None),
    )
    network = dict(routes=[route])
    apply_flight_cells(network, resolve_cells([cell(count=0, source=BTS)]), endpoint)
    assert network["routes"] == [route]
    assert (route["passengers"], route["seats"], route["departures"]) == (123, 456, 0)
    assert route["flight_components"][0]["departures"] == 0
