"""The margins are the estimator's ground truth, so their agreement is checked.

That the origin-destination workbook and the carrier series land on the same
integer, month after month, is the only evidence that AFAC holds a table
carrying route and carrier together.  If that ever stops being true these
tests should fail loudly rather than let a silently mismatched pair be fitted.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.ingest.afac.margins import (
    Reconciliation,
    read_carrier_base,
    read_summary_domestic_block,
    reconcile,
)


def test_reconciliation_reports_the_gap_in_both_absolute_and_relative_terms() -> None:
    row = Reconciliation("2025M02", route_passengers=4_481_158, carrier_passengers=4_481_168)
    assert row.difference == -10
    assert row.relative_pct == pytest.approx(-0.000223, abs=1e-6)


def test_reconciliation_survives_an_empty_carrier_month() -> None:
    """A month with no carrier rows must not raise on division."""

    row = Reconciliation("2099M01", route_passengers=10, carrier_passengers=0)
    assert row.difference == 10
    assert pd.isna(row.relative_pct)


def test_reconcile_only_compares_months_both_margins_cover() -> None:
    routes = pd.DataFrame(
        {"period_id": ["2026M01", "2026M02"], "pasajeros": [100, 200]}
    )
    carriers = pd.DataFrame(
        {"period_id": ["2026M02", "2026M03"], "pasajeros": [200, 300]}
    )
    rows = reconcile(routes, carriers)
    assert [row.period_id for row in rows] == ["2026M02"]
    assert rows[0].difference == 0


def test_carrier_base_keeps_scheduled_domestic_only(tmp_path: Path) -> None:
    """International, charter and zero-passenger rows are not part of the margin."""

    source = pd.DataFrame(
        {
            "Año": [2026] * 4,
            "Tipo": ["Nacional", "Internacional", "Nacional", "Nacional"],
            "Servicio": ["Regular", "Regular", "Fletamento ", "Regular"],
            "Región": ["Mexicana"] * 4,
            "Aerolinea": ["Volaris", "Volaris", "Volaris", "Carguera"],
            "Id_mes": [1, 1, 1, 1],
            "Mes": ["Ene"] * 4,
            "Pasajeros": [500, 900, 700, 0],
            "Fecha": [pd.Timestamp("2026-01-01")] * 4,
        }
    )
    path = tmp_path / "DB_AFAC.xlsx"
    source.to_excel(path, sheet_name="AFAC", index=False)

    result = read_carrier_base(path)
    assert list(result["carrier_name"]) == ["Volaris"]
    assert int(result.loc[0, "pasajeros"]) == 500
    assert result.loc[0, "period_id"] == "2026M01"


def test_carrier_base_pads_the_month_so_periods_sort(tmp_path: Path) -> None:
    source = pd.DataFrame(
        {
            "Año": [2026], "Tipo": ["Nacional"], "Servicio": ["Regular"],
            "Región": ["Mexicana"], "Aerolinea": ["Volaris"], "Id_mes": [9],
            "Mes": ["Sep"], "Pasajeros": [1], "Fecha": [pd.Timestamp("2026-09-01")],
        }
    )
    path = tmp_path / "DB_AFAC.xlsx"
    source.to_excel(path, sheet_name="AFAC", index=False)
    assert read_carrier_base(path).loc[0, "period_id"] == "2026M09"


# --------------------------------------------------------------------------
# The airline summary workbook, which is the only place flights per carrier
# are published.
# --------------------------------------------------------------------------

def test_the_domestic_block_stops_before_the_international_one(tmp_path: Path) -> None:
    """Reading past the block boundary triples the totals without any error."""

    rows = [[None] * 14 for _ in range(9)]
    rows[5] = ["EMPRESAS NACIONALES / DOMESTIC AIR CARRIERS"] + [None] * 13
    rows[6] = ["EN SERVICIO REGULAR NACIONAL / SCHEDULED DOMESTIC"] + [None] * 13
    body = [
        ["Volaris", 100, 110] + [None] * 11,
        ["T     o     t     a     l", 100, 110] + [None] * 11,
        ["EMPRESAS NACIONALES / DOMESTIC AIR CARRIERS"] + [None] * 13,
        ["EN SERVICIO REGULAR INTERNACIONAL"] + [None] * 13,
        ["Volaris", 999, 999] + [None] * 11,
    ]
    frame = pd.DataFrame(rows + body)
    path = tmp_path / "resumen.xlsx"
    frame.to_excel(path, sheet_name="VLOSREG", index=False, header=False)

    result = read_summary_domestic_block(path, "VLOSREG", 2026)
    assert set(result["carrier_name"]) == {"Volaris"}
    assert sorted(result["value"]) == [100, 110], "se coló el bloque internacional"


def test_a_sheet_without_a_domestic_block_raises(tmp_path: Path) -> None:
    path = tmp_path / "resumen.xlsx"
    pd.DataFrame([["EMPRESAS EXTRANJERAS"] + [None] * 13]).to_excel(
        path, sheet_name="VLOSREG", index=False, header=False
    )
    with pytest.raises(ValueError, match="domestic block"):
        read_summary_domestic_block(path, "VLOSREG", 2026)


def test_published_flights_fall_short_of_route_flights_by_the_cargo_carriers() -> None:
    """Freight airlines fly scheduled domestic legs and carry no passengers.

    Their flights are counted in the origin-destination workbook but they are
    absent from the passenger margin, so flights miss by about one per cent
    while passengers reconcile exactly.  Pinned so the gap is never mistaken
    for a parsing error.
    """

    routes = pd.read_csv("data/reference/afac_od_nacional_regular.csv")
    flights = pd.read_csv("data/reference/afac_carrier_flights_domestic.csv")
    by_route = routes.groupby("period_id")["vuelos"].sum()
    by_carrier = flights.groupby("period_id")["vuelos"].sum()
    shared = sorted(set(by_route.index) & set(by_carrier.index))
    assert len(shared) >= 10

    gap = ((by_route[shared] - by_carrier[shared]) / by_carrier[shared]).abs()
    assert gap.max() < 0.02, "el hueco crecio: revisar si entro otra aerolinea"
    assert gap.min() > 0.005, "el hueco desaparecio: revisar si se colaron las cargueras"
