"""Route-extension Gold must not silently vanish from a rebuilt warehouse.

Regression test for the `just rebuild` gap where `create_clean_checkout`
copies `data/bronze` (including the manually-captured route-extension
research artifacts) but excludes `data/gold`, while the six generators that
turn that bronze into route-extension Gold are not part of
`src.pipeline.registry.PIPELINE_STEPS`. Before this fix, `build_warehouse`
silently skipped the missing Gold instead of failing, so a rebuild could ship
a warehouse quietly missing route Gold that a prior, non-rebuilt environment
had.
"""

from types import SimpleNamespace

import pandas as pd
import pytest

from src.transform import stage6_warehouse as warehouse


def _patch_paths(monkeypatch, tmp_path, *, bronze_dir):
    gold = tmp_path / "gold"
    gold.mkdir()
    sql = tmp_path / "sql"
    sql.mkdir()
    monkeypatch.setattr(
        warehouse,
        "PATHS",
        SimpleNamespace(data=tmp_path, gold=gold, bronze=bronze_dir, warehouse=tmp_path / "warehouse.duckdb"),
    )
    monkeypatch.setattr(warehouse, "SQL_DIR", sql)
    monkeypatch.setattr(warehouse, "table_definitions", lambda **kwargs: {})
    return gold


def test_missing_gold_with_bronze_present_fails_loudly(tmp_path, monkeypatch):
    # Use the real, documented bronze/gold pairing for one publicly-derivable table.
    name = "fact_domestic_scheduled_route_movements"
    assert warehouse.ROUTE_EXTENSION_BRONZE_SOURCES[name] is not None

    fake_bronze = tmp_path / "bronze"
    monkeypatch.setattr(
        warehouse,
        "ROUTE_EXTENSION_BRONZE_SOURCES",
        {**warehouse.ROUTE_EXTENSION_BRONZE_SOURCES, name: (fake_bronze / "present.pdf",)},
    )
    fake_bronze.mkdir()
    (fake_bronze / "present.pdf").write_bytes(b"stub")

    gold = _patch_paths(monkeypatch, tmp_path, bronze_dir=fake_bronze)
    # Every other route-extension table stays absent with no bronze -> silent skip.
    with pytest.raises(warehouse.RouteExtensionMissingError, match=name):
        warehouse.build_warehouse(max_stage=9)


def test_missing_gold_without_bronze_is_silently_skipped(tmp_path, monkeypatch):
    fake_bronze = tmp_path / "bronze"
    fake_bronze.mkdir()
    gold = _patch_paths(monkeypatch, tmp_path, bronze_dir=fake_bronze)
    # None of the bronze sources exist in this checkout: no route extension
    # Gold can be produced, so a missing file must not raise.
    warehouse.build_warehouse(max_stage=9)


def test_paid_derived_tables_are_never_gated_on_bronze(tmp_path, monkeypatch):
    for name in (
        "fact_route_carrier_domestic_estimate",
        "fact_aeromexico_domestic_capacity_estimate",
        "fact_route_carrier_international_estimate",
        "fact_aeromexico_international_capacity_estimate",
    ):
        assert warehouse.ROUTE_EXTENSION_BRONZE_SOURCES[name] is None


def test_present_gold_still_loads_into_warehouse(tmp_path, monkeypatch):
    fake_bronze = tmp_path / "bronze"
    fake_bronze.mkdir()
    gold = _patch_paths(monkeypatch, tmp_path, bronze_dir=fake_bronze)
    pd.DataFrame({"record_id": ["rec_test"]}).to_parquet(
        gold / "fact_oma_documented_routes.parquet", index=False
    )
    warehouse.build_warehouse(max_stage=9)
    import duckdb

    with duckdb.connect(str(tmp_path / "warehouse.duckdb")) as connection:
        assert connection.execute("select count(*) from fact_oma_documented_routes").fetchone()[0] == 1
