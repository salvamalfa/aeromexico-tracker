"""Shared, deliberately small helpers for Stage 4 source pipelines."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd

from src.common.http import SourceHttpClient
from src.common.storage import save_bronze
from src.config import PATHS


PARSER_VERSION = "stage4_v1.0.0"


def utc_now() -> datetime:
    return datetime.now(UTC)


def fetch_bronze(
    client: SourceHttpClient,
    url: str,
    *,
    source_system: str,
    entity: str,
    period: str,
    ext: str,
    relative_dir: str,
    notes: str = "",
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
) -> Path:
    response = client.request("GET", url, headers=headers, params=params)
    return save_bronze(
        response.content,
        source_system,
        entity,
        period,
        ext,
        str(response.url),
        "httpx",
        notes,
        http_status=response.status_code,
        content_type=response.headers.get("content-type", "application/octet-stream"),
        relative_dir=relative_dir,
    )


def lineage(path: Path) -> dict[str, Any]:
    metadata_path = path.with_suffix(path.suffix + ".meta.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return {
        "source_file": path.relative_to(PATHS.bronze).as_posix(),
        "source_hash": metadata["sha256"],
        "ingested_at": pd.Timestamp(metadata["downloaded_at"]),
        "parser_version": PARSER_VERSION,
    }


def bronze_period(path: Path) -> str:
    """Return the logical period stored beside one immutable bronze artifact."""

    metadata_path = path.with_suffix(path.suffix + ".meta.json")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    parts = str(metadata["logical_key"]).split("|")
    if len(parts) != 4:
        raise ValueError(f"Invalid logical_key in {metadata_path}")
    return parts[2]


def latest_bronze(source_system: str, entity: str) -> Path | None:
    """Return the newest existing artifact for a Stage 4 logical entity."""

    manifest = PATHS.bronze / "_manifest.jsonl"
    if not manifest.exists():
        return None
    prefix = f"{source_system}|{entity}|"
    records = [
        json.loads(line)
        for line in manifest.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    for record in reversed(records):
        if not str(record.get("logical_key", "")).startswith(prefix):
            continue
        source_file = record.get("source_file")
        if not isinstance(source_file, str):
            continue
        path = PATHS.bronze / source_file
        if path.is_file():
            return path
    return None


def write_parquet_atomic(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".parquet", dir=path.parent, delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        frame.to_parquet(temporary, index=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
