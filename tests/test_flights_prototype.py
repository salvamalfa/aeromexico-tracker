from __future__ import annotations

import math

import pandas as pd
from src.config import PATHS

import pytest

from src.analysis_agent.flight_evidence import build_flight_evidence

pytestmark = pytest.mark.local_data


def test_flight_payload_contract_and_pilot_metrics(flight_payload) -> None:
    payload = flight_payload
    assert payload["schema_version"] == "flight_dashboard_payload_v1"
    assert payload["metadata"]["pilot_period"] == "2026Q2"
    quarter = next(item for item in payload["quarters"] if item["period_id"] == "2026Q2")
    values = {key: metric["value"] for key, metric in quarter["metrics"].items()}
    assert values == {
        "passengers": 6_014_000.0,
        "asm_miles": 9_256_000_000.0,
        "rpm_miles": 7_851_000_000.0,
        "load_factor": 0.8490000000000001,
    }
    for metric in quarter["metrics"].values():
        assert metric["period_type"] == "quarter"
        assert metric["period_start"] == "2026-04-01"
        assert metric["period_end"] == "2026-06-30"
        assert metric["cutoff_date"] == "2026-07-13"
        assert metric["source_id"] == "sec-quarterly"
        assert metric["agent_eligible"] is True


def test_monthly_sec_mix_is_complete_only_when_three_months_exist(flight_payload) -> None:
    payload = flight_payload
    mixes = {item["period_id"]: item["passenger_mix"] for item in payload["quarters"]}
    assert {period for period, mix in mixes.items() if mix} == {
        "2025Q1", "2025Q2", "2026Q1", "2026Q2"
    }
    mix = mixes["2026Q2"]
    assert mix["months"] == ["2026M04", "2026M05", "2026M06"]
    assert mix["passengers"]["domestic"] + mix["passengers"]["international"] == mix["passengers"]["total"]
    assert math.isclose(mix["passengers"]["domestic_share"] + mix["passengers"]["international_share"], 1.0)
    assert mixes["2025Q4"] is None


def test_monthly_passenger_chart_uses_complete_afac_gold_and_sums_segments(flight_payload) -> None:
    series = flight_payload["monthly_passengers"]
    assert series["period_start"] == "2015-01-01"
    assert series["period_end"] == "2026-06-30"
    assert series["source_id"] == "afac-gold-current"
    assert series["observed_months"] == series["calendar_months"] == 138
    assert len(series["records"]) == 138
    assert all(item["availability"] == "observed" for item in series["records"])
    assert all(item["total_segment_sum"] == item["domestic"] + item["international"] for item in series["records"])
    assert all(item["reported_total"] == item["total_segment_sum"] for item in series["records"])
    assert not any(item["agent_eligible"] for item in series["records"])


def test_domestic_passenger_estimates_are_monthly_retrospective_and_bounded(flight_payload) -> None:
    payload = flight_payload
    monthly = payload["domestic_monthly_networks"]
    assert list(monthly) == ["2026M03", "2026M04", "2026M05", "2026M06", "2026M07"]
    for period_id, network in monthly.items():
        assert network["period_id"] == period_id
        assert network["mode"] == "estimated_domestic"
        assert network["agent_eligible"] is False
        assert network["observed_months"] == [period_id]
        assert all(route["passengers_estimated"] for route in network["routes"])
        # Bounds may be withheld (None) when a cell of the route needed a
        # support repair; when both are present they must bracket the point.
        # The bounds and the point are separate float sums over the same
        # cells, so equality can differ in the last bits (e.g.
        # 38481.65409295874 vs 38481.654092958735, one ULP apart): allow a
        # few ULPs of summation rounding and nothing more.
        for route in network["routes"]:
            low, high = route["passengers_low"], route["passengers_high"]
            assert (low is None) == (high is None)
            if low is not None:
                slack = 16 * math.ulp(route["passengers"])
                assert low - slack <= route["passengers"] <= high + slack
        assert any(route["departures"] is not None for route in network["routes"])
        assert all(route["departures_estimated"] == (route["departures"] is not None)
                   for route in network["routes"])
        assert all(route["load_factor"] is None or 0 <= route["load_factor"] <= 1
                   for route in network["routes"])
    assert monthly["2026M03"]["routes"][0]["support_repair_applied"] is True
    assert any(not item["support_observed_in_period"]
               for route in monthly["2026M07"]["routes"] for item in route["monthly"])


def test_t100_network_is_bounded_and_never_claims_global_coverage(flight_payload) -> None:
    payload = flight_payload
    network = payload["route_network"]
    assert network["period_id"] == "2026Q2"
    assert network["period_type"] == "quarter"
    assert network["availability"] == "complete"
    months = ["2026M04", "2026M05", "2026M06"]
    assert network["expected_months"] == network["observed_months"] == months
    assert (network["period_start"], network["period_end"]) == ("2026-04-01", "2026-06-30")
    assert (network["comparison_period_start"], network["comparison_period_end"]) == ("2025-04-01", "2025-06-30")
    # Read the refreshed directional source, independently of the dashboard's
    # aggregate view. June and Connect must contribute their own records.
    traffic = pd.read_parquet(PATHS.gold / "fact_route_traffic.parquet")
    source = traffic[traffic.carrier_key.isin(["AEROMEXICO", "AEROMEXICO_CONNECT"])
                     & traffic.period_id.isin(months) & traffic.departures_performed.gt(0)]
    assert set(source.carrier_key) == {"AEROMEXICO", "AEROMEXICO_CONNECT"}
    assert set(source.period_id) == set(months)
    routes = pd.read_parquet(PATHS.gold / "dim_route.parquet")
    source = source.merge(routes[["route_key", "market_key", "origin_iata", "dest_iata"]],
                          on="route_key", validate="many_to_one")
    airports = pd.read_parquet(PATHS.gold / "dim_airport.parquet")
    located = set(airports.loc[airports.latitude.notna() & airports.longitude.notna(), "airport_iata"])
    source = source[source.origin_iata.isin(located) & source.dest_iata.isin(located)]
    source = source.rename(columns={"departures_performed": "departures"})
    # The historical map retains all BTS classes. Regular-flight coverage
    # must use F/G separately; 51 L-class non-scheduled departures stay explicit.
    assert source.groupby(["carrier_key", "service_class"]).departures.sum().to_dict() == {
        ("AEROMEXICO", "F"): 5725.0,
        ("AEROMEXICO", "L"): 51.0,
        ("AEROMEXICO_CONNECT", "F"): 1229.0,
    }
    metrics = ["passengers", "seats", "departures"]
    directions = source.groupby(["market_key", "origin_iata", "dest_iata"])[metrics].sum()
    expected_markets = set(source.market_key)
    assert network["route_count"] == len(expected_markets)
    assert network["airport_count"] == len(set(source.origin_iata) | set(source.dest_iata))
    assert network["totals"] == source[metrics].sum().to_dict()
    assert "México–Estados Unidos" in network["coverage"]
    assert network["agent_eligible"] is False
    assert network["announced_routes_available"] is False
    assert network["marketing_carrier"] is None
    assert {route["market_key"] for route in network["routes"]} == expected_markets
    for route in network["routes"]:
        assert route["departures"] > 0 and route["operation_status"] == "operated_observed"
        expected_directions = directions.loc[route["market_key"]]
        assert {(d["origin_iata"], d["destination_iata"]) for d in route["directions"]} == set(expected_directions.index)
        for direction in route["directions"]:
            expected = expected_directions.loc[(direction["origin_iata"], direction["destination_iata"])]
            for metric in metrics:
                assert direction[metric] == pytest.approx(expected[metric])
        for metric in metrics:
            assert sum(direction[metric] for direction in route["directions"]) == pytest.approx(route[metric])
    assert network["world_geometry"]["version"] == "Natural Earth 5.1.2 / 1:110m"
    assert network["world_geometry"]["license"] == "public domain"
    assert network["world_geometry"]["sha256"] == "6866c877d39cba9c357620878839b336d569f8c662d3cfab4cb1dbe2d39c977f"
    for route in network["routes"]:
        assert all(
            finite is not None
            for finite in (
                route["origin"]["lat"], route["origin"]["lon"],
                route["destination"]["lat"], route["destination"]["lon"],
            )
        )
    assert {quarter["period_id"] for quarter in payload["quarters"]} <= set(payload["route_networks"])
    assert "2015M01" in payload["route_networks"] and "2026M07" in payload["route_networks"]
    for period_id, period_network in payload["route_networks"].items():
        assert period_network["period_id"] == period_id
        assert set(period_network["observed_months"]).issubset(period_network["expected_months"])
        assert all(
            (month == period_id if "M" in period_id else
             f"{month[:4]}Q{(int(month[5:7]) - 1) // 3 + 1}" == period_id)
            for month in period_network["observed_months"]
        )


def test_forecast_is_secondary_current_perspective(flight_payload) -> None:
    forecast = flight_payload["forecast"]
    assert forecast["available"] is True
    assert forecast["agent_eligible"] is False
    assert forecast["trained_at"].startswith("2026-08-24")
    assert forecast["trained_through_period"] == "2026M06"
    assert len(forecast["points"]) == 24
    assert len([point for point in forecast["points"] if not point["is_backtest"]]) == 12
    for point in forecast["points"]:
        assert point["lower_95"] <= point["lower_80"] <= point["forecast"]
        assert point["forecast"] <= point["upper_80"] <= point["upper_95"]


def test_candidate_evidence_is_sec_only_and_does_not_modify_parent(flight_payload) -> None:
    package = build_flight_evidence(flight_payload)
    assert package["schema_version"] == "flight_evidence_v1"
    assert package["status"] == "candidate_unapproved"
    assert package["parent_evidence"]["evidence_fingerprint"] == (
        "808256bfb7420d221a3f2f2383c4b95d9889110ad1545fd85f24df8d442a9ff1"
    )
    assert {source["source_system"] for source in package["sources"]} == {"SEC EDGAR"}
    assert all(metric["agent_eligible"] for metric in package["metrics"])
    assert {metric["period_id"] for metric in package["metrics"]} == {"2026Q2"}
    assert "bts_t100" in package["excluded"]
    assert not any("route" in metric["key"] for metric in package["metrics"])

