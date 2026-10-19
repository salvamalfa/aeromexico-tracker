"""Candidate Gold provenance through the existing Stage 9 record-lineage gates."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.config import PATHS
from src.source_updates.catalog import ROOT
from src.transform.stage6_contracts import load_contracts, validate_all_gold, validate_table
from src.transform.stage9 import build_record_lineage_specs, lineage_evidence
from src.transform.stage9_lineage import build_bridge_record_lineage, build_dim_source_artifact
from src.transform.validate_stage9 import validate_lineage_frames


def validate_macro_units(frame: pd.DataFrame) -> None:
    expected = {
        "policy_rate": "percent",
        "usd_mxn_fix": "mxn_per_usd",
        "usd_mxn": "mxn_per_usd",
        "inpc": "index",
        "jet_fuel_usd_per_gallon": "usd_per_gallon",
    }
    for indicator, unit in expected.items():
        if not frame.loc[frame.indicator_key.eq(indicator), "unit"].eq(unit).all():
            raise ValueError(f"Gold macro {indicator} requires unit={unit}")


def materialize_lineage() -> dict:
    from src.ingest.stage4_common import write_parquet_atomic

    validate_all_gold(max_stage=6)
    contracts = load_contracts()
    tables = {
        name: pd.read_parquet(PATHS.gold / f"{name}.parquet")
        for name, definition in contracts["tables"].items()
        if int(definition.get("stage", 6)) <= 6 and "record_id" in definition["columns"]
    }
    validate_macro_units(tables["fact_macro"])
    artifacts = validate_table("dim_source_artifact", build_dim_source_artifact(verify_files=True))
    bridge = validate_table(
        "bridge_record_lineage",
        build_bridge_record_lineage(build_record_lineage_specs(tables, artifacts), artifacts),
    )
    validation = validate_lineage_frames(tables=tables, artifacts=artifacts, bridge=bridge)
    for name, frame in (("dim_source_artifact", artifacts), ("bridge_record_lineage", bridge)):
        write_parquet_atomic(frame, PATHS.gold / f"{name}.parquet")
    result = {
        "scope": "Stage6 record-bearing tables; no analytics or publication",
        "validation": validation,
        **lineage_evidence(tables, artifacts, bridge),
    }
    (PATHS.quality / "candidate_gold_lineage.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def prepare_provenance(workspace: Path) -> tuple[pd.DataFrame, dict]:
    """Reject fabricated catalogs/bridges by rebuilding the catalog from actual Bronze."""
    if any(not (workspace / "data/gold" / name).is_file() for name in ("dim_source_artifact.parquet", "bridge_record_lineage.parquet")):
        raise ValueError("Gold lineage catalogue and bridge are required for inherited hashes")
    artifacts = validate_table(
        "dim_source_artifact", pd.read_parquet(workspace / "data/gold/dim_source_artifact.parquet")
    )
    expected = validate_table(
        "dim_source_artifact",
        build_dim_source_artifact(
            workspace / "data/bronze/_manifest.jsonl",
            catalog_path=ROOT / "config/source_catalog.yaml",
            verify_files=True,
        ),
    )
    pd.testing.assert_frame_equal(artifacts, expected, check_like=True)
    bridge = validate_table(
        "bridge_record_lineage", pd.read_parquet(workspace / "data/gold/bridge_record_lineage.parquet")
    )
    definitions = load_contracts()["tables"]
    names = set(bridge.table_name)
    if not names <= set(definitions):
        raise ValueError("Undeclared table in Gold lineage bridge")
    tables = {name: pd.read_parquet(workspace / "data/gold" / f"{name}.parquet") for name in names}
    for name, frame in tables.items():
        validate_table(name, frame)
    if "fact_macro" in tables:
        validate_macro_units(tables["fact_macro"])
    validate_lineage_frames(tables=tables, artifacts=artifacts, bridge=bridge)
    return artifacts.set_index("artifact_id"), {
        record: group for record, group in bridge.groupby("record_id")
    }


def contributing_files(workspace: Path, selected: pd.DataFrame, aliases: list[str], cache: dict) -> set[str]:
    if "provenance" not in cache:
        cache["provenance"] = prepare_provenance(workspace)
    artifacts, records = cache["provenance"]
    memo: dict[str, set[str]] = {}

    def ancestry(record_id: str, trail: set[str]) -> set[str]:
        if record_id in memo:
            return memo[record_id]
        if record_id in trail or record_id not in records:
            raise ValueError("Missing or cyclic Gold record lineage")
        links = records[record_id]
        resolved = set(links.artifact_id.dropna().astype(str))
        for parent in links.parent_record_id.dropna().astype(str):
            resolved |= ancestry(parent, trail | {record_id})
        if not resolved or links.link_type.eq("declaration").any():
            raise ValueError("Gold record lacks exact documentary ancestry")
        memo[record_id] = resolved
        return resolved

    files: set[str] = set()
    for record in selected.record_id.astype(str):
        contributors = artifacts.loc[sorted(ancestry(record, set()))]
        if not contributors.source_system.isin(aliases).any():
            raise ValueError("Gold ancestry does not contain the requested source")
        files.update(contributors.source_file.astype(str))
    return files
