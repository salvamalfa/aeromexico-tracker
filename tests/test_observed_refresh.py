"""Real retained source networks guard selective refresh and year-ago evidence."""

import copy
import json
import subprocess

import pytest

from src.config import PATHS
from src.dashboard.map_periods import period_months
from src.web_export.observed_refresh import refresh_observed_network

BASELINE = "089f48a656e301d2380c8d1a23aab5bb6ada728b"
LABELS = ("Brasil · ANAC", "Estados Unidos · BTS T-100")


def retained(period="2026M07", entity="INDUSTRY"):
    prefix = "flights" if entity == "AEROMEXICO" else f"flights/entities/{entity}"
    name = f"site/data/v1/{prefix}/international/{period}.json"
    return json.loads(subprocess.check_output(["git", "show", f"{BASELINE}:{name}"], cwd=PATHS.root))


def refresh(network, label, *, cells=None, previous=None):
    cells = (
        cells
        if cells is not None
        else [
            cell
            for route in network["routes"]
            for cell in route.get("flight_components", [])
            if cell["source_label"] == label
        ]
    )
    endpoints = {
        point["iata"]: point
        for route in network["routes"]
        for point in (route["origin"], route["destination"])
    }
    return refresh_observed_network(
        network, cells, period_months("2026M07"), label, endpoints, "2026M07", previous
    )


@pytest.mark.parametrize("label", LABELS)
@pytest.mark.parametrize("entity", ["AEROMEXICO", "INDUSTRY"])
def test_real_noop_preserves_all_comparators_eligibility_and_input(label, entity):
    before = retained(entity=entity)
    original = copy.deepcopy(before)
    assert refresh(before, label) == original
    assert before == original
    if entity == "INDUSTRY":
        by_key = {route["market_key"]: route for route in before["routes"]}
        assert by_key["BJX<>SMF"]["previous"]["departures"] == 28
        assert by_key["GDL<>ONT"]["previous"]["departures"] == 124


@pytest.mark.parametrize("support", ["physical", "missing", "incompatible"])
def test_changed_real_bts_cell_only_revalidates_its_own_departure_comparator(support):
    before, previous = retained(), retained("2025M07")
    cells = copy.deepcopy(
        [
            cell
            for route in before["routes"]
            for cell in route.get("flight_components", [])
            if cell["source_label"] == LABELS[1]
        ]
    )
    key = "GDL<>ONT"
    for cell in cells:
        if "<>".join(sorted((cell["origin_iata"], cell["destination_iata"]))) == key:
            cell["departures"] += 1
    if support == "missing":
        previous = None
    elif support == "incompatible":
        next(route for route in previous["routes"] if route["market_key"] == key)["flight_components"] = []
    after = refresh(before, LABELS[1], cells=cells, previous=previous)
    old = {route["market_key"]: route for route in before["routes"]}
    new = {route["market_key"]: route for route in after["routes"]}
    assert new[key]["departures"] > old[key]["departures"]
    assert new[key]["previous"]["departures"] == (124 if support == "physical" else None)
    for field in ("passengers", "seats"):
        assert new[key]["previous"][field] == old[key]["previous"][field]
    assert {k: v for k, v in new.items() if k != key} == {k: v for k, v in old.items() if k != key}
    for field in ("agent_eligible", "eligibility_reason", "previous", "next"):
        assert after.get(field) == before.get(field)


def test_native_removal_requires_explicit_missing_value_review():
    with pytest.raises(ValueError, match="removes an observed cell"):
        refresh(retained(), LABELS[1], cells=[])


def test_real_anac_arrival_preserves_every_bts_route_and_comparator():
    before = retained()
    label = LABELS[0]
    cells = copy.deepcopy(
        [
            cell
            for route in before["routes"]
            for cell in route.get("flight_components", [])
            if cell["source_label"] == label
        ]
    )
    assert cells
    for cell in cells:
        cell["departures"] += 1
    after = refresh(before, label, cells=cells)
    untouched = {
        route["market_key"]: route
        for route in before["routes"]
        if not any(cell["source_label"] == label for cell in route.get("flight_components", []))
    }
    assert {
        route["market_key"]: route for route in after["routes"] if route["market_key"] in untouched
    } == untouched
