"""Declarative contracts and lineage checks for every Silver dataset."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import yaml

from src.config import PATHS


CONTRACT_PATH = PATHS.root / "config" / "silver_schema_contracts.yaml"
DIRECT_LINEAGE = {"source_file", "source_hash", "ingested_at", "parser_version"}
LINEAGE_TYPES = {
    "direct_artifact",
    "derived_from_silver",
    "reconciliation",
    "reference_catalog",
}


def load_silver_contracts() -> dict[str, Any]:
    """Load and structurally validate the Silver catalog."""

    contracts = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    for table_name, definition in contracts.get("tables", {}).items():
        if not definition.get("grain"):
            raise ValueError(f"Silver contract is missing grain: {table_name}")
        if not definition.get("required_columns"):
            raise ValueError(f"Silver contract has no required columns: {table_name}")
        lineage_type = definition.get("lineage_type")
        if lineage_type not in LINEAGE_TYPES:
            raise ValueError(f"Invalid Silver lineage_type for {table_name}: {lineage_type}")
        required = set(definition["required_columns"])
        if lineage_type == "direct_artifact":
            lineage_columns = set(definition.get("lineage_columns", DIRECT_LINEAGE))
            missing = lineage_columns - required
            if missing:
                raise ValueError(f"Direct Silver contract {table_name} omits lineage columns: {sorted(missing)}")
    return contracts


def _validate_column_checks(table_name: str, frame: pd.DataFrame, definition: dict[str, Any]) -> None:
    for column_name, rules in definition.get("columns", {}).items():
        if column_name not in frame:
            raise ValueError(f"Silver contract {table_name} is missing constrained column {column_name}")
        values = frame[column_name].dropna()
        if "allowed_values" in rules:
            invalid = values[~values.isin(rules["allowed_values"])]
            if not invalid.empty:
                raise ValueError(f"Silver domain violation {table_name}.{column_name}: {sorted(invalid.astype(str).unique())[:10]}")
        if "min" in rules and (values < rules["min"]).any():
            raise ValueError(f"Silver minimum violation {table_name}.{column_name}")
        if "max" in rules and (values > rules["max"]).any():
            raise ValueError(f"Silver maximum violation {table_name}.{column_name}")


def validate_silver_table(table_name: str, frame: pd.DataFrame) -> int:
    """Validate presence, declared grain, lineage and stable business domains."""

    definition = load_silver_contracts()["tables"][table_name]
    missing = sorted(set(definition["required_columns"]) - set(frame.columns))
    if missing:
        raise ValueError(f"Silver contract {table_name} is missing columns: {missing}")
    grain = list(definition["grain"])
    missing_grain = sorted(set(grain) - set(frame.columns))
    if missing_grain:
        raise ValueError(f"Silver grain {table_name} is missing columns: {missing_grain}")
    if not definition.get("allow_duplicate_grain", False) and frame.duplicated(grain).any():
        sample = frame.loc[frame.duplicated(grain, keep=False), grain].head(10).to_dict("records")
        raise ValueError(f"Duplicate Silver grain {table_name}: {sample}")
    _validate_column_checks(table_name, frame, definition)
    return len(frame)


def validate_silver_relationships() -> dict[str, int]:
    """Reject orphan keys for the relationships declared in the Silver catalog."""

    definitions = load_silver_contracts()["tables"]
    cache: dict[str, pd.DataFrame] = {}
    results: dict[str, int] = {}
    for table_name, definition in definitions.items():
        for foreign_key in definition.get("foreign_keys", []):
            parent_name = foreign_key["references"]["table"]
            child_columns = list(foreign_key["columns"])
            parent_columns = list(foreign_key["references"]["columns"])
            child = cache.setdefault(table_name, pd.read_parquet(PATHS.silver / f"{table_name}.parquet"))
            parent = cache.setdefault(parent_name, pd.read_parquet(PATHS.silver / f"{parent_name}.parquet"))
            child_keys = child[child_columns].dropna().drop_duplicates()
            parent_keys = parent[parent_columns].dropna().drop_duplicates().rename(
                columns={parent: child for child, parent in zip(child_columns, parent_columns)}
            )
            orphaned = child_keys.merge(parent_keys, on=child_columns, how="left", indicator=True)
            orphaned = orphaned.loc[orphaned["_merge"].eq("left_only")]
            key = f"{table_name}:{','.join(child_columns)}->{parent_name}"
            results[key] = len(orphaned)
            if len(orphaned):
                raise ValueError(f"Silver foreign key violation {key}: {orphaned[child_columns].head(10).to_dict('records')}")
        for foreign_key in definition.get("foreign_keys_any_of", []):
            child_columns = list(foreign_key["columns"])
            child = cache.setdefault(
                table_name,
                pd.read_parquet(PATHS.silver / f"{table_name}.parquet"),
            )
            child_keys = child[child_columns].dropna().drop_duplicates()
            parent_sets: list[pd.DataFrame] = []
            parent_names: list[str] = []
            for reference in foreign_key["references"]:
                parent_name = reference["table"]
                parent_names.append(parent_name)
                parent_columns = list(reference["columns"])
                if len(child_columns) != len(parent_columns):
                    raise ValueError(f"Mismatched alternative foreign key in {table_name}")
                parent = cache.setdefault(
                    parent_name,
                    pd.read_parquet(PATHS.silver / f"{parent_name}.parquet"),
                )
                parent_sets.append(
                    parent[parent_columns]
                    .dropna()
                    .drop_duplicates()
                    .rename(
                        columns={
                            parent_column: child_column
                            for child_column, parent_column in zip(child_columns, parent_columns)
                        }
                    )
                )
            valid_keys = pd.concat(parent_sets, ignore_index=True).drop_duplicates()
            orphaned = child_keys.merge(valid_keys, on=child_columns, how="left", indicator=True)
            orphaned = orphaned.loc[orphaned["_merge"].eq("left_only")]
            key = f"{table_name}:{','.join(child_columns)}->{'|'.join(parent_names)}"
            results[key] = len(orphaned)
            if len(orphaned):
                raise ValueError(
                    f"Silver alternative foreign key violation {key}: "
                    f"{orphaned[child_columns].head(10).to_dict('records')}"
                )
    return results


def validate_all_silver() -> dict[str, int]:
    """Validate all and only the physical Silver datasets."""

    definitions = load_silver_contracts()["tables"]
    declared = set(definitions)
    physical = {path.stem for path in PATHS.silver.glob("*.parquet")}
    if declared != physical:
        raise ValueError(
            f"Silver catalog mismatch; undeclared={sorted(physical - declared)}, missing={sorted(declared - physical)}"
        )
    results = {
        table_name: validate_silver_table(
            table_name,
            pd.read_parquet(PATHS.silver / f"{table_name}.parquet"),
        )
        for table_name in sorted(definitions)
    }
    validate_silver_relationships()
    return results


def run_silver_contract_validation() -> dict[str, Any]:
    """Validate Silver and persist a deterministic, inspectable receipt."""

    rows = validate_all_silver()
    relationships = validate_silver_relationships()
    payload: dict[str, Any] = {
        "contract_version": load_silver_contracts()["version"],
        "status": "passed",
        "tables": rows,
        "relationships": relationships,
    }
    target = PATHS.quality / "stage9_silver_contracts.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return payload
