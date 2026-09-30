"""Vuelos map by airline (Dashboard v2, fase 3)."""

from __future__ import annotations

import math

import pytest

from src.dashboard.route_entities import (
    AEROMEXICO_ROUTES,
    INDUSTRY_ROUTES,
    VIVA_ROUTES,
    breakdown_totals,
)
from src.dashboard import domestic_routes, international_routes


def test_aeromexico_labels_are_the_historical_ones() -> None:
    assert AEROMEXICO_ROUTES.domestic_estimated_label == domestic_routes.ESTIMATED_LABEL
    assert AEROMEXICO_ROUTES.international_estimated_label == international_routes.ESTIMATED_LABEL
    assert dict(AEROMEXICO_ROUTES.estimate_carriers) == domestic_routes.ESTIMATED_CARRIERS


def test_industry_breakdown_folds_connect_into_aeromexico() -> None:
    totals = breakdown_totals(
        INDUSTRY_ROUTES,
        [("AEROMEXICO", 100.0), ("AEROMEXICO_CONNECT", 20.0), ("VOLARIS", 50.0), ("VIVA_AEROBUS", 30.0)],
    )
    assert totals == {"AEROMEXICO": 120.0, "VIVA_AEROBUS": 30.0, "VOLARIS": 50.0}


def test_single_airline_has_no_breakdown_and_rejects_foreign_keys() -> None:
    assert breakdown_totals(VIVA_ROUTES, [("VIVA_AEROBUS", 1.0)]) is None
    with pytest.raises(ValueError):
        breakdown_totals(INDUSTRY_ROUTES, [("DELTA", 1.0)])


AEROMEXICO_ONLY_LABELS = (
    "AICM", "OMA", "ANAC", "Aerocivil", "CAA", "AIFA", "único operador",
)


@pytest.mark.local_data
def test_entity_maps_have_no_aeromexico_layers_and_industry_sums(flight_payload) -> None:
    entities = flight_payload["entity_networks"]
    assert set(entities) == {"INDUSTRY", "VOLARIS", "VIVA_AEROBUS"}
    for key, block in entities.items():
        networks = [*block["route_networks"].values(), *block["domestic_monthly_networks"].values()]
        for network in networks:
            for route in network["routes"]:
                label = route["source_label"]
                assert not any(marker in label for marker in AEROMEXICO_ONLY_LABELS), (key, label)
                # Mexico–United States stays observed by T-100, never estimated.
                countries = {route["origin"]["country"], route["destination"]["country"]}
                if route.get("passengers_estimated") and network.get("mode") != "estimated_domestic":
                    assert "US" not in countries and "United States" not in countries, route["market_key"]
                if key == "INDUSTRY" and route.get("passengers") is not None:
                    breakdown = route["carrier_breakdown"]
                    assert math.isclose(sum(breakdown.values()), route["passengers"], abs_tol=1.0)
                else:
                    assert "carrier_breakdown" not in route or route["carrier_breakdown"] is None
    # Aeroméxico's own map keeps its historical layers.
    am_labels = {r["source_label"] for n in flight_payload["international_networks"].values() for r in n["routes"]}
    assert "Estados Unidos · BTS T-100" in am_labels


@pytest.mark.local_data
def test_fleet_capacity_fills_occupancy_for_volaris_and_viva(flight_payload) -> None:
    for key in ("VOLARIS", "VIVA_AEROBUS"):
        networks = flight_payload["entity_networks"][key]["domestic_monthly_networks"].values()
        routes = [route for network in networks for route in network["routes"]]
        shown = [route for route in routes if route.get("load_factor") is not None]
        assert len(shown) > 0.6 * len(routes), key
        assert all(0 < route["load_factor"] <= 1 for route in shown)
        assert all(route["seats_low"] <= route["seats"] <= route["seats_high"] for route in shown)
