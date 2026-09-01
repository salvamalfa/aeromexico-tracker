"""Acceptance checks for Stage 9 record identifiers and lineage metadata."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
import importlib
import json
import re
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from src.config import PATHS
from src.ingest.stage4_common import write_parquet_atomic
from src.pipeline.registry import PIPELINE_STEPS, validate_registry
from src.transform.scd2 import build_scd2_history
from src.transform.silver_contracts import (
    load_silver_contracts,
    validate_all_silver,
    validate_silver_relationships,
)
from src.transform.stage6_contracts import (
    load_contracts,
    validate_all_gold,
    validate_relationships,
    validate_table,
)
from src.transform.stage6_dimensions import consolidation_method
from src.transform.stage6_facts import select_preferred_sources
from src.transform.stage9_lineage import (
    build_dim_source,
    build_dim_source_artifact,
    build_dim_source_priority,
    make_record_id,
)
from src.transform.stage9_quality import (
    REFERENCE_OPERATIONAL_LEDGER,
    read_operational_issues,
)


_RECORD_ID = re.compile(r"^rec_[0-9a-f]{64}$")
_ARTIFACT_ID = re.compile(r"^art_[0-9a-f]{64}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LOCAL_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|file://|\\\\)", re.IGNORECASE)


def _fail(message: str) -> None:
    raise ValueError(f"Stage 9 lineage validation failed: {message}")


def validate_lineage_frames(
    *,
    tables: Mapping[str, pd.DataFrame],
    artifacts: pd.DataFrame,
    bridge: pd.DataFrame,
    contracts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate in-memory lineage before any Stage 9 files are published."""

    catalog = contracts or load_contracts()
    expected_records: set[tuple[str, str]] = set()
    all_record_ids: set[str] = set()
    table_counts: dict[str, int] = {}
    for table_name, frame in sorted(tables.items()):
        definition = catalog["tables"].get(table_name)
        if definition is None:
            _fail(f"undeclared record table {table_name}")
        grain = definition.get("grain")
        if not isinstance(grain, list) or not grain:
            _fail(f"{table_name} has no declared natural grain")
        missing = [column for column in ["record_id", *grain] if column not in frame]
        if missing:
            _fail(f"{table_name} is missing columns {missing}")
        identifiers = frame["record_id"].astype(str)
        if identifiers.duplicated().any():
            _fail(f"{table_name} has duplicate record_id values")
        if not identifiers.map(lambda value: bool(_RECORD_ID.fullmatch(value))).all():
            _fail(f"{table_name} contains a malformed record_id")
        expected = frame.apply(
            lambda row: make_record_id(
                table_name, {column: row[column] for column in grain}
            ),
            axis=1,
        )
        mismatch = identifiers.ne(expected)
        if mismatch.any():
            sample = identifiers[mismatch].head(3).tolist()
            _fail(
                f"{table_name} record_id is not derived from table + grain; sample={sample}"
            )
        for record_id in identifiers:
            expected_records.add((table_name, record_id))
            if record_id in all_record_ids:
                _fail(f"record_id is not globally unique: {record_id}")
            all_record_ids.add(record_id)
        table_counts[table_name] = len(frame)

    required_artifacts = {"artifact_id", "artifact_sha256", "source_file", "source_url"}
    missing_artifacts = required_artifacts - set(artifacts.columns)
    if missing_artifacts:
        _fail(f"dim_source_artifact is missing {sorted(missing_artifacts)}")
    if artifacts["artifact_id"].duplicated().any():
        _fail("dim_source_artifact has duplicate artifact_id values")
    artifact_hash_by_id: dict[str, str] = {}
    for row in artifacts.itertuples(index=False):
        artifact_id = str(row.artifact_id)
        digest = str(row.artifact_sha256)
        if not _ARTIFACT_ID.fullmatch(artifact_id) or not _SHA256.fullmatch(digest):
            _fail("dim_source_artifact contains a malformed identifier or hash")
        if _LOCAL_PATH.search(str(row.source_file)):
            _fail("dim_source_artifact exposes an absolute local path")
        if not str(row.source_url).startswith("https://"):
            _fail("dim_source_artifact contains a non-HTTPS source URL")
        artifact_hash_by_id[artifact_id] = digest

    required_bridge = {
        "lineage_link_id",
        "record_id",
        "table_name",
        "lineage_type",
        "link_type",
        "lineage_status",
        "artifact_id",
        "artifact_sha256",
        "parent_record_id",
        "lineage_fingerprint",
        "lineage_note",
    }
    missing_bridge = required_bridge - set(bridge.columns)
    if missing_bridge:
        _fail(f"bridge_record_lineage is missing {sorted(missing_bridge)}")
    if bridge["lineage_link_id"].duplicated().any():
        _fail("bridge_record_lineage has duplicate lineage_link_id values")
    actual_records = set(
        bridge[["table_name", "record_id"]]
        .astype(str)
        .itertuples(index=False, name=None)
    )
    missing_declarations = expected_records - actual_records
    extra_declarations = actual_records - expected_records
    if missing_declarations or extra_declarations:
        _fail(
            f"record coverage differs: missing={len(missing_declarations)}, "
            f"extra={len(extra_declarations)}"
        )

    fingerprint_counts = bridge.groupby(["table_name", "record_id"])[
        "lineage_fingerprint"
    ].nunique(dropna=False)
    if not fingerprint_counts.eq(1).all():
        _fail("one record has multiple lineage fingerprints")
    if not bridge["lineage_fingerprint"].astype(str).map(
        lambda value: bool(_SHA256.fullmatch(value))
    ).all():
        _fail("bridge_record_lineage contains a malformed lineage_fingerprint")

    artifact_links = bridge[bridge["link_type"].eq("artifact")]
    for row in artifact_links.itertuples(index=False):
        artifact_id = str(row.artifact_id)
        if artifact_id not in artifact_hash_by_id:
            _fail(f"bridge references unknown artifact {artifact_id}")
        if str(row.artifact_sha256) != artifact_hash_by_id[artifact_id]:
            _fail(f"bridge artifact hash differs from catalog for {artifact_id}")
        if str(row.lineage_fingerprint) == str(row.artifact_sha256):
            _fail("artifact_sha256 was reused as a lineage_fingerprint")

    non_artifact_links = bridge[~bridge["link_type"].eq("artifact")]
    if non_artifact_links["artifact_id"].notna().any() or non_artifact_links[
        "artifact_sha256"
    ].notna().any():
        _fail("a non-artifact link contains artifact identifiers")
    parent_links = bridge[bridge["link_type"].eq("parent_record")]
    unknown_parents = set(parent_links["parent_record_id"].dropna().astype(str)) - all_record_ids
    if unknown_parents:
        _fail(f"bridge references {len(unknown_parents)} unknown parent records")
    declarations = bridge[bridge["link_type"].eq("declaration")]
    if declarations["lineage_note"].isna().any():
        _fail("a declared-without-artifact record has no explanatory note")
    if bridge["lineage_note"].dropna().astype(str).map(
        lambda value: bool(_LOCAL_PATH.search(value))
    ).any():
        _fail("a lineage note exposes an absolute local path")

    resolved_artifact_records = int(
        artifact_links[["table_name", "record_id"]].drop_duplicates().shape[0]
    )
    resolved_parent_records = int(
        parent_links[["table_name", "record_id"]].drop_duplicates().shape[0]
    )
    declared_records = int(
        declarations[["table_name", "record_id"]].drop_duplicates().shape[0]
    )
    return {
        "status": "passed",
        "record_tables": table_counts,
        "records_expected": len(expected_records),
        "records_declared": len(actual_records),
        "coverage_pct": 1.0,
        "artifact_records": resolved_artifact_records,
        "parent_records": resolved_parent_records,
        "declared_without_exact_link_records": declared_records,
        "artifact_count": len(artifacts),
        "unknown_parent_records": 0,
        "unknown_artifact_records": 0,
    }


def _frames_equal(left: pd.DataFrame, right: pd.DataFrame) -> bool:
    try:
        pd.testing.assert_frame_equal(
            left.reset_index(drop=True),
            right.reset_index(drop=True),
            check_dtype=True,
            check_like=False,
        )
    except AssertionError:
        return False
    return True


def _resolve_registry_callables() -> list[str]:
    resolved: list[str] = []
    for step in PIPELINE_STEPS:
        module_name, attribute = step.callable_ref.split(":", 1)
        value = getattr(importlib.import_module(module_name), attribute)
        if not callable(value):
            raise TypeError(f"Pipeline callable is not callable: {step.callable_ref}")
        resolved.append(step.step_id)
    return resolved


def _source_statuses(
    sources: pd.DataFrame, artifacts: pd.DataFrame
) -> list[dict[str, Any]]:
    artifact_counts = artifacts.groupby("source_key").size().to_dict()
    statuses: list[dict[str, Any]] = []
    for row in sources.sort_values("source_key").itertuples(index=False):
        count = int(artifact_counts.get(row.source_key, 0))
        if count:
            status = "available"
            reason = f"{count} immutable Bronze artifacts"
        elif bool(row.artifact_expected):
            status = "not_available"
            reason = "No artifact exists in the current Bronze snapshot"
        else:
            status = "not_applicable"
            reason = "Curated or derived source with no standalone public artifact"
        statuses.append(
            {
                "source_key": str(row.source_key),
                "status": status,
                "reason": reason,
                "artifact_count": count,
            }
        )
    return statuses


def _scd2_fixture_evidence() -> dict[str, Any]:
    fixture = pd.DataFrame(
        [
            {
                "carrier_key": "AEROMEXICO",
                "period_id": "2025Q2",
                "metric_key": "total_revenue",
                "segment": "total",
                "value": 1.0,
                "ingested_at": "2025-07-01T00:00:00Z",
            },
            {
                "carrier_key": "AEROMEXICO",
                "period_id": "2025Q2",
                "metric_key": "total_revenue",
                "segment": "total",
                "value": 1.0,
                "ingested_at": "2025-07-02T00:00:00Z",
            },
            {
                "carrier_key": "AEROMEXICO",
                "period_id": "2025Q2",
                "metric_key": "total_revenue",
                "segment": "total",
                "value": 2.0,
                "ingested_at": "2025-07-03T00:00:00Z",
            },
        ]
    )
    history = build_scd2_history(
        fixture,
        key_columns=["carrier_key", "period_id", "metric_key", "segment"],
    )
    return {
        "input_observations": len(fixture),
        "versions": len(history),
        "values": history["value"].tolist(),
        "restatement_count": history["restatement_count"].astype(int).tolist(),
        "is_current": history["is_current"].astype(bool).tolist(),
        "first_valid_to": history.iloc[0]["valid_to"],
    }


def _close(observed: float, expected: float) -> bool:
    return bool(
        np.isclose(
            float(observed),
            float(expected),
            rtol=1e-10,
            atol=max(1e-9, abs(float(expected)) * 1e-10),
        )
    )


def run() -> dict[str, Any]:
    """Execute the complete Stage 9 acceptance gate and persist its evidence."""

    from src.transform.stage9 import load_record_tables

    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, observed: Any, expected: Any) -> None:
        checks.append(
            {
                "check_name": name,
                "passed": bool(passed),
                "observed": json.dumps(observed, ensure_ascii=False, default=str),
                "expected": json.dumps(expected, ensure_ascii=False, default=str),
            }
        )

    contracts = load_contracts()
    silver_contracts = load_silver_contracts()
    gold_counts = validate_all_gold(max_stage=9)
    gold_relationships = validate_relationships(max_stage=9)
    silver_counts = validate_all_silver()
    silver_relationships = validate_silver_relationships()
    required_new_tables = {
        "dim_source",
        "dim_source_artifact",
        "bridge_record_lineage",
        "dim_source_priority",
        "dim_airport_group",
        "fact_airport_group_traffic",
    }
    add(
        "contracts_stage9",
        contracts.get("version") == "stage9_v1.0.0"
        and silver_contracts.get("version") == "stage9_v1.0.0"
        and len(gold_counts) == 31
        and len(silver_counts) == 28
        and required_new_tables <= set(gold_counts),
        {
            "gold_version": contracts.get("version"),
            "silver_version": silver_contracts.get("version"),
            "gold_tables": len(gold_counts),
            "silver_tables": len(silver_counts),
            "new_tables": sorted(required_new_tables & set(gold_counts)),
        },
        {
            "gold_version": "stage9_v1.0.0",
            "silver_version": "stage9_v1.0.0",
            "gold_tables": 31,
            "silver_tables": 28,
            "new_tables": sorted(required_new_tables),
        },
    )
    all_relationships = {**gold_relationships, **silver_relationships}
    add(
        "foreign_keys_zero_orphans",
        bool(all_relationships) and all(value == 0 for value in all_relationships.values()),
        all_relationships,
        "all declared relationships equal zero orphan keys",
    )

    sources = pd.read_parquet(PATHS.gold / "dim_source.parquet")
    artifacts = pd.read_parquet(PATHS.gold / "dim_source_artifact.parquet")
    fresh_sources = validate_table("dim_source", build_dim_source())
    fresh_artifacts = validate_table(
        "dim_source_artifact", build_dim_source_artifact(verify_files=True)
    )
    statuses = _source_statuses(sources, artifacts)
    add(
        "source_catalog_and_manifest",
        len(sources) == 23
        and len(artifacts) == 752
        and _frames_equal(sources, fresh_sources)
        and _frames_equal(artifacts, fresh_artifacts)
        and len(statuses) == len(sources)
        and all(item["status"] in {"available", "not_available", "not_applicable"} for item in statuses),
        {
            "sources": len(sources),
            "artifacts": len(artifacts),
            "statuses": statuses,
        },
        {
            "sources": 23,
            "artifacts": 752,
            "catalog_and_manifest_exact": True,
            "every_source_has_explicit_status": True,
        },
    )

    tables = load_record_tables(contracts=contracts)
    bridge = pd.read_parquet(PATHS.gold / "bridge_record_lineage.parquet")
    lineage = validate_lineage_frames(
        tables=tables,
        artifacts=artifacts,
        bridge=bridge,
        contracts=contracts,
    )
    dashboard_record_tables = {
        "fact_carrier_metrics",
        "fact_route_traffic_summary",
        "fact_dashboard_coverage",
        "fact_forecasts",
        "fact_anomalies",
        "fact_report_language",
        "fact_study_results",
        "fact_spread_decomposition",
    }
    add(
        "record_lineage_complete",
        lineage["coverage_pct"] == 1.0
        and lineage["unknown_parent_records"] == 0
        and lineage["unknown_artifact_records"] == 0
        and dashboard_record_tables <= set(lineage["record_tables"]),
        lineage,
        {
            "coverage_pct": 1.0,
            "unknown_parent_records": 0,
            "unknown_artifact_records": 0,
            "dashboard_tables": sorted(dashboard_record_tables),
        },
    )

    issues = pd.read_parquet(PATHS.gold / "fact_data_quality_issues.parquet")
    operational_rows = len(read_operational_issues(REFERENCE_OPERATIONAL_LEDGER))
    origin_counts = issues.groupby("issue_origin").size().to_dict()
    stage6_build = json.loads(
        (PATHS.quality / "stage6_build.json").read_text(encoding="utf-8")
    )
    reconciliation = stage6_build["quality_reconciliation"]
    resolved_consistent = issues["status"].eq("resolved").eq(
        issues["resolved"].fillna(False).astype(bool)
    ).all()
    resolution_dates_consistent = issues.loc[
        issues["status"].ne("resolved"), "resolved_at"
    ].isna().all()
    add(
        "quality_ledger_reconciled",
        operational_rows == 264
        and origin_counts.get("operational_ledger") == 264
        and origin_counts.get("derived_reconciliation") == 23
        and len(issues) == 287
        and issues["issue_signature"].notna().all()
        and issues["issue_signature"].is_unique
        and resolved_consistent
        and resolution_dates_consistent
        and reconciliation
        == {
            "operational_baseline_rows": 264,
            "operational_run_rows": 235,
            "operational_raw_input_rows": 499,
            "operational_input_rows": 264,
            "operational_duplicate_rows": 235,
            "derived_input_rows": 23,
            "combined_raw_input_rows": 522,
            "combined_input_rows": 287,
            "canonical_rows": 287,
            "deduplicated_rows": 235,
        },
        {
            "operational_file_rows": operational_rows,
            "origin_counts": origin_counts,
            "canonical_rows": len(issues),
            "reconciliation": reconciliation,
            "open_rows": int(issues["status"].eq("open").sum()),
        },
        {
            "operational": 264,
            "derived": 23,
            "canonical": 287,
            "raw_operational": 499,
            "deduplicated": 235,
            "unique_signatures": True,
        },
    )

    dim_airport = pd.read_parquet(PATHS.gold / "dim_airport.parquet")
    dim_airport_group = pd.read_parquet(PATHS.gold / "dim_airport_group.parquet")
    airport_fact = pd.read_parquet(PATHS.gold / "fact_airport_traffic.parquet")
    group_fact = pd.read_parquet(PATHS.gold / "fact_airport_group_traffic.parquet")
    silver_airports = pd.read_parquet(PATHS.silver / "airport_traffic.parquet")
    silver_groups = silver_airports[silver_airports["is_group_total"].fillna(False)].copy()
    silver_groups["airport_group_key"] = silver_groups["airport_iata"].str.replace(
        "ALL_", "", regex=False
    )
    comparison_columns = [
        "airport_group_key",
        "period_id",
        "source_system",
        "passengers_domestic",
        "passengers_international",
        "passengers_total",
        "cargo_tons",
        "operations",
    ]
    silver_compare = silver_groups[comparison_columns].sort_values(
        comparison_columns[:3]
    ).reset_index(drop=True)
    gold_compare = group_fact[comparison_columns].sort_values(
        comparison_columns[:3]
    ).reset_index(drop=True)
    group_parity = len(silver_compare) == len(gold_compare)
    if group_parity:
        group_parity = silver_compare[comparison_columns[:3]].equals(
            gold_compare[comparison_columns[:3]]
        ) and all(
            np.allclose(
                pd.to_numeric(silver_compare[column], errors="coerce"),
                pd.to_numeric(gold_compare[column], errors="coerce"),
                equal_nan=True,
            )
            for column in comparison_columns[3:]
        )
    forbidden_airports = {"ALL_OMA", "ALL_GAP", "ALL_ASUR"}
    add(
        "airport_group_separation",
        set(dim_airport_group["airport_group_key"]) == {"OMA", "GAP", "ASUR"}
        and len(group_fact) == 47
        and not (set(dim_airport["airport_iata"].dropna()) & forbidden_airports)
        and not (set(airport_fact["airport_iata"].dropna()) & forbidden_airports)
        and group_parity,
        {
            "groups": sorted(dim_airport_group["airport_group_key"].tolist()),
            "group_rows": len(group_fact),
            "silver_group_rows": len(silver_groups),
            "forbidden_in_dim": sorted(set(dim_airport["airport_iata"].dropna()) & forbidden_airports),
            "forbidden_in_fact": sorted(set(airport_fact["airport_iata"].dropna()) & forbidden_airports),
            "silver_gold_parity": group_parity,
        },
        {"groups": ["ASUR", "GAP", "OMA"], "group_rows": 47, "silver_gold_parity": True},
    )

    priority = pd.read_parquet(PATHS.gold / "dim_source_priority.parquet")
    priority_exact = _frames_equal(priority, build_dim_source_priority())
    connection = duckdb.connect(str(PATHS.warehouse), read_only=True)
    try:
        consolidated = connection.execute("SELECT * FROM v_carrier_consolidated").fetchdf()
        sql_default = connection.execute("SELECT * FROM v_carrier_default").fetchdf()
        quarters = connection.execute(
            "SELECT * FROM v_aeromexico_quarterly "
            "WHERE period_id IN ('2026Q1', '2026Q2') ORDER BY period_id"
        ).fetchdf()
        casm_ex = connection.execute(
            "SELECT period_id, value FROM v_carrier_default "
            "WHERE carrier_key='AEROMEXICO' AND segment='total' "
            "AND metric_key='casm_ex_fuel' AND period_id IN ('2026Q1','2026Q2') "
            "ORDER BY period_id"
        ).fetchdf()
        health = connection.execute("SELECT * FROM v_data_health").fetchdf()
        freshness = connection.execute(
            "SELECT * FROM v_dashboard_source_freshness"
        ).fetchdf()
    finally:
        connection.close()
    grain = ["carrier_key", "period_id", "metric_key", "segment"]
    python_default = select_preferred_sources(consolidated, grain)
    compare_columns = [*grain, "source_system", "source_file", "value", "ingested_at"]
    python_compare = python_default[compare_columns].sort_values(grain).reset_index(drop=True)
    sql_compare = sql_default[compare_columns].sort_values(grain).reset_index(drop=True)
    precedence_parity = len(python_compare) == len(sql_compare)
    if precedence_parity:
        precedence_parity = python_compare.drop(columns="value").equals(
            sql_compare.drop(columns="value")
        ) and np.allclose(
            python_compare["value"], sql_compare["value"], equal_nan=True
        )
    add(
        "source_precedence_python_sql_parity",
        priority_exact and precedence_parity,
        {
            "priority_rows": len(priority),
            "default_rows": int(priority["is_default"].sum()),
            "compared_rows": len(sql_compare),
            "catalog_exact": priority_exact,
            "python_sql_equal": precedence_parity,
        },
        {
            "catalog_exact": True,
            "python_sql_equal": True,
            "one_default_per_domain": True,
        },
    )

    metrics = pd.read_parquet(PATHS.gold / "dim_metric.parquet")
    allowed_methods = {"sum", "weighted", "latest", "non_additive"}
    method_matches = all(
        str(row.consolidation_method) == consolidation_method(str(row.metric_key))
        for row in metrics.itertuples(index=False)
    )
    ratio_tokens = (
        "margin",
        "factor",
        "growth",
        "rask",
        "cask",
        "trasm",
        "prasm",
        "yield",
        "per_",
        "break_even",
        "concentration",
        "volatility",
    )
    explicit_share_ratios = {
        "ancillary_share",
        "fuel_cost_share",
        "market_share_domestic_mx",
    }
    additive_ratios = metrics[
        metrics["metric_key"].astype(str).map(
            lambda key: key in explicit_share_ratios
            or any(token in key for token in ratio_tokens)
        )
        & metrics["consolidation_method"].eq("sum")
    ]["metric_key"].tolist()
    add(
        "consolidation_rules_safe",
        metrics["consolidation_method"].notna().all()
        and set(metrics["consolidation_method"]) <= allowed_methods
        and method_matches
        and not additive_ratios
        and not metrics["consolidation_method"].eq("weighted").any(),
        {
            "methods": metrics.groupby("consolidation_method").size().to_dict(),
            "python_catalog_match": method_matches,
            "additive_ratio_metrics": additive_ratios,
        },
        {
            "allowed": sorted(allowed_methods),
            "all_metrics_declared": True,
            "additive_ratio_metrics": [],
            "weighted_without_declared_weight": 0,
        },
    )

    carrier = pd.read_parquet(PATHS.gold / "fact_carrier_metrics.parquet")
    source_history = carrier[
        carrier["source_system"].isin(["sec_edgar", "afac", "bmv_xbrl"])
    ]
    fixture_evidence = _scd2_fixture_evidence()
    actual_scd2 = {
        source: {
            "rows": int(len(group)),
            "versions_after_baseline": int(group["restatement_count"].gt(0).sum()),
            "current_rows": int(group["is_current"].sum()),
        }
        for source, group in source_history.groupby("source_system")
    }
    add(
        "scd2_homogeneous_and_value_driven",
        set(actual_scd2) == {"sec_edgar", "afac", "bmv_xbrl"}
        and fixture_evidence["versions"] == 2
        and fixture_evidence["values"] == [1.0, 2.0]
        and fixture_evidence["restatement_count"] == [0, 1]
        and fixture_evidence["is_current"] == [False, True],
        {"materialized": actual_scd2, "frozen_fixture": fixture_evidence},
        {
            "sources": ["afac", "bmv_xbrl", "sec_edgar"],
            "unchanged_observation_collapsed": True,
            "changed_value_increments_count": True,
        },
    )

    quarter_by_id = quarters.set_index("period_id")
    casm_by_id = casm_ex.set_index("period_id")["value"]
    expected_anchors = {
        "2026Q1": {
            "total_revenue": 1_341_000_000.0,
            "adjusted_ebitdar": 335_800_000.0,
            "ebitdar_margin": 0.250,
            "operating_income": 141_800_000.0,
            "operating_margin": 0.106,
            "passengers": 5_791_000.0,
            "load_factor_reported": 0.844,
            "trasm_cents_per_mile": 15.6,
            "fleet_size": 166.0,
            "casm_ex_fuel": 10.2,
        },
        "2026Q2": {
            "total_revenue": 1_479_000_000.0,
            "adjusted_ebitdar": 264_200_000.0,
            "ebitdar_margin": 0.179,
            "operating_income": 67_900_000.0,
            "operating_margin": 0.046,
            "passengers": 6_014_000.0,
            "load_factor_reported": 0.849,
            "trasm_cents_per_mile": 16.0,
            "fleet_size": 169.0,
            "unit_margin_cents_per_km": 0.43495983456613274,
            "casm_ex_fuel": 10.0,
        },
    }
    observed_anchors: dict[str, dict[str, float]] = {}
    anchors_pass = set(quarter_by_id.index) == set(expected_anchors)
    for period_id, expected in expected_anchors.items():
        observed_anchors[period_id] = {}
        for metric_key, expected_value in expected.items():
            observed_value = (
                float(casm_by_id.loc[period_id])
                if metric_key == "casm_ex_fuel"
                else float(quarter_by_id.loc[period_id, metric_key])
            )
            observed_anchors[period_id][metric_key] = observed_value
            anchors_pass = anchors_pass and _close(observed_value, expected_value)
    afac_june = carrier[
        carrier["is_current"]
        & carrier["period_id"].eq("2026M06")
        & carrier["metric_key"].eq("passengers_afac")
        & carrier["segment"].eq("total")
        & carrier["carrier_key"].isin(["AEROMEXICO", "AEROMEXICO_CONNECT"])
    ].set_index("carrier_key")["value"]
    afac_values = {
        "AEROMEXICO": float(afac_june.loc["AEROMEXICO"]),
        "AEROMEXICO_CONNECT": float(afac_june.loc["AEROMEXICO_CONNECT"]),
    }
    afac_values["GROUP_TOTAL"] = sum(afac_values.values())
    anchors_pass = anchors_pass and afac_values == {
        "AEROMEXICO": 1_481_477.0,
        "AEROMEXICO_CONNECT": 339_718.0,
        "GROUP_TOTAL": 1_821_195.0,
    }
    add(
        "business_anchors_unchanged",
        anchors_pass,
        {"quarters": observed_anchors, "afac_2026M06": afac_values},
        {"quarters": expected_anchors, "afac_2026M06": {"AEROMEXICO": 1_481_477.0, "AEROMEXICO_CONNECT": 339_718.0, "GROUP_TOTAL": 1_821_195.0}},
    )

    expected_domains = {
        "carrier_metrics",
        "routes_bts",
        "airports",
        "airport_groups",
        "market",
        "macro",
        "analytics",
    }
    expected_health_datasets = {
        "fact_carrier_metrics",
        "fact_route_traffic",
        "fact_airport_traffic",
        "fact_airport_group_traffic",
        "fact_market_data",
        "fact_macro",
        "fact_forecasts",
        "dim_model_performance",
        "fact_report_language",
        "fact_anomalies",
        "dim_cluster_assignments",
        "fact_study_results",
        "fact_route_traffic_summary",
        "fact_spread_decomposition",
        "fact_dashboard_coverage",
    }
    health_fields = {
        "dataset_name",
        "data_domain",
        "source_system",
        "rows",
        "last_ingested_at",
        "issue_count",
    }
    add(
        "data_health_complete",
        expected_domains == set(health["data_domain"])
        and expected_health_datasets == set(health["dataset_name"])
        and health["rows"].gt(0).all()
        and health_fields <= set(health.columns)
        and {"dataset_name", "data_domain", "source_system"} <= set(freshness.columns)
        and expected_health_datasets <= set(freshness["dataset_name"]),
        {
            "domains": sorted(health["data_domain"].unique()),
            "datasets": sorted(health["dataset_name"].unique()),
            "health_rows": len(health),
            "freshness_rows": len(freshness),
        },
        {
            "domains": sorted(expected_domains),
            "datasets": sorted(expected_health_datasets),
            "all_rows_positive": True,
        },
    )

    validate_registry()
    resolved_steps = _resolve_registry_callables()
    phase_counts = Counter(step.phase.value for step in PIPELINE_STEPS)
    expected_phase_counts = {
        "ingest": 13,
        "parse": 7,
        "transform": 6,
        "analytics": 2,
        "dashboard": 4,
    }
    add(
        "central_registry_complete",
        len(PIPELINE_STEPS) == 32
        and len(resolved_steps) == 32
        and dict(phase_counts) == expected_phase_counts
        and PIPELINE_STEPS[-2].step_id == "dashboard.materialize_stage9"
        and PIPELINE_STEPS[-1].step_id == "dashboard.validate_stage9",
        {
            "steps": len(PIPELINE_STEPS),
            "resolved": len(resolved_steps),
            "phases": dict(phase_counts),
            "last_steps": [step.step_id for step in PIPELINE_STEPS[-2:]],
        },
        {"steps": 32, "phases": expected_phase_counts, "all_callables_importable": True},
    )

    checks_frame = pd.DataFrame(checks)
    all_passed = bool(checks_frame["passed"].all())
    result = {
        "parser_version": "stage9_v1.0.0",
        "status": "passed" if all_passed else "failed",
        "passed": int(checks_frame["passed"].sum()),
        "total": len(checks_frame),
        "all_passed": all_passed,
        "failed": checks_frame.loc[~checks_frame["passed"], "check_name"].tolist(),
        "checks": checks,
        "gold_contract_counts": gold_counts,
        "silver_contract_counts": silver_counts,
        "relationships": all_relationships,
        "source_statuses": statuses,
        "lineage": lineage,
        "quality_reconciliation": reconciliation,
        "anchors": {"quarters": observed_anchors, "afac_2026M06": afac_values},
        "health": {
            "domains": sorted(health["data_domain"].unique()),
            "datasets": sorted(health["dataset_name"].unique()),
        },
        "registry": {
            "steps": len(PIPELINE_STEPS),
            "phases": dict(phase_counts),
        },
    }
    output = PATHS.quality / "stage9_acceptance.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(checks_frame, PATHS.quality / "stage9_acceptance_checks.parquet")
    output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    if not all_passed:
        failures = checks_frame.loc[~checks_frame["passed"]].to_dict("records")
        raise AssertionError(f"Stage 9 acceptance failed: {failures}")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, ensure_ascii=False, default=str))
