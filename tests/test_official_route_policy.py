"""Retired route estimates cannot reach exports or an older runtime snapshot."""
from copy import deepcopy

from src.dashboard.official_route_policy import official_network


def route(**changes):
    return dict(market_key="MEX<>BOG", source_label="Colombia · Aerocivil",
                operation_status="operated_observed", passengers=None, seats=None,
                departures=60, load_factor=None,
                origin={"iata":"MEX"}, destination={"iata":"BOG"},
                directions=[dict(origin_iata="MEX", destination_iata="BOG", passengers=None, seats=None, departures=30)],
                previous={"passengers":None,"seats":None,"departures":50}) | changes


def test_official_observations_and_schedules_keep_their_original_values():
    network = {"routes":[route(), route(operation_status="assigned_slot_not_flown", source_label="AICM")]}
    before = deepcopy(network)
    result = official_network(network)
    assert network == before
    assert [r["departures"] for r in result["routes"]] == [60,60]
    assert [r["operation_status"] for r in result["routes"]] == ["operated_observed","assigned_slot_not_flown"]
    assert all(r["passengers"] is r["seats"] is None for r in result["routes"])


def test_enriched_authority_keeps_real_flights_and_loses_all_seed_metrics():
    enriched = route(passengers=10000, seats=12000, load_factor=.83,
                     passengers_estimated=True, capacity_estimated=True,
                     passengers_low=9000, seats_high=15000,
                     monthly=[{"passengers":5000}], carrier_breakdown={"AEROMEXICO":10000},
                     coverage_note="Meses: 06 · Aerocivil · Pasajeros estimados de Grupo Aeroméxico (AFAC + AeroDataBox)")
    enriched["directions"][0].update(passengers=5000,seats=6000,passengers_low=4500)
    result = official_network({"routes":[enriched]})["routes"][0]
    assert result["departures"] == 60 and result["previous"]["departures"] == 50
    assert result["passengers"] is result["seats"] is result["load_factor"] is None
    assert result["directions"][0]["departures"] == 30
    assert result["directions"][0]["passengers"] is result["directions"][0]["seats"] is None
    assert "monthly" not in result and "carrier_breakdown" not in result
    assert "AeroDataBox" not in result["coverage_note"]


def test_estimated_networks_and_routes_are_excluded_even_with_official_sounding_labels():
    assert official_network({"mode":"estimated_domestic", "routes":[route()]})["routes"] == []
    assert official_network({"routes":[route(operation_status="estimated_from_afac_margins_and_aerodatabox_seed")]})["routes"] == []


def test_metric_provenance_cannot_reintroduce_estimated_departures():
    result = official_network({"routes":[route(metric_value_kinds={"departures":"estimated"})]})
    assert result["routes"][0]["departures"] is None
