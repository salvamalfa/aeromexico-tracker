"""Tests for the portable SEC series inspection output."""

from __future__ import annotations

import polars as pl

from src.parse.sec.inspect_series import format_series


def test_format_series_is_ascii_and_stable() -> None:
    frame = pl.DataFrame(
        {
            "period_id": ["2025Q1"],
            "load_factor_pct": [82.3],
            "trasm_usd_cents": [15.6],
            "casm_ex_fuel_usd_cents": [10.2],
        }
    )

    rendered = format_series(frame)

    assert rendered == (
        "period_id,load_factor_pct,trasm_usd_cents,casm_ex_fuel_usd_cents\n"
        "2025Q1,82.3,15.6,10.2"
    )
    rendered.encode("ascii")
