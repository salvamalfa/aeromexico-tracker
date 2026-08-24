"""Shared deterministic utilities for the Stage 7 analytical layer."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

import duckdb
import pandas as pd

from src.config import PATHS
from src.ingest.stage4_common import write_parquet_atomic
from src.transform.stage6_contracts import validate_table


SEED = 1561861
ANALYTICS_DIR = PATHS.data / "analytics"
MODELS_DIR = PATHS.root / "models"


def warehouse_query(sql: str, parameters: list[Any] | None = None) -> pd.DataFrame:
    connection = duckdb.connect(str(PATHS.warehouse), read_only=True)
    try:
        return connection.execute(sql, parameters or []).df()
    finally:
        connection.close()


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in sorted(PATHS.gold.glob("*.parquet")):
        if path.name.startswith(("fact_forecasts", "dim_model", "fact_report_language", "fact_anomalies", "dim_cluster", "fact_study")):
            continue
        digest.update(path.name.encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def model_run_id(config: dict[str, Any]) -> str:
    payload = json.dumps(
        {"source_fingerprint": source_fingerprint(), "config": config},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"stage7_{hashlib.sha256(payload).hexdigest()[:16]}"


def code_version() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PATHS.root,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() or "unavailable"


def reproducible_timestamp() -> datetime:
    values: list[pd.Timestamp] = []
    for path in PATHS.gold.glob("*.parquet"):
        try:
            frame = pd.read_parquet(path, columns=["ingested_at"])
        except (KeyError, ValueError):
            continue
        if len(frame):
            values.append(pd.to_datetime(frame["ingested_at"], utc=True).max())
    if not values:
        return datetime(2000, 1, 1, tzinfo=UTC)
    return max(values).to_pydatetime()


def write_gold(table_name: str, frame: pd.DataFrame) -> Path:
    validated = validate_table(table_name, frame)
    path = PATHS.gold / f"{table_name}.parquet"
    write_parquet_atomic(validated, path)
    return path


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

