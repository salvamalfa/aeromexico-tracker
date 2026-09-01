from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd
import pytest

from src.transform.stage6_dimensions import consolidation_method
from src.transform.stage6_facts import select_preferred_sources


ROOT = Path(__file__).resolve().parents[1]


def _fact_row(
    carrier: str,
    metric: str,
    value: float,
    source: str,
    *,
    preliminary: bool = False,
    confidence: float = 1.0,
    ingested_at: str = "2026-01-01",
) -> dict[str, object]:
    timestamp = pd.Timestamp(ingested_at)
    return {
        "carrier_key": carrier,
        "period_id": "2026Q1",
        "calendar_period_id": "2026Q1",
        "fiscal_period_id": "2026Q1",
        "period_type": "quarter",
        "period_start_date": pd.Timestamp("2026-01-01").date(),
        "period_end_date": pd.Timestamp("2026-03-31").date(),
        "metric_key": metric,
        "segment": "total",
        "value": value,
        "value_metric": None,
        "value_imperial": None,
        "value_as_reported": value,
        "unit_as_reported": "unit",
        "unit_normalized": "unit",
        "currency": None,
        "value_original_currency": None,
        "value_usd": None,
        "fx_rate_used": None,
        "fx_rate_type": None,
        "is_derived": False,
        "is_preliminary": preliminary,
        "is_estimated": False,
        "derivation_formula": None,
        "valid_from": timestamp,
        "valid_to": None,
        "is_current": True,
        "restatement_count": 0,
        "source_system": source,
        "source_file": f"{source}.parquet",
        "source_hash": source.ljust(64, "0")[:64],
        "ingested_at": timestamp,
        "confidence": confidence,
    }


def _connection() -> duckdb.DuckDBPyConnection:
    rows = [
        _fact_row("AEROMEXICO", "passengers", 100.0, "afac"),
        _fact_row("AEROMEXICO_CONNECT", "passengers", 30.0, "afac"),
        _fact_row("AEROMEXICO", "load_factor_total", 0.84, "sec_edgar"),
        _fact_row("AEROMEXICO_CONNECT", "load_factor_total", 0.90, "sec_edgar"),
        _fact_row("AEROMEXICO", "fleet_size", 169.0, "sec_edgar"),
        _fact_row("AEROMEXICO_CONNECT", "fleet_size", 50.0, "sec_edgar"),
        _fact_row(
            "AEROMEXICO",
            "total_revenue",
            100.0,
            "sec_edgar",
            preliminary=True,
            confidence=1.0,
            ingested_at="2026-02-01",
        ),
        _fact_row(
            "AEROMEXICO",
            "total_revenue",
            90.0,
            "aeromexico_ir",
            preliminary=False,
            confidence=0.8,
            ingested_at="2026-01-01",
        ),
    ]
    carriers = pd.DataFrame(
        [
            {"carrier_key": "AEROMEXICO", "parent_carrier_key": None},
            {"carrier_key": "AEROMEXICO_CONNECT", "parent_carrier_key": "AEROMEXICO"},
        ]
    )
    metrics = pd.DataFrame(
        [
            {"metric_key": "passengers", "consolidation_method": "sum"},
            {"metric_key": "load_factor_total", "consolidation_method": "non_additive"},
            {"metric_key": "fleet_size", "consolidation_method": "latest"},
            {"metric_key": "total_revenue", "consolidation_method": "sum"},
        ]
    )
    priorities = pd.DataFrame(
        [
            {"data_domain": "carrier_metrics", "source_system": "sec_edgar", "priority": 0, "is_default": False},
            {"data_domain": "carrier_metrics", "source_system": "aeromexico_ir", "priority": 0, "is_default": False},
            {"data_domain": "carrier_metrics", "source_system": "afac", "priority": 1, "is_default": False},
            {"data_domain": "carrier_metrics", "source_system": "*", "priority": 2, "is_default": True},
        ]
    )
    priorities["source_priority_order"] = "asc"
    priorities["is_preliminary_order"] = "asc"
    priorities["confidence_order"] = "desc"
    priorities["ingested_at_order"] = "desc"
    connection = duckdb.connect(":memory:")
    connection.register("facts_fixture", pd.DataFrame(rows))
    connection.register("carriers_fixture", carriers)
    connection.register("metrics_fixture", metrics)
    connection.register("priorities_fixture", priorities)
    connection.execute("CREATE TABLE fact_carrier_metrics AS SELECT * FROM facts_fixture")
    connection.execute("CREATE TABLE dim_carrier AS SELECT * FROM carriers_fixture")
    connection.execute("CREATE TABLE dim_metric AS SELECT * FROM metrics_fixture")
    connection.execute("CREATE TABLE dim_source_priority AS SELECT * FROM priorities_fixture")
    connection.execute((ROOT / "sql" / "gold" / "01_business_views.sql").read_text(encoding="utf-8"))
    return connection


def test_python_precedence_uses_priority_preliminary_confidence_and_ingestion() -> None:
    frame = pd.DataFrame(
        [
            _fact_row("AEROMEXICO", "total_revenue", 100, "sec_edgar", preliminary=True, confidence=1.0, ingested_at="2026-03-01"),
            _fact_row("AEROMEXICO", "total_revenue", 90, "aeromexico_ir", preliminary=False, confidence=0.8, ingested_at="2026-01-01"),
            _fact_row("AEROMEXICO", "total_revenue", 95, "sec_filing", preliminary=False, confidence=0.9, ingested_at="2025-12-01"),
        ]
    )
    selected = select_preferred_sources(
        frame,
        ["carrier_key", "period_id", "metric_key"],
    )
    assert len(selected) == 1
    assert selected.iloc[0]["source_system"] == "sec_filing"
    assert selected.iloc[0]["value"] == 95


def test_consolidation_rules_are_explicit() -> None:
    assert consolidation_method("passengers") == "sum"
    assert consolidation_method("fleet_size") == "latest"
    assert consolidation_method("load_factor_total") == "non_additive"
    assert consolidation_method("ttm_total_revenue") == "sum"
    assert consolidation_method("yoy_growth_total_revenue") == "non_additive"
    with pytest.raises(ValueError, match="no consolidation rule"):
        consolidation_method("unreviewed_metric")


def test_sql_consolidation_never_sums_non_additive_or_latest_metrics() -> None:
    connection = _connection()
    try:
        values = dict(
            connection.execute(
                "SELECT metric_key, value FROM v_carrier_default "
                "WHERE carrier_key='AEROMEXICO' ORDER BY metric_key"
            ).fetchall()
        )
    finally:
        connection.close()
    assert values["passengers"] == 130.0
    assert values["load_factor_total"] == 0.84
    assert values["fleet_size"] == 169.0
    assert values["total_revenue"] == 90.0


def test_python_and_sql_source_precedence_return_the_same_record() -> None:
    source_rows = pd.DataFrame(
        [
            _fact_row(
                "AEROMEXICO", "total_revenue", 100.0, "sec_edgar",
                preliminary=True, confidence=1.0, ingested_at="2026-02-01",
            ),
            _fact_row(
                "AEROMEXICO", "total_revenue", 90.0, "aeromexico_ir",
                preliminary=False, confidence=0.8, ingested_at="2026-01-01",
            ),
        ]
    )
    python_value = select_preferred_sources(
        source_rows,
        ["carrier_key", "period_id", "metric_key", "segment"],
    ).iloc[0]["value"]
    connection = _connection()
    try:
        sql_value = connection.execute(
            "SELECT value FROM v_carrier_default WHERE metric_key='total_revenue'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert sql_value == python_value == 90.0


def test_sql_consolidation_rejects_missing_or_unweighted_rules() -> None:
    connection = _connection()
    try:
        connection.execute("DELETE FROM dim_metric WHERE metric_key='load_factor_total'")
        with pytest.raises(duckdb.Error, match="Missing consolidation rule"):
            connection.execute(
                "SELECT value FROM v_carrier_consolidated WHERE metric_key='load_factor_total'"
            ).fetchall()
        connection.execute(
            "INSERT INTO dim_metric VALUES ('load_factor_total', 'weighted')"
        )
        with pytest.raises(duckdb.Error, match="explicit weight metric"):
            connection.execute(
                "SELECT value FROM v_carrier_consolidated WHERE metric_key='load_factor_total'"
            ).fetchall()
    finally:
        connection.close()
