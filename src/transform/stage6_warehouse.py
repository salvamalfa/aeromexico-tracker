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
# run as part of the rebuild. They ARE registered as `transform.*` steps in
# `src.pipeline.registry.PIPELINE_STEPS` (gated on the same bronze files, and
# ordered after `transform.stage6` since each reads `dim_airport` from the
# warehouse it builds), so a clean `just rebuild` regenerates them whenever
# the bronze research is present; this guard still exists to fail loudly if a
# generator's output goes missing for any other reason.
# `None` marks a table whose regeneration depends on paid/raw provider inputs
# (AeroDataBox sweeps or the private domestic IPF derivation) that this public
# repository never carries: for those, a missing file stays a silent skip.
# `src.pipeline.registry` cannot import these constants directly at module
# load time (`src.transform.__init__` imports `src.pipeline`, so importing
# `src.transform.stage6_warehouse` from `src.pipeline.registry` is a cycle).
# Its `transform.*` route-extension steps instead repeat the same root-
# relative bronze paths literally; `tests/test_pipeline_route_extension_steps.py`
# cross-checks the two against each other and against
# `ROUTE_EXTENSION_GENERATOR_STEPS` below so they cannot silently drift apart.
DOMESTIC_SLOTS_SOURCE = (
    PATHS.bronze / "domestic_routes_research" / "aicm_aeromexico_summer_slots_2026S26_20260913T004629Z.pdf",
)
OMA_ROUTES_SOURCE = (
    PATHS.bronze / "international_routes" / "oma_mty_cdg_route_launch_2026Q2_20260913T143058Z.pdf",
)
AFAC_SOURCE = PATHS.bronze / "afac_research" / "afac_research_city_pairs_2026M07_20260908T182059Z.xlsx"
AIFA_ROSTER_SOURCE = (
    PATHS.bronze / "domestic_routes_research" / "expansion_aifa_airline_destinations_2026M06_20260913T200713Z.html"
)
# src.transform.afac_exclusive_domestic reads all three of these (AFAC, the
# AIFA airline roster, and the Colima transfer document).
EXCLUSIVE_MARKET_SOURCES = (
    AFAC_SOURCE,
    AIFA_ROSTER_SOURCE,
    PATHS.bronze / "domestic_routes_research" / "colima_subsectur_mirror_colima_aicm_transfer_2026M05_20260913T200338Z.html",
)
# src.transform.aifa_shared_presence reads only AFAC and the AIFA roster; the
# Colima transfer document is unrelated to it. Giving it its own tuple (not
# EXCLUSIVE_MARKET_SOURCES) means a snapshot that carries the workbook and
# the roster but not the Colima document still fails closed when this Gold is
# missing, instead of silently skipping it.
AIFA_SHARED_PRESENCE_SOURCES = (
    AFAC_SOURCE,
    AIFA_ROSTER_SOURCE,
)
INTERNATIONAL_ROUTES_SOURCE = (
    PATHS.bronze / "international_routes" / "selection.json",
)

ROUTE_EXTENSION_BRONZE_SOURCES: dict[str, tuple[Path, ...] | None] = {
    "fact_aicm_international_scheduled_route_movements": DOMESTIC_SLOTS_SOURCE,
    "bridge_aicm_international_slot_lineage": DOMESTIC_SLOTS_SOURCE,
    "fact_aifa_shared_route_presence": AIFA_SHARED_PRESENCE_SOURCES,
    "bridge_aifa_shared_route_presence_lineage": AIFA_SHARED_PRESENCE_SOURCES,
    "fact_domestic_exclusive_market_inferences": EXCLUSIVE_MARKET_SOURCES,
    "bridge_domestic_exclusive_market_lineage": EXCLUSIVE_MARKET_SOURCES,
    "fact_route_carrier_domestic_estimate": None,
    "fact_aeromexico_domestic_capacity_estimate": None,
    "fact_route_carrier_international_estimate": None,
    "fact_aeromexico_international_capacity_estimate": None,
    "fact_domestic_scheduled_route_movements": DOMESTIC_SLOTS_SOURCE,
    "bridge_domestic_slot_lineage": DOMESTIC_SLOTS_SOURCE,
    "fact_international_route_observations": INTERNATIONAL_ROUTES_SOURCE,
    "bridge_international_route_lineage": INTERNATIONAL_ROUTES_SOURCE,
    "fact_oma_documented_routes": OMA_ROUTES_SOURCE,
    "bridge_oma_documented_route_lineage": OMA_ROUTES_SOURCE,
}

# Maps each route-extension Gold table with a public bronze source to the
# pipeline step that regenerates it, so `src.pipeline.registry` and its tests
# can assert the DAG actually produces what this guard requires instead of
# only gating on the file existing. Paid/private-only tables (`None` above)
# have no such step: nothing in a public rebuild can regenerate them.
ROUTE_EXTENSION_GENERATOR_STEPS: dict[str, str] = {
    "fact_aicm_international_scheduled_route_movements": "transform.aicm_international_slots",
    "bridge_aicm_international_slot_lineage": "transform.aicm_international_slots",
    "fact_aifa_shared_route_presence": "transform.aifa_shared_presence",
    "bridge_aifa_shared_route_presence_lineage": "transform.aifa_shared_presence",
    "fact_domestic_exclusive_market_inferences": "transform.afac_exclusive_domestic",
    "bridge_domestic_exclusive_market_lineage": "transform.afac_exclusive_domestic",
    "fact_domestic_scheduled_route_movements": "transform.domestic_slots",
    "bridge_domestic_slot_lineage": "transform.domestic_slots",
    "fact_international_route_observations": "transform.international_routes",
    "bridge_international_route_lineage": "transform.international_routes",
    "fact_oma_documented_routes": "transform.oma_documented_routes",
    "bridge_oma_documented_route_lineage": "transform.oma_documented_routes",
}


class RouteExtensionMissingError(RuntimeError):
    """A route-extension Gold table is missing although its bronze source exists."""


def build_warehouse(*, max_stage: int = 6, enforce_route_extensions: bool = True) -> list[str]:
    """Rebuild DuckDB from Gold.

    `enforce_route_extensions=False` is only for the initial core build in
    `transform.stage6`: the route-extension generators depend on that step, so
    their Gold cannot exist yet. Every later rebuild (Stage 7, 8, 9) enforces
    the guard and fails if a generator did not run.
    """
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
            elif (
                enforce_route_extensions
                and bronze_sources is not None
                and all(source.exists() for source in bronze_sources)
            ):
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
