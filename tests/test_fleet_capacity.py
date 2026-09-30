"""Fleet-average seat capacity for Volaris and Viva (Dashboard v2, fase 4)."""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from src.analytics.fleet_capacity import FLEET_CAPACITY_METHOD, fleet_capacity, t100_gauge
from src.dashboard.route_capacity import load_route_capacity
from src.dashboard.route_entities import AEROMEXICO_ROUTES, INDUSTRY_ROUTES, VOLARIS_ROUTES


def _months(first_year: int, first_month: int, count: int) -> list[str]:
    out, year, month = [], first_year, first_month
    for _ in range(count):
        out.append(f"{year}M{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


@pytest.fixture()
def connection():
    con = duckdb.connect()
    rows = []
    # 2025M04–2026M03 at 200 seats/departure on a busy route and 180 on another;
    # 2026M04 (the period itself) at 999 must never enter the gauge.
    for period in _months(2025, 4, 12):
        rows.append(("VOLARIS", "GDL<>LAX", period, 20000.0, 100.0))
        rows.append(("VOLARIS", "GDL<>OAK", period, 9000.0, 50.0))
    rows.append(("VOLARIS", "GDL<>LAX", "2026M04", 99900.0, 100.0))
    con.register("t100", pd.DataFrame(rows, columns=["carrier_key", "market_key", "period_id", "seats", "departures"]))
    con.execute("CREATE TABLE fact_route_traffic_summary AS SELECT * FROM t100")
    domestic = pd.DataFrame(
        [
            ("2026M04", "GDL<>MEX", "GDL", "MEX", "VOLARIS", 10.0, True),
            ("2026M04", "GDL<>TIJ", "GDL", "TIJ", "VOLARIS", 1.5, False),
            ("2026M04", "GDL<>MEX", "GDL", "MEX", "AEROMEXICO", 8.0, True),
        ],
        columns=["period_id", "market_key", "origin_iata", "destination_iata", "carrier_key",
                 "seed_weight", "support_observed_in_period"],
    )
    con.register("dom", domestic)
    con.execute("CREATE TABLE fact_route_carrier_domestic_estimate AS SELECT * FROM dom")
    yield con
    con.close()


def test_gauge_uses_the_twelve_months_before_the_period(connection) -> None:
    gauge = t100_gauge(connection, "VOLARIS", "2026M04")
    assert gauge["months"] == _months(2025, 4, 12)
    # (12 * 20000 + 12 * 9000) / (12 * 150) — the 999-seat period is excluded.
    assert gauge["point"] == pytest.approx(29000 / 150)
    assert gauge["low"] <= gauge["point"] <= gauge["high"]
    assert t100_gauge(connection, "VOLARIS", "2026M03") is None  # only 11 months before


def test_borrowed_support_is_not_a_departure_count(connection) -> None:
    frame = fleet_capacity(connection, "domestic", ("VOLARIS",)).set_index("market_key")
    observed, borrowed = frame.loc["GDL<>MEX"], frame.loc["GDL<>TIJ"]
    assert observed.capacity_usable and observed.seats_estimated == pytest.approx(10 * 29000 / 150)
    assert observed.seats_estimated_low <= observed.seats_estimated <= observed.seats_estimated_high
    assert not borrowed.capacity_usable and pd.isna(borrowed.seats_estimated)
    assert set(frame.capacity_method) == {FLEET_CAPACITY_METHOD}
    assert set(frame.aircraft_model_coverage) == {0.0}


def test_only_volaris_and_viva_take_the_fleet_gauge(connection) -> None:
    with pytest.raises(ValueError):
        fleet_capacity(connection, "domestic", ("AEROMEXICO",))


def test_industry_blocks_an_aeromexico_cell_without_capacity(connection) -> None:
    # No Aeroméxico model-capacity table here: its passenger cell must block
    # Industria's seats instead of silently contributing nothing.
    assert load_route_capacity(connection, AEROMEXICO_ROUTES, "domestic").empty
    connection.execute(
        "CREATE TABLE fact_aeromexico_domestic_capacity_estimate AS SELECT * FROM "
        "(SELECT '2026M04' period_id, 'X<>Y' market_key, 'X' origin_iata, 'Y' destination_iata, "
        "'AEROMEXICO' carrier_key, 1.0 departures_estimated, 170.0 seats_estimated, "
        "170.0 seats_estimated_low, 170.0 seats_estimated_high, 1.0 aircraft_model_coverage, "
        "TRUE capacity_usable)"
    )
    industry = load_route_capacity(connection, INDUSTRY_ROUTES, "domestic")
    am_cell = industry[(industry.carrier_key == "AEROMEXICO") & (industry.market_key == "GDL<>MEX")]
    assert len(am_cell) == 1 and not am_cell.capacity_usable.iloc[0]
    volaris = load_route_capacity(connection, VOLARIS_ROUTES, "domestic")
    assert set(volaris.carrier_key) == {"VOLARIS"}
