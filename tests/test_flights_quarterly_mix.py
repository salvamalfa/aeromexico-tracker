"""``_load_mix`` must never turn a missing monthly value into a published 0.

Regression test for PR #10: ``pandas.Series.sum()`` skips nulls by default
(and returns 0.0 when every value in the group is null), so a quarter missing
one or all of its three monthly SEC segment values was still marked complete
and published with a (partially or wholly fabricated) summed total instead
of being withheld, in violation of AGENTS.md's "no conviertas un faltante en
cero".
"""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from src.dashboard.flights import _load_mix


def _mix_row(period_id: str, metric_key: str, segment: str, value: float | None) -> dict:
    return {
        "period_id": period_id,
        "metric_key": metric_key,
        "segment": segment,
        "value": value,
        "unit_normalized": "count",
        "source_file": "test.htm",
        "source_hash": "a" * 64,
    }


def _connection_with_rows(rows: list[dict]) -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(":memory:")
    frame = pd.DataFrame(rows)
    connection.register("mix_df", frame)
    connection.execute(
        "CREATE VIEW v_carrier_default AS "
        "SELECT *, 'AEROMEXICO' AS carrier_key, 'month' AS period_type, "
        "'sec_edgar' AS source_system FROM mix_df"
    )
    return connection


def _complete_quarter_rows(period_ids: list[str], *, override: dict | None = None) -> list[dict]:
    """Three fully reconciling months (domestic + international == total)."""

    override = override or {}
    rows = []
    for period_id in period_ids:
        values = {
            ("passengers", "domestic"): 100.0, ("passengers", "international"): 50.0,
            ("passengers", "total"): 150.0,
            ("asm_total", "domestic"): 1_000.0, ("asm_total", "international"): 500.0,
            ("asm_total", "total"): 1_500.0,
            ("rpm_total", "domestic"): 800.0, ("rpm_total", "international"): 400.0,
            ("rpm_total", "total"): 1_200.0,
        }
        values.update(override.get(period_id, {}))
        for (metric_key, segment), value in values.items():
            rows.append(_mix_row(period_id, metric_key, segment, value))
    return rows


def test_complete_quarter_is_published_and_sums_exactly():
    rows = _complete_quarter_rows(["2026M04", "2026M05", "2026M06"])
    connection = _connection_with_rows(rows)
    result = _load_mix(connection)
    assert "2026Q2" in result
    assert result["2026Q2"]["passengers"]["total"] == pytest.approx(450.0)


def test_one_null_month_withholds_the_whole_quarter_not_a_partial_sum():
    rows = _complete_quarter_rows(
        ["2026M04", "2026M05", "2026M06"],
        override={"2026M05": {("passengers", "domestic"): None}},
    )
    connection = _connection_with_rows(rows)
    result = _load_mix(connection)
    assert "2026Q2" not in result


def test_all_null_month_values_never_publish_a_fabricated_zero():
    """The historical bug: `Series.sum()` of an all-null group returns 0.0,
    which used to reach the payload as a false, complete-looking zero."""

    rows = _complete_quarter_rows(
        ["2026M04", "2026M05", "2026M06"],
        override={
            month: {
                ("passengers", "domestic"): None,
                ("passengers", "international"): None,
                ("passengers", "total"): None,
            }
            for month in ("2026M04", "2026M05", "2026M06")
        },
    )
    connection = _connection_with_rows(rows)
    result = _load_mix(connection)
    assert "2026Q2" not in result


def test_non_finite_month_value_also_withholds_the_quarter():
    rows = _complete_quarter_rows(
        ["2026M04", "2026M05", "2026M06"],
        override={"2026M06": {("rpm_total", "total"): float("inf")}},
    )
    connection = _connection_with_rows(rows)
    result = _load_mix(connection)
    assert "2026Q2" not in result
