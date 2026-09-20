"""Build the local DuckDB warehouse and its consumption views."""

from __future__ import annotations

from pathlib import Path

import duckdb

from src.config import PATHS
from src.transform.stage6_contracts import table_definitions


SQL_DIR = PATHS.root / "sql" / "gold"


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
        route_extensions = (
            "fact_aicm_international_scheduled_route_movements",
            "bridge_aicm_international_slot_lineage",
            "fact_aifa_shared_route_presence",
            "bridge_aifa_shared_route_presence_lineage",
            "fact_domestic_exclusive_market_inferences",
            "bridge_domestic_exclusive_market_lineage",
            "fact_route_carrier_domestic_estimate",
            "fact_domestic_scheduled_route_movements",
            "bridge_domestic_slot_lineage",
            "fact_international_route_observations",
            "bridge_international_route_lineage",
            "fact_oma_documented_routes",
            "bridge_oma_documented_route_lineage",
        )
        for name in route_extensions:
            path = PATHS.gold / f"{name}.parquet"
            if path.exists():
                connection.execute(
                    f"CREATE TABLE {name} AS SELECT * FROM read_parquet(?)",
                    [str(path)],
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
