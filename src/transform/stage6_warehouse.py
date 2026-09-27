"""Build the local DuckDB warehouse and its consumption views."""

from __future__ import annotations

from pathlib import Path

import duckdb

from src.config import PATHS
from src.transform.stage6_contracts import table_definitions


SQL_DIR = PATHS.root / "sql" / "gold"

# The bronze "research" artifacts each publicly-derivable route extension is
# built from. They are not fetched by any `ingest.*` pipeline step (they are
# manually captured documents), but they ARE ordinary files copied wholesale
# into a `just rebuild` clean checkout (only `data/gold` and friends are
# excluded there, see `src.rebuild.create_clean_checkout`). So whenever these
# bronze files are present, the corresponding Gold parquet must be too: its
# absence means the six route-extension transformers below silently did not
# run as part of the rebuild (they are intentionally not registered in
# `src.pipeline.registry.PIPELINE_STEPS`, since they need a human/agent to run
# them once new bronze research is captured, not automatic network ingestion).
# `None` marks a table whose regeneration depends on paid/raw provider inputs
# (AeroDataBox sweeps or the private domestic IPF derivation) that this public
# repository never carries: for those, a missing file stays a silent skip.
_DOMESTIC_SLOTS_SOURCE = (
    PATHS.bronze / "domestic_routes_research" / "aicm_aeromexico_summer_slots_2026S26_20260913T004629Z.pdf",
)
_OMA_ROUTES_SOURCE = (
    PATHS.bronze / "international_routes" / "oma_mty_cdg_route_launch_2026Q2_20260913T143058Z.pdf",
)
_AFAC_SOURCE = PATHS.bronze / "afac_research" / "afac_research_city_pairs_2026M07_20260908T182059Z.xlsx"
_AIFA_ROSTER_SOURCE = (
    PATHS.bronze / "domestic_routes_research" / "expansion_aifa_airline_destinations_2026M06_20260913T200713Z.html"
)
# src.transform.afac_exclusive_domestic reads all three of these (AFAC, the
# AIFA airline roster, and the Colima transfer document).
_EXCLUSIVE_MARKET_SOURCES = (
    _AFAC_SOURCE,
    _AIFA_ROSTER_SOURCE,
    PATHS.bronze / "domestic_routes_research" / "colima_subsectur_mirror_colima_aicm_transfer_2026M05_20260913T200338Z.html",
)
# src.transform.aifa_shared_presence reads only AFAC and the AIFA roster; the
# Colima transfer document is unrelated to it. Giving it its own tuple (not
# _EXCLUSIVE_MARKET_SOURCES) means a snapshot that carries the workbook and
# the roster but not the Colima document still fails closed when this Gold is
# missing, instead of silently skipping it.
_AIFA_SHARED_PRESENCE_SOURCES = (
    _AFAC_SOURCE,
    _AIFA_ROSTER_SOURCE,
)
_INTERNATIONAL_ROUTES_SOURCE = (
    PATHS.bronze / "international_routes" / "selection.json",
)

ROUTE_EXTENSION_BRONZE_SOURCES: dict[str, tuple[Path, ...] | None] = {
    "fact_aicm_international_scheduled_route_movements": _DOMESTIC_SLOTS_SOURCE,
    "bridge_aicm_international_slot_lineage": _DOMESTIC_SLOTS_SOURCE,
    "fact_aifa_shared_route_presence": _AIFA_SHARED_PRESENCE_SOURCES,
    "bridge_aifa_shared_route_presence_lineage": _AIFA_SHARED_PRESENCE_SOURCES,
    "fact_domestic_exclusive_market_inferences": _EXCLUSIVE_MARKET_SOURCES,
    "bridge_domestic_exclusive_market_lineage": _EXCLUSIVE_MARKET_SOURCES,
    "fact_route_carrier_domestic_estimate": None,
    "fact_aeromexico_domestic_capacity_estimate": None,
    "fact_route_carrier_international_estimate": None,
    "fact_aeromexico_international_capacity_estimate": None,
    "fact_domestic_scheduled_route_movements": _DOMESTIC_SLOTS_SOURCE,
    "bridge_domestic_slot_lineage": _DOMESTIC_SLOTS_SOURCE,
    "fact_international_route_observations": _INTERNATIONAL_ROUTES_SOURCE,
    "bridge_international_route_lineage": _INTERNATIONAL_ROUTES_SOURCE,
    "fact_oma_documented_routes": _OMA_ROUTES_SOURCE,
    "bridge_oma_documented_route_lineage": _OMA_ROUTES_SOURCE,
}


class RouteExtensionMissingError(RuntimeError):
    """A route-extension Gold table is missing although its bronze source exists."""


def build_warehouse(*, max_stage: int = 6) -> list[str]:
    temporary = PATHS.data / "warehouse.stage6.tmp.duckdb"
    temporary.unlink(missing_ok=True)
    connection = duckdb.connect(str(temporary))
    try:
        for table_name in table_definitions(max_stage=max_stage):
            path = (PATHS.gold / f"{table_name}.parquet").resolve().as_posix()
            connection.execute(
                f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM read_parquet(?)',
                [path],
            )
        for sql_path in sorted(SQL_DIR.glob("*.sql")):
            sql_stage = 8 if sql_path.name.startswith("08_") else (7 if sql_path.name.startswith("07_") else 6)
            if sql_stage > max_stage:
                continue
            connection.execute(sql_path.read_text(encoding="utf-8"))
        # Optional validated route extensions survive every warehouse reconstruction.
        # They intentionally remain outside the Stage 9 core contract, but the
        # Vuelos payload and their focused lineage tests consume them from DuckDB.
        for name, bronze_sources in ROUTE_EXTENSION_BRONZE_SOURCES.items():
            path = PATHS.gold / f"{name}.parquet"
            if path.exists():
                connection.execute(
                    f"CREATE TABLE {name} AS SELECT * FROM read_parquet(?)",
                    [str(path)],
                )
            elif bronze_sources is not None and all(source.exists() for source in bronze_sources):
                raise RouteExtensionMissingError(
                    f"{name}.parquet is missing from data/gold, but its bronze source "
                    f"({', '.join(str(source) for source in bronze_sources)}) is present. "
                    "Run the corresponding src.transform.* route-extension generator before "
                    "rebuilding the warehouse, or the rebuilt DuckDB will silently drop this "
                    "route Gold."
                )
        views = [row[0] for row in connection.execute(
            "SELECT table_name FROM information_schema.views WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()]
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    PATHS.warehouse.unlink(missing_ok=True)
    temporary.replace(PATHS.warehouse)
    return views
