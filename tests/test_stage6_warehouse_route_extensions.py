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


def test_aifa_shared_presence_source_excludes_the_unrelated_colima_document():
    # src.transform.aifa_shared_presence only reads the AFAC workbook and the
    # AIFA airline roster (see its `_verified(AFAC)` / `_verified(ROSTER)`
    # calls); it never touches the Colima transfer document, which belongs to
    # the separate fact_domestic_exclusive_market_inferences generator. Each
    # table's guard must list exactly the inputs its own generator reads, or
    # a snapshot with the workbook+roster but no Colima document would not
    # fail closed when this Gold is missing.
    for name in ("fact_aifa_shared_route_presence", "bridge_aifa_shared_route_presence_lineage"):
        sources = warehouse.ROUTE_EXTENSION_BRONZE_SOURCES[name]
        assert sources is not None
        assert len(sources) == 2
        assert not any("colima" in str(source).lower() for source in sources)


def test_aifa_shared_presence_gold_missing_with_only_its_own_sources_fails_loudly(tmp_path, monkeypatch):
    name = "fact_aifa_shared_route_presence"
    fake_bronze = tmp_path / "bronze"
    afac_dir = fake_bronze / "afac_research"
    roster_dir = fake_bronze / "domestic_routes_research"
    afac_dir.mkdir(parents=True)
    roster_dir.mkdir(parents=True)
    afac = afac_dir / "afac.xlsx"
    roster = roster_dir / "roster.html"
    afac.write_bytes(b"stub")
    roster.write_bytes(b"stub")
    monkeypatch.setattr(
        warehouse,
        "ROUTE_EXTENSION_BRONZE_SOURCES",
        {**warehouse.ROUTE_EXTENSION_BRONZE_SOURCES, name: (afac, roster)},
    )

    gold = _patch_paths(monkeypatch, tmp_path, bronze_dir=fake_bronze)
    with pytest.raises(warehouse.RouteExtensionMissingError, match=name):
        warehouse.build_warehouse(max_stage=9)


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


def test_initial_stage6_build_defers_the_guard_to_later_rebuilds(tmp_path, monkeypatch):
    # `transform.stage6` builds the core warehouse before the route-extension
    # generators (which depend on it) can run, so a clean Gold with present
    # bronze must not abort that first build; the Stage 9 rebuild still does.
    name = "fact_oma_documented_routes"
    fake_bronze = tmp_path / "bronze"
    fake_bronze.mkdir()
    (fake_bronze / "present.pdf").write_bytes(b"stub")
    monkeypatch.setattr(
        warehouse,
        "ROUTE_EXTENSION_BRONZE_SOURCES",
        {**warehouse.ROUTE_EXTENSION_BRONZE_SOURCES, name: (fake_bronze / "present.pdf",)},
    )
    _patch_paths(monkeypatch, tmp_path, bronze_dir=fake_bronze)

    warehouse.build_warehouse(max_stage=6, enforce_route_extensions=False)
    with pytest.raises(warehouse.RouteExtensionMissingError, match=name):
        warehouse.build_warehouse(max_stage=9)


def test_transform_stage6_calls_the_warehouse_without_the_guard():
    import inspect

    from src.transform import stage6

    assert "build_warehouse(max_stage=6, enforce_route_extensions=False)" in inspect.getsource(stage6.run)


def test_guard_resolves_bronze_against_the_active_paths_not_import_time(tmp_path, monkeypatch):
    # Locally the real Bronze exists; a test (or rebuild workspace) that points
    # PATHS at an empty Bronze must not be judged against it. Before this fix
    # the sources were absolute paths frozen at import, so every hermetic
    # warehouse test raised RouteExtensionMissingError on a machine with data.
    assert all(
        sources is None or all(not source.is_absolute() for source in sources)
        for sources in warehouse.ROUTE_EXTENSION_BRONZE_SOURCES.values()
    )
    real_like_bronze = tmp_path / "real_bronze"
    for sources in warehouse.ROUTE_EXTENSION_BRONZE_SOURCES.values():
        for source in sources or ():
            (real_like_bronze / source).parent.mkdir(parents=True, exist_ok=True)
            (real_like_bronze / source).write_bytes(b"stub")
    empty_bronze = tmp_path / "bronze"
    empty_bronze.mkdir()
    _patch_paths(monkeypatch, tmp_path, bronze_dir=empty_bronze)
    warehouse.build_warehouse(max_stage=9)

    monkeypatch.setattr(warehouse.PATHS, "bronze", real_like_bronze)
    with pytest.raises(warehouse.RouteExtensionMissingError):
        warehouse.build_warehouse(max_stage=9)
