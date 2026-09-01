"""Declared Pandera contracts for every versioned Gold table."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pandera.pandas as pa
import yaml

from src.config import PATHS
from src.transform.stage9_lineage import add_record_ids


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

    contracts = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    for table_name, definition in contracts.get("tables", {}).items():
        if not definition.get("grain"):
            raise ValueError(f"Gold contract is missing grain: {table_name}")
    return contracts


def table_definitions(*, max_stage: int | None = None) -> dict[str, Any]:
    """Return declared tables, optionally bounded to a pipeline stage."""

    tables = load_contracts()["tables"]
    if max_stage is None:
        return tables
    return {
        name: definition
        for name, definition in tables.items()
        if int(definition.get("stage", 6)) <= max_stage
    }


def contract_for(table_name: str) -> pa.DataFrameSchema:
    """Create a strict Pandera schema from the versioned YAML declaration."""

    definition = load_contracts()["tables"][table_name]
    columns: dict[str, pa.Column] = {}
    for name, properties in definition["columns"].items():
        column_checks: list[pa.Check] = []
        if "allowed_values" in properties:
            column_checks.append(pa.Check.isin(properties["allowed_values"]))
        if "min" in properties:
            column_checks.append(pa.Check.ge(properties["min"]))
        if "max" in properties:
            column_checks.append(pa.Check.le(properties["max"]))
        if "regex" in properties:
            column_checks.append(pa.Check.str_matches(properties["regex"]))
        columns[name] = pa.Column(
            _dtype(properties["type"], properties["nullable"]),
            checks=column_checks,
            nullable=properties["nullable"],
            coerce=True,
            unique=bool(properties.get("unique", False)),
        )
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


def _state_token(row: pd.Series, columns: list[str]) -> tuple[object, ...]:
    values: list[object] = []
    for column in columns:
        value = row[column]
        values.append(None if pd.isna(value) else value)
    return tuple(values)


def validate_table_invariants(
    table_name: str, frame: pd.DataFrame, definition: dict[str, Any]
) -> None:
    """Evaluate relational invariants declared alongside a Gold contract."""

    for invariant in definition.get("invariants", []):
        kind = invariant.get("kind")
        name = invariant.get("name", kind or "unnamed")
        if kind != "scd2_history":
            raise ValueError(f"Unsupported invariant {table_name}.{name}: {kind!r}")
        keys = list(invariant["key_columns"])
        value_columns = list(invariant.get("value_columns", ["value"]))
        required = {
            *keys,
            *value_columns,
            "valid_from",
            "valid_to",
            "is_current",
            "restatement_count",
        }
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError(
                f"Invariant {table_name}.{name} is missing columns: {missing}"
            )
        invalid_intervals = frame["valid_to"].notna() & frame["valid_to"].lt(
            frame["valid_from"]
        )
        if invalid_intervals.any():
            raise ValueError(
                f"Invariant {table_name}.{name} has "
                f"{int(invalid_intervals.sum())} reversed validity intervals"
            )
        for logical_key, group in frame.groupby(keys, dropna=False, sort=False):
            ordered = group.sort_values("valid_from", kind="stable").reset_index(drop=True)
            current = ordered["is_current"].fillna(False).astype(bool)
            if int(current.sum()) != 1 or not bool(current.iloc[-1]):
                raise ValueError(
                    f"Invariant {table_name}.{name} requires one final current row; "
                    f"key={logical_key!r}"
                )
            if ordered.loc[current, "valid_to"].notna().any() or ordered.loc[
                ~current, "valid_to"
            ].isna().any():
                raise ValueError(
                    f"Invariant {table_name}.{name} has inconsistent valid_to/current; "
                    f"key={logical_key!r}"
                )
            counters = ordered["restatement_count"].astype(int).tolist()
            if counters != list(range(len(ordered))):
                raise ValueError(
                    f"Invariant {table_name}.{name} has non-ordinal restatement_count; "
                    f"key={logical_key!r}, observed={counters}"
                )
            if len(ordered) > 1:
                valid_from = pd.to_datetime(ordered["valid_from"]).astype(
                    "datetime64[ns]"
                )
                expected_to = (
                    valid_from.shift(-1).iloc[:-1] - np.timedelta64(1, "us")
                )
                actual_to = (
                    pd.to_datetime(ordered["valid_to"].iloc[:-1])
                    .astype("datetime64[ns]")
                    .reset_index(drop=True)
                )
                if not actual_to.equals(expected_to.reset_index(drop=True)):
                    raise ValueError(
                        f"Invariant {table_name}.{name} has a validity gap or overlap; "
                        f"key={logical_key!r}"
                    )
                states = [
                    _state_token(row, value_columns)
                    for _, row in ordered.iterrows()
                ]
                if any(left == right for left, right in zip(states, states[1:])):
                    raise ValueError(
                        f"Invariant {table_name}.{name} increments restatement_count "
                        f"without a value change; key={logical_key!r}"
                    )


def add_record_id(table_name: str, frame: pd.DataFrame) -> pd.DataFrame:
    """Add the stable ``rec_<sha256>`` id from the declared business grain.

    ``record_id`` is an opaque lineage key.  It is deliberately not the Gold
    table's business grain and is never derived from a raw source hash.
    """

    definition = load_contracts()["tables"][table_name]
    if "record_id" not in definition["columns"]:
        return frame.copy()
    grain = definition.get("grain", [])
    if not isinstance(grain, list) or not grain:
        raise ValueError(f"record_id requires a declared grain: {table_name}")
    return add_record_ids(
        frame.drop(columns=["record_id"], errors="ignore"),
        table_name=table_name,
        natural_key_columns=grain,
    )


def validate_table(table_name: str, frame: pd.DataFrame) -> pd.DataFrame:
    """Validate a full table, returning a schema-coerced frame."""

    definition = load_contracts()["tables"][table_name]
    validated = contract_for(table_name).validate(frame, lazy=True)
    validate_table_invariants(table_name, validated, definition)
    return validated


def validate_all_gold(*, max_stage: int | None = None) -> dict[str, int]:
    """Validate every declared table against its physical Parquet output."""

    results: dict[str, int] = {}
    for table_name in table_definitions(max_stage=max_stage):
        path = PATHS.gold / f"{table_name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Declared gold table is missing: {path}")
        frame = pd.read_parquet(path)
        validate_table(table_name, frame)
        results[table_name] = len(frame)
    validate_relationships(max_stage=max_stage)
    return results


def validate_relationships(*, max_stage: int | None = None) -> dict[str, int]:
    """Validate every declared foreign key without relying on DuckDB constraints."""

    definitions = table_definitions(max_stage=max_stage)
    cache: dict[str, pd.DataFrame] = {}
    results: dict[str, int] = {}
    for table_name, definition in definitions.items():
        for foreign_key in definition.get("foreign_keys", []):
            parent_name = foreign_key["references"]["table"]
            if parent_name not in definitions:
                continue
            child_columns = list(foreign_key["columns"])
            parent_columns = list(foreign_key["references"]["columns"])
            if len(child_columns) != len(parent_columns):
                raise ValueError(f"Mismatched foreign key declaration in {table_name}")
            child = cache.setdefault(table_name, pd.read_parquet(PATHS.gold / f"{table_name}.parquet"))
            parent = cache.setdefault(parent_name, pd.read_parquet(PATHS.gold / f"{parent_name}.parquet"))
            child_keys = child[child_columns].dropna().drop_duplicates()
            parent_keys = parent[parent_columns].dropna().drop_duplicates()
            renamed = {parent: child for child, parent in zip(child_columns, parent_columns)}
            orphaned = child_keys.merge(parent_keys.rename(columns=renamed), on=child_columns, how="left", indicator=True)
            orphaned = orphaned[orphaned["_merge"].eq("left_only")]
            key = f"{table_name}:{','.join(child_columns)}->{parent_name}"
            results[key] = len(orphaned)
            if len(orphaned):
                sample = orphaned[child_columns].head(10).to_dict("records")
                raise ValueError(f"Foreign key violation {key}: {len(orphaned)} orphan rows; sample={sample}")
    return results


def declared_gold_paths(*, max_stage: int | None = None) -> list[Path]:
    return [
        PATHS.gold / f"{name}.parquet"
        for name in table_definitions(max_stage=max_stage)
    ]
