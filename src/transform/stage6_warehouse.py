"""Build the local DuckDB warehouse and its consumption views."""

from __future__ import annotations

from pathlib import Path

import duckdb

from src.config import PATHS
from src.transform.stage6_contracts import load_contracts


SQL_DIR = PATHS.root / "sql" / "gold"


def build_warehouse() -> list[str]:
    temporary = PATHS.data / "warehouse.stage6.tmp.duckdb"
    temporary.unlink(missing_ok=True)
    connection = duckdb.connect(str(temporary))
    try:
        for table_name in load_contracts()["tables"]:
            path = (PATHS.gold / f"{table_name}.parquet").resolve().as_posix()
            connection.execute(
                f'CREATE OR REPLACE TABLE "{table_name}" AS SELECT * FROM read_parquet(?)',
                [path],
            )
        for sql_path in sorted(SQL_DIR.glob("*.sql")):
            connection.execute(sql_path.read_text(encoding="utf-8"))
        views = [row[0] for row in connection.execute(
            "SELECT table_name FROM information_schema.views WHERE table_schema = 'main' ORDER BY table_name"
        ).fetchall()]
        connection.execute("CHECKPOINT")
    finally:
        connection.close()
    PATHS.warehouse.unlink(missing_ok=True)
    temporary.replace(PATHS.warehouse)
    return views
