"""Declared Pandera contracts for every Stage 6 gold table."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pandera.pandas as pa
import yaml

from src.config import PATHS


CONTRACT_PATH = PATHS.root / "config" / "gold_schema_contracts.yaml"
TYPE_MAP: dict[str, Any] = {
    "string": pa.String,
    "float": pa.Float64,
    "int": pa.Int64,
    "bool": pa.Bool,
    "date": pa.Date,
    "datetime": pa.DateTime,
}


def _dtype(type_name: str, nullable: bool) -> Any:
    if type_name == "int" and nullable:
        return pd.Int64Dtype()
    if type_name == "bool" and nullable:
        return pd.BooleanDtype()
    return TYPE_MAP[type_name]


def load_contracts() -> dict[str, Any]:
    """Load the versioned schema catalog used by validation and documentation."""

    return yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))


def contract_for(table_name: str) -> pa.DataFrameSchema:
    """Create a strict Pandera schema from the versioned YAML declaration."""

    definition = load_contracts()["tables"][table_name]
    columns = {
        name: pa.Column(_dtype(properties["type"], properties["nullable"]), nullable=properties["nullable"], coerce=True)
        for name, properties in definition["columns"].items()
    }
    checks: list[pa.Check] = []
    primary_key = definition.get("primary_key", [])
    if primary_key and not definition.get("allow_duplicate_key", False):
        checks.append(
            pa.Check(
                lambda frame: ~frame.duplicated(primary_key).any(),
                error=f"duplicate primary key: {primary_key}",
            )
        )
    return pa.DataFrameSchema(columns, checks=checks, strict=True, coerce=True)


def validate_table(table_name: str, frame: pd.DataFrame) -> pd.DataFrame:
    """Validate a full table, returning a schema-coerced frame."""

    return contract_for(table_name).validate(frame, lazy=True)


def validate_all_gold() -> dict[str, int]:
    """Validate every declared table against its physical Parquet output."""

    results: dict[str, int] = {}
    for table_name in load_contracts()["tables"]:
        path = PATHS.gold / f"{table_name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Declared gold table is missing: {path}")
        frame = pd.read_parquet(path)
        validate_table(table_name, frame)
        results[table_name] = len(frame)
    return results


def declared_gold_paths() -> list[Path]:
    return [PATHS.gold / f"{name}.parquet" for name in load_contracts()["tables"]]
