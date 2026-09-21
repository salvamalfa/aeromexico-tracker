"""Checks that domestic monthly estimates aggregate correctly under the
global quarter selector: quarter -> months mapping, totals-based occupancy,
and honest partial-quarter coverage. See docs/etapas for the full audit."""

from __future__ import annotations

import pytest

from src.dashboard.flights import build_flight_payload


def _payload() -> dict:
    return build_flight_payload()


def test_2026q2_offers_exactly_its_three_calendar_months() -> None:
    payload = _payload()
    months = sorted(
        month for month in payload["domestic_monthly_networks"]
        if month in ("2026M04", "2026M05", "2026M06")
    )
    assert months == ["2026M04", "2026M05", "2026M06"]


def test_quarterly_aggregate_equals_sum_of_the_three_monthly_payloads() -> None:
    """The server's own 2026Q2 quarter aggregate (load_domestic_networks) must
    equal, route by route, an independent sum of the three monthly payloads
    computed here -- the exact rule the national month selector's client-side
    aggregation also follows."""

    payload = _payload()
    quarter = payload["domestic_networks"]["2026Q2"]
    monthly = payload["domestic_monthly_networks"]
    by_market: dict[str, dict[str, float]] = {}
    for month_id in ("2026M04", "2026M05", "2026M06"):
        for route in monthly[month_id]["routes"]:
            agg = by_market.setdefault(route["market_key"], {
                "passengers": 0.0, "passengers_low": 0.0, "passengers_high": 0.0,
                "seats": 0.0, "departures": 0.0, "capacity_months": 0, "months": 0,
            })
            agg["passengers"] += route["passengers"]
            agg["passengers_low"] += route["passengers_low"]
            agg["passengers_high"] += route["passengers_high"]
            agg["months"] += 1
            if route["capacity_complete"]:
                agg["seats"] += route["seats"]
                agg["departures"] += route["departures"]
                agg["capacity_months"] += 1

    assert len(quarter["routes"]) == len(by_market)
    for route in quarter["routes"]:
        summed = by_market[route["market_key"]]
        assert route["passengers"] == pytest.approx(summed["passengers"])
        assert route["passengers_low"] == pytest.approx(summed["passengers_low"])
        assert route["passengers_high"] == pytest.approx(summed["passengers_high"])
        # A market present in fewer of the quarter's months than expected
        # (e.g. a route only estimated from June onward) must say so, never
        # silently pass as a full three-month figure.
        assert route["months_selected"] == 3
        assert route["months_covered"] == summed["months"]
        if summed["months"] < 3:
            assert f"cobertura parcial: {summed['months']} de 3 meses" in route["coverage_note"]
        # Never sum three months of passengers against one or two months of
        # seats: capacity is only "complete" when every month that counted
        # toward passengers also counted toward capacity -- independent of
        # whether that set of months covers the whole quarter.
        if summed["capacity_months"] == summed["months"] and summed["months"] > 0:
            assert route["capacity_complete"] is True
            assert route["seats"] == pytest.approx(summed["seats"])
            assert route["departures"] == pytest.approx(summed["departures"])
        else:
            assert route["capacity_complete"] is False


def test_group_occupancy_uses_summed_totals_not_averaged_percentages() -> None:
    payload = _payload()
    monthly = payload["domestic_monthly_networks"]
    quarter = payload["domestic_networks"]["2026Q2"]
    gdl = next(r for r in quarter["routes"] if r["market_key"] == "GDL<>MEX")
    monthly_load_factors = []
    for month_id in ("2026M04", "2026M05", "2026M06"):
        route = next(r for r in monthly[month_id]["routes"] if r["market_key"] == "GDL<>MEX")
        assert route["load_factor"] is not None
        monthly_load_factors.append(route["load_factor"])
    averaged = sum(monthly_load_factors) / 3
    assert gdl["load_factor"] == pytest.approx(gdl["passengers"] / gdl["seats"])
    # Averaging the three monthly percentages is a different (and wrong)
    # number; the quarter figure must not match it.
    assert gdl["load_factor"] != pytest.approx(averaged, rel=1e-6)


def test_partial_quarter_2026q1_is_marked_partial_and_keeps_its_one_month() -> None:
    payload = _payload()
    q1 = payload["domestic_networks"].get("2026Q1")
    assert q1 is not None
    assert q1["availability"] == "partial"
    assert q1["observed_months"] == ["2026M03"]
    assert q1["expected_months"] == ["2026M01", "2026M02", "2026M03"]
    assert len(q1["routes"]) > 0
    assert all(route["passengers"] > 0 for route in q1["routes"])


def test_gdl_mex_june_matches_known_result() -> None:
    payload = _payload()
    june = payload["domestic_monthly_networks"]["2026M06"]
    gdl = next(r for r in june["routes"] if r["market_key"] == "GDL<>MEX")
    assert gdl["passengers"] == pytest.approx(108_975, rel=0.001)
    assert gdl["departures"] == pytest.approx(745, rel=0.001)
    assert gdl["seats"] == pytest.approx(131_926, rel=0.001)
    assert gdl["load_factor"] == pytest.approx(0.826, rel=0.002)
