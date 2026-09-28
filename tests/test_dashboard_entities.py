"""Industry aggregation and the Mercado payload, on a synthetic warehouse.

These run in CI (no local data): they build a tiny ``v_carrier_default`` in a
temporary DuckDB file and check the aggregation rules documented in
src/dashboard/entities.py and src/dashboard/market.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from jsonschema import Draft202012Validator

from src.config import PATHS
from src.dashboard.entities import (
    INDUSTRY,
    aggregate_industry,
    load_carrier_quarters,
    load_entity_quarters,
)
from src.dashboard.market import build_market_payload

MARKET_SCHEMA = json.loads(
    (PATHS.root / "contracts" / "web" / "market.schema.json").read_text(encoding="utf-8")
)

QUARTER_ROWS = {
    # carrier: {period: (passengers, ask_km, lf_reported, lf_derived, rask, cask, cask_ex_fuel)}
    "AEROMEXICO": {
        "2025Q4": (6.0e6, 14.0e9, 0.87, 0.87, 10.0, 8.0, None),
        "2026Q1": (5.8e6, 14.0e9, 0.84, 0.84, 9.7, 8.6, 6.3),
    },
    "VOLARIS": {
        "2025Q4": (8.2e6, 15.0e9, 0.85, 0.85, 5.8, 5.2, 3.6),
        "2026Q1": (7.8e6, 14.0e9, 0.85, 0.85, 5.4, 5.5, 3.8),
    },
    "VIVA_AEROBUS": {
        # 2025Q4: no reported load factor -> RPM/ASM is used and declared.
        "2025Q4": (7.8e6, 10.0e9, None, 0.85, 6.5, 5.6, 3.9),
        "2026Q1": (6.9e6, 9.0e9, 0.84, 0.84, 5.7, 6.4, 4.5),
    },
}


def _metric_rows() -> list[tuple]:
    rows = []
    for carrier, periods in QUARTER_ROWS.items():
        for period, (pax, ask, lf_rep, lf_der, rask, cask, ex_fuel) in periods.items():
            values = {
                "passengers": (pax, None),
                "asm_total": (ask / 1.609344, ask),
                "load_factor_total": (lf_rep, None),
                "load_factor_derived": (lf_der, None),
                "rask": (rask, rask),
                "cask": (cask, cask),
                "unit_margin": (rask - cask, rask - cask),
                "cask_ex_fuel": (ex_fuel, ex_fuel),
            }
            for metric, (value, value_metric) in values.items():
                if value is None:
                    continue
                rows.append((carrier, period, "quarter", "total", metric, value, value_metric))
    return rows


def _afac_rows() -> list[tuple]:
    rows = []
    shares = {"AEROMEXICO": 290, "VOLARIS": 370, "VIVA_AEROBUS": 330, "TAR": 10}
    for month in ("2025M10", "2025M11", "2025M12", "2026M01", "2026M02", "2026M03"):
        for carrier, value in shares.items():
            for segment, factor in (("total", 1.0), ("domestic", 0.8), ("international", 0.2)):
                if carrier == "TAR" and segment == "international":
                    continue
                rows.append((carrier, month, "month", segment, "passengers_afac", value * factor * 1000, None))
        rows.append(("MARKET_TOTAL_MX", month, "month", "total", "passengers_afac", 2.0e6, None))
    # Viva has no international row in 2026M02: missing, not zero.
    return [row for row in rows if not (row[0] == "VIVA_AEROBUS" and row[1] == "2026M02" and row[3] == "international")]


@pytest.fixture()
def warehouse(tmp_path: Path) -> Path:
    path = tmp_path / "warehouse.duckdb"
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "CREATE TABLE v_carrier_default (carrier_key VARCHAR, period_id VARCHAR, period_type VARCHAR, "
            "segment VARCHAR, metric_key VARCHAR, value DOUBLE, value_metric DOUBLE)"
        )
        connection.executemany(
            "INSERT INTO v_carrier_default VALUES (?, ?, ?, ?, ?, ?, ?)", _metric_rows() + _afac_rows()
        )
        connection.execute(
            "CREATE TABLE dim_source_artifact AS SELECT 'afac' AS source_system, TIMESTAMP '2026-09-13 00:00:00' AS downloaded_at"
        )
    return path


def test_carrier_quarters_use_reported_load_factor_and_declare_fallback(warehouse: Path) -> None:
    with duckdb.connect(str(warehouse), read_only=True) as connection:
        frame = load_carrier_quarters(connection)
    viva = frame[(frame.carrier_key == "VIVA_AEROBUS")].set_index("period_id")
    assert viva.loc["2025Q4", "load_factor_basis"] == "calculated"
    assert viva.loc["2026Q1", "load_factor_basis"] == "reported"
    assert viva.loc["2025Q4", "load_factor"] == pytest.approx(0.85)


def test_industry_is_ask_weighted_ratio_of_sums_not_a_simple_average(warehouse: Path) -> None:
    with duckdb.connect(str(warehouse), read_only=True) as connection:
        quarters = load_entity_quarters(connection)
    industry = quarters[INDUSTRY.key].set_index("period_id").loc["2026Q1"]
    asks = {"AEROMEXICO": 14.0e9, "VOLARIS": 14.0e9, "VIVA_AEROBUS": 9.0e9}
    rasks = {"AEROMEXICO": 9.7, "VOLARIS": 5.4, "VIVA_AEROBUS": 5.7}
    expected = sum(rasks[c] * asks[c] for c in asks) / sum(asks.values())
    assert industry["rask_cents_per_km"] == pytest.approx(expected)
    assert industry["rask_cents_per_km"] != pytest.approx(sum(rasks.values()) / 3)
    assert industry["passengers"] == pytest.approx(5.8e6 + 7.8e6 + 6.9e6)
    assert industry["ask_km"] == pytest.approx(sum(asks.values()))
    assert industry["unit_margin_cents_per_km"] == pytest.approx(
        industry["rask_cents_per_km"] - industry["cask_cents_per_km"]
    )


def test_industry_ex_fuel_is_missing_when_one_carrier_does_not_publish_it(warehouse: Path) -> None:
    with duckdb.connect(str(warehouse), read_only=True) as connection:
        quarters = load_entity_quarters(connection)
    industry = quarters[INDUSTRY.key].set_index("period_id")
    assert pd.isna(industry.loc["2025Q4", "cask_ex_fuel_cents_per_km"])
    assert industry.loc["2026Q1", "cask_ex_fuel_cents_per_km"] > 0


def test_industry_only_exists_on_the_constant_three_carrier_panel() -> None:
    carriers = pd.DataFrame(
        [
            {"carrier_key": carrier, "period_id": period, "passengers": 1.0, "ask_km": 1.0,
             "load_factor": 0.8, "rask_cents_per_km": 5.0, "cask_cents_per_km": 4.0,
             "unit_margin_cents_per_km": 1.0, "load_factor_basis": "reported",
             "cask_ex_fuel_cents_per_km": None}
            for carrier, period in [
                ("AEROMEXICO", "2022Q4"), ("VOLARIS", "2022Q4"),
                ("AEROMEXICO", "2023Q1"), ("VOLARIS", "2023Q1"), ("VIVA_AEROBUS", "2023Q1"),
            ]
        ]
    )
    industry = aggregate_industry(carriers)
    assert industry["period_id"].tolist() == ["2023Q1"]


def test_market_payload_shares_are_over_mexican_carriers_and_missing_stays_null(warehouse: Path) -> None:
    payload = build_market_payload(str(warehouse))
    errors = list(Draft202012Validator(MARKET_SCHEMA).iter_errors(payload))
    assert errors == [], errors[:3]

    month = {m["period_id"]: m for m in payload["months"]}
    total = month["2026M01"]["segments"]["total"]
    # Denominator: every Mexican carrier (TAR included), never MARKET_TOTAL_MX.
    assert total["mexican_carriers_passengers"] == pytest.approx(1_000_000)
    assert total["carriers"]["VOLARIS"]["share"] == pytest.approx(0.37)
    assert total["industry"]["share"] == pytest.approx(0.99)

    missing = month["2026M02"]["segments"]["international"]
    assert missing["carriers"]["VIVA_AEROBUS"]["passengers"] is None
    assert missing["carriers"]["VIVA_AEROBUS"]["share"] is None
    assert missing["industry"]["share"] is None

    quarters = {q["period_id"]: q for q in payload["quarters"]}
    assert set(quarters) == {"2025Q4", "2026Q1"}
    # The quarter with a missing Viva month keeps Viva missing, not a two-month sum.
    assert quarters["2026Q1"]["segments"]["international"]["carriers"]["VIVA_AEROBUS"]["share"] is None
    change = quarters["2026Q1"]["segments"]["total"]["carriers"]["AEROMEXICO"]["share_change_qoq_pp"]
    assert change == pytest.approx(0.0)
    assert payload["metadata"]["industry_note"].startswith("Industria = Aeroméxico, Volaris y Viva · 99%")
