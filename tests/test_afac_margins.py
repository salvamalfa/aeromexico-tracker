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

from src.ingest.afac.margins import Reconciliation, read_carrier_base, reconcile


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
