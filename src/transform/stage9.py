"""Materialize the Stage 9 source catalog and record-level lineage bridge.

The bridge is deliberately conservative.  A Gold record is linked to a
Bronze artifact only when the relationship is demonstrated by an immutable
source hash (or by the exact aggregation rule used by the transform).  When a
derived or curated record cannot be resolved at record level, the bridge keeps
an explicit declaration instead of inventing a file link.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

import pandas as pd

from src.config import PATHS
from src.ingest.stage4_common import write_parquet_atomic
from src.transform.generate_data_dictionary import generate as generate_dictionary
from src.transform.stage6_contracts import (
    load_contracts,
    validate_all_gold,
    validate_table,
)
from src.transform.stage6_warehouse import build_warehouse
from src.transform.stage9_lineage import (
    LineageSpec,
    build_bridge_record_lineage,
    build_dim_source,
    build_dim_source_artifact,
    build_dim_source_priority,
    load_source_catalog,
)


LINEAGE_TABLES = {
    "dim_source",
    "dim_source_artifact",
    "dim_source_priority",
    "bridge_record_lineage",
}
ANALYTICAL_TABLES = {
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
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _stable_hash(values: Iterable[Any]) -> str:
    """Reproduce the Stage 6 aggregate-source fingerprint exactly."""

    payload = "|".join(sorted({str(value) for value in values if pd.notna(value)}))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stable_hash_sequence(values: Iterable[Any]) -> str:
    """Hash a sorted contributor sequence when the transform preserves repeats."""

    payload = "|".join(sorted(str(value) for value in values if pd.notna(value)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record_table_names(contracts: Mapping[str, Any] | None = None) -> list[str]:
    """Return every fact/analytical table whose contract declares record_id."""

    catalog = contracts or load_contracts()
    return sorted(
        table_name
        for table_name, definition in catalog["tables"].items()
        if table_name not in LINEAGE_TABLES
        and "record_id" in definition.get("columns", {})
    )


def load_record_tables(
    *, gold_dir: Path = PATHS.gold, contracts: Mapping[str, Any] | None = None
) -> dict[str, pd.DataFrame]:
    """Load every declared record-bearing Gold table, failing on omissions."""

    tables: dict[str, pd.DataFrame] = {}
    for table_name in record_table_names(contracts):
        path = gold_dir / f"{table_name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"Record-bearing Gold table is missing: {path}")
        frame = pd.read_parquet(path)
        if "record_id" not in frame:
            raise ValueError(
                f"{table_name} has no record_id; rebuild it through the Stage 9 contracts"
            )
        tables[table_name] = frame
    return tables


def _artifact_maps(
    artifacts: pd.DataFrame,
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
    by_hash: dict[str, list[str]] = defaultdict(list)
    by_file: dict[str, list[str]] = defaultdict(list)
    for row in artifacts.itertuples(index=False):
        by_hash[str(row.artifact_sha256)].append(str(row.artifact_id))
        by_file[str(row.source_file)].append(str(row.artifact_id))
    return (
        {key: tuple(sorted(values)) for key, values in by_hash.items()},
        {key: tuple(sorted(values)) for key, values in by_file.items()},
    )


def _aggregate_artifact_map(
    artifacts: pd.DataFrame, *, silver_dir: Path = PATHS.silver
) -> dict[str, tuple[str, ...]]:
    """Resolve the aggregate hashes that are provable from Silver lineage.

    Most grouped Gold records contain one distinct Bronze digest; AFAC is the
    intentional exception because scheduled and charter inputs can both
    contribute to one carrier/month/market result.
    """

    by_hash, _ = _artifact_maps(artifacts)
    resolved: dict[str, tuple[str, ...]] = dict(by_hash)
    for digest, artifact_ids in by_hash.items():
        resolved[_stable_hash([digest])] = artifact_ids

    afac_path = silver_dir / "afac_monthly_stats.parquet"
    if afac_path.is_file():
        afac = pd.read_parquet(afac_path)
        required = {"source_hash", "carrier_key", "period_id", "market"}
        if required.issubset(afac.columns):
            groupings = (
                ["carrier_key", "period_id", "market"],
                ["carrier_key", "period_id"],
                ["period_id", "market"],
                ["period_id"],
            )
            for grouping in groupings:
                for _, group in afac.groupby(grouping, dropna=False):
                    hashes = sorted(set(group["source_hash"].dropna().astype(str)))
                    artifact_ids = sorted(
                        {
                            artifact_id
                            for digest in hashes
                            for artifact_id in by_hash.get(digest, ())
                        }
                    )
                    if hashes and len(artifact_ids) == len(hashes):
                        fingerprint = _stable_hash(hashes)
                        resolved[fingerprint] = tuple(
                            sorted(set(resolved.get(fingerprint, ())) | set(artifact_ids))
                        )
    return resolved


def _scd2_attestation_artifacts(
    tables: Mapping[str, pd.DataFrame],
    artifacts: pd.DataFrame,
    *,
    silver_dir: Path,
) -> dict[str, tuple[str, ...]]:
    """Return every SEC or BMV artifact that attests a retained SCD2 state.

    ``build_scd2_history`` correctly collapses repeated observations whose
    value did not change.  That must not discard their documentary lineage:
    every later publication inside the version's validity window that reports
    the same state is retained here as an additional contributor.
    """

    gold = tables.get("fact_carrier_metrics")
    if gold is None or gold.empty:
        return {}
    silver_frames: list[pd.DataFrame] = []
    for name in (
        "sec_financials",
        "sec_operating_metrics",
        "peer_financials",
        "peer_operating_metrics",
    ):
        path = silver_dir / f"{name}.parquet"
        if not path.is_file():
            continue
        frame = pd.read_parquet(path)
        required = {
            "carrier_key",
            "period_id",
            "metric_key",
            "value_normalized",
            "unit_normalized",
            "source_system",
            "source_hash",
            "ingested_at",
        }
        if not required.issubset(frame.columns):
            continue
        frame = frame.copy()
        frame["segment"] = frame.get("segment", "total")
        frame["segment"] = frame["segment"].fillna("total")
        frame["is_preliminary"] = frame.get("is_preliminary", False)
        frame["attested_at"] = pd.to_datetime(
            frame["ingested_at"], utc=True
        ).dt.tz_convert(None)
        silver_frames.append(frame)
    bmv_path = silver_dir / "bmv_financials.parquet"
    if bmv_path.is_file():
        from src.transform.stage6_facts import _bmv_observations

        bmv = _bmv_observations(silver_dir=silver_dir).rename(
            columns={"value": "value_normalized"}
        )
        bmv["attested_at"] = pd.to_datetime(
            bmv["scd2_order_at"], errors="raise"
        )
        silver_frames.append(bmv)
    if not silver_frames:
        return {}

    source = pd.concat(silver_frames, ignore_index=True)
    base = gold[
        ~gold["is_derived"].fillna(False)
        & gold["source_system"].astype(str).isin(source["source_system"].astype(str).unique())
    ].copy()
    if base.empty:
        return {}
    base["_valid_from"] = pd.to_datetime(base["valid_from"], errors="coerce")
    base["_valid_to"] = pd.to_datetime(base["valid_to"], errors="coerce")
    keys = ["carrier_key", "period_id", "metric_key", "segment", "source_system"]
    candidates = base[
        [
            "record_id",
            *keys,
            "value",
            "unit_normalized",
            "is_preliminary",
            "_valid_from",
            "_valid_to",
        ]
    ].merge(
        source[
            [
                *keys,
                "value_normalized",
                "unit_normalized",
                "is_preliminary",
                "source_hash",
                "attested_at",
            ]
        ],
        on=keys,
        how="inner",
        suffixes=("_gold", "_silver"),
    )
    numeric_equal = pd.to_numeric(
        candidates["value"], errors="coerce"
    ).sub(
        pd.to_numeric(candidates["value_normalized"], errors="coerce")
    ).abs().le(1e-9)
    state_equal = (
        numeric_equal
        & candidates["unit_normalized_gold"].astype(str).eq(
            candidates["unit_normalized_silver"].astype(str)
        )
        & candidates["is_preliminary_gold"].fillna(False).eq(
            candidates["is_preliminary_silver"].fillna(False)
        )
    )
    within_version = candidates["attested_at"].ge(candidates["_valid_from"]) & (
        candidates["_valid_to"].isna()
        | candidates["attested_at"].le(candidates["_valid_to"])
    )
    candidates = candidates[state_equal & within_version]
    by_hash, _ = _artifact_maps(artifacts)
    output: dict[str, tuple[str, ...]] = {}
    for record_id, group in candidates.groupby("record_id"):
        output[str(record_id)] = tuple(
            sorted(
                {
                    artifact_id
                    for digest in group["source_hash"].dropna().astype(str)
                    for artifact_id in by_hash.get(digest, ())
                }
            )
        )
    return output


def _source_files(value: Any) -> tuple[str, ...]:
    if value is None or pd.isna(value):
        return ()
    text = str(value).strip()
    if not text:
        return ()
    return tuple(
        item.strip().replace("\\", "/")
        for item in re.split(r"\s*\|\s*", text)
        if item.strip()
    )


def _artifacts_for_row(
    row: pd.Series,
    *,
    aggregate_map: Mapping[str, tuple[str, ...]],
    by_file: Mapping[str, tuple[str, ...]],
) -> tuple[str, ...]:
    source_hash = row.get("source_hash")
    if pd.notna(source_hash):
        digest = str(source_hash).lower()
        if _SHA256.fullmatch(digest) and digest in aggregate_map:
            return aggregate_map[digest]
    files: list[str] = []
    for column in ("source_file", "source_files"):
        if column in row.index:
            files.extend(_source_files(row.get(column)))
    return tuple(
        sorted(
            {
                artifact_id
                for source_file in files
                for artifact_id in by_file.get(source_file, ())
            }
        )
    )


def _route_summary_parents(
    summaries: pd.DataFrame,
    routes: pd.DataFrame,
    dim_route: pd.DataFrame | None,
) -> dict[str, tuple[str, ...]]:
    if dim_route is None or not {
        "route_key",
        "market_key",
    }.issubset(dim_route.columns):
        return {}
    lookup = routes[["record_id", "carrier_key", "route_key", "period_id"]].merge(
        dim_route[["route_key", "market_key"]], on="route_key", how="inner"
    )
    parents = (
        lookup.groupby(["carrier_key", "market_key", "period_id"])["record_id"]
        .agg(lambda values: tuple(sorted(set(values.astype(str)))))
        .to_dict()
    )
    return {
        str(row.record_id): parents.get(
            (str(row.carrier_key), str(row.market_key), str(row.period_id)), ()
        )
        for row in summaries.itertuples(index=False)
    }


def _coverage_parents(
    coverage: pd.DataFrame, carrier_metrics: pd.DataFrame
) -> dict[str, tuple[str, ...]]:
    keys = ["carrier_key", "metric_key", "period_type", "segment"]
    grouped = (
        carrier_metrics.groupby(keys, dropna=False)["record_id"]
        .agg(lambda values: tuple(sorted(set(values.astype(str)))))
        .to_dict()
    )
    return {
        str(row.record_id): grouped.get(
            tuple(getattr(row, column) for column in keys), ()
        )
        for row in coverage.itertuples(index=False)
    }


def _forecast_parents(
    frame: pd.DataFrame, carrier_metrics: pd.DataFrame
) -> dict[str, tuple[str, ...]]:
    current = carrier_metrics[
        carrier_metrics.get("is_current", True).fillna(False)
        & carrier_metrics["segment"].eq("total")
    ].copy()
    output: dict[str, tuple[str, ...]] = {}
    for row in frame.itertuples(index=False):
        carrier = str(getattr(row, "carrier_key"))
        metric = str(getattr(row, "metric_key"))
        trained_through = str(getattr(row, "trained_through_period"))
        matches = current[
            current["carrier_key"].astype(str).eq(carrier)
            & current["metric_key"].astype(str).eq(metric)
            & current["period_id"].astype(str).le(trained_through)
        ]
        output[str(row.record_id)] = tuple(
            sorted(set(matches["record_id"].astype(str)))
        )
    return output


def _performance_parents(
    frame: pd.DataFrame, carrier_metrics: pd.DataFrame
) -> dict[str, tuple[str, ...]]:
    return _forecast_parents(frame, carrier_metrics)


def _carrier_derived_parents(
    carrier_metrics: pd.DataFrame,
) -> dict[str, tuple[str, ...]]:
    """Resolve exact metric parents for reproducible carrier derivations."""

    base = carrier_metrics[
        ~carrier_metrics["is_derived"].fillna(False)
        & carrier_metrics["is_current"].fillna(False)
        & carrier_metrics["value"].notna()
        & carrier_metrics["segment"].eq("total")
    ].copy()
    catalog = load_source_catalog()
    priority_rows = [
        row
        for row in catalog["priorities"]
        if row["data_domain"] == "carrier_metrics"
    ]
    explicit_priority = {
        str(row["source_system"]): int(row["priority"])
        for row in priority_rows
        if row["source_system"] != "*"
    }
    default_priority = next(
        int(row["priority"])
        for row in priority_rows
        if row["source_system"] == "*"
    )
    def preferred(frame: pd.DataFrame) -> dict[tuple[str, str, str], str]:
        ranked = frame.assign(
            _priority=frame["source_system"].map(explicit_priority).fillna(default_priority),
            _preliminary=frame["is_preliminary"].fillna(False),
            _confidence=pd.to_numeric(frame["confidence"], errors="coerce").fillna(0),
            _ingested=pd.to_datetime(frame["ingested_at"], errors="coerce"),
        )
        selected = ranked.sort_values(
            [
                "carrier_key",
                "period_id",
                "metric_key",
                "_priority",
                "_preliminary",
                "_confidence",
                "_ingested",
            ],
            ascending=[True, True, True, True, True, False, False],
            kind="stable",
        ).drop_duplicates(["carrier_key", "period_id", "metric_key"], keep="first")
        return {
            (str(row.carrier_key), str(row.period_id), str(row.metric_key)): str(row.record_id)
            for row in selected.itertuples(index=False)
        }

    preferred_base = preferred(base)
    current_total = carrier_metrics[
        carrier_metrics["is_current"].fillna(False)
        & carrier_metrics["value"].notna()
        & carrier_metrics["segment"].eq("total")
    ]
    preferred_all = preferred(current_total)
    derived = carrier_metrics[carrier_metrics["is_derived"].fillna(False)]
    derived_by_key = {
        (str(row.carrier_key), str(row.period_id), str(row.metric_key)): str(row.record_id)
        for row in derived.itertuples(index=False)
        if str(row.source_system) == "derived_gold"
    }

    direct_dependencies: dict[str, tuple[str, ...]] = {
        "load_factor_derived": ("rpm_total", "asm_total"),
        "rask_derived": ("total_revenue", "asm_total"),
        "prask_derived": ("passenger_revenue", "asm_total"),
        "cask_derived": ("operating_expenses_total", "asm_total"),
        "cask_ex_fuel_derived": (
            "operating_expenses_total",
            "jet_fuel_expense",
            "asm_total",
        ),
        "yield_derived": ("passenger_revenue", "rpm_total"),
        "fuel_cost_share": ("jet_fuel_expense", "operating_expenses_total"),
        "revenue_per_passenger": ("total_revenue", "passengers"),
        "asm_per_aircraft": ("asm_total", "fleet_size"),
        "unit_margin": ("rask", "cask"),
        "pask": ("rask", "cask"),
        "sla_rask": ("rask", "average_stage_length"),
        "sla_cask": ("cask", "average_stage_length"),
    }

    def identifier(
        carrier: str, period: str, metric: str, *, allow_derived: bool = True
    ) -> str | None:
        key = (carrier, period, metric)
        if allow_derived and key in derived_by_key:
            return derived_by_key[key]
        return preferred_base.get(key) or preferred_all.get(key)

    def prior_quarter(period: str, lag: int) -> str | None:
        match = re.fullmatch(r"(\d{4})Q([1-4])", period)
        if not match:
            return None
        ordinal = int(match.group(1)) * 4 + int(match.group(2)) - 1 - lag
        return f"{ordinal // 4}Q{ordinal % 4 + 1}"

    output: dict[str, tuple[str, ...]] = {}
    for row in derived.itertuples(index=False):
        if str(row.source_system) != "derived_gold":
            continue
        carrier = str(row.carrier_key)
        period = str(row.period_id)
        metric = str(row.metric_key)
        parent_ids: list[str] = []

        growth = re.fullmatch(r"(qoq|yoy)_growth_(.+)", metric)
        ttm = re.fullmatch(r"ttm_(.+)", metric)
        if growth:
            input_metric = growth.group(2)
            lag = 1 if growth.group(1) == "qoq" else 4
            prior = prior_quarter(period, lag)
            for candidate_period in (period, prior):
                if candidate_period is not None:
                    parent = identifier(carrier, candidate_period, input_metric)
                    if parent:
                        parent_ids.append(parent)
        elif ttm:
            input_metric = ttm.group(1)
            for lag in range(4):
                candidate_period = prior_quarter(period, lag)
                if candidate_period is not None:
                    parent = identifier(carrier, candidate_period, input_metric)
                    if parent:
                        parent_ids.append(parent)
        else:
            dependencies = direct_dependencies.get(metric, ())
            if metric == "rask":
                dependencies = (
                    "trasm"
                    if identifier(carrier, period, "trasm", allow_derived=False)
                    else "rask_derived",
                )
            elif metric == "prask":
                dependencies = (
                    "prasm"
                    if identifier(carrier, period, "prasm", allow_derived=False)
                    else "prask_derived",
                )
            elif metric == "cask":
                dependencies = (
                    "casm"
                    if identifier(carrier, period, "casm", allow_derived=False)
                    else "cask_derived",
                )
            elif metric == "cask_ex_fuel":
                dependencies = (
                    "casm_ex_fuel"
                    if identifier(carrier, period, "casm_ex_fuel", allow_derived=False)
                    else "cask_ex_fuel_derived",
                )
            elif metric == "break_even_load_factor":
                yield_metric = (
                    "yield"
                    if identifier(carrier, period, "yield", allow_derived=False)
                    else "yield_derived"
                )
                dependencies = ("cask", yield_metric)
            for dependency in dependencies:
                parent = identifier(carrier, period, dependency)
                if parent:
                    parent_ids.append(parent)
        output[str(row.record_id)] = tuple(sorted(set(parent_ids)))

    # Seasonal passengers combine Aeromexico and Connect for the same month.
    seasonal_inputs = carrier_metrics[
        carrier_metrics["metric_key"].eq("passengers_afac")
        & carrier_metrics["segment"].eq("total")
        & carrier_metrics["carrier_key"].isin(["AEROMEXICO", "AEROMEXICO_CONNECT"])
        & carrier_metrics["is_current"].fillna(False)
    ]
    seasonal_by_period: dict[tuple[str, str], tuple[str, ...]] = {}
    for period, group in seasonal_inputs.groupby("period_id"):
        seasonal_by_period[(str(period), _stable_hash_sequence(group["source_hash"]))] = tuple(
            sorted(set(group["record_id"].astype(str)))
        )
    seasonal = derived[derived["metric_key"].eq("passengers_afac_sa")]
    for row in seasonal.itertuples(index=False):
        output[str(row.record_id)] = seasonal_by_period.get(
            (str(row.period_id), str(row.source_hash)), output.get(str(row.record_id), ())
        )
    return output


def _parent_maps(
    tables: Mapping[str, pd.DataFrame], *, dim_route: pd.DataFrame | None
) -> dict[str, dict[str, tuple[str, ...]]]:
    parents: dict[str, dict[str, tuple[str, ...]]] = {}
    carrier = tables.get("fact_carrier_metrics")
    if carrier is not None:
        parents["fact_carrier_metrics"] = _carrier_derived_parents(carrier)
        if "fact_dashboard_coverage" in tables:
            parents["fact_dashboard_coverage"] = _coverage_parents(
                tables["fact_dashboard_coverage"], carrier
            )
        if "fact_forecasts" in tables:
            parents["fact_forecasts"] = _forecast_parents(
                tables["fact_forecasts"], carrier
            )
        if "dim_model_performance" in tables:
            parents["dim_model_performance"] = _performance_parents(
                tables["dim_model_performance"], carrier
            )
    if "fact_route_traffic_summary" in tables and "fact_route_traffic" in tables:
        parents["fact_route_traffic_summary"] = _route_summary_parents(
            tables["fact_route_traffic_summary"],
            tables["fact_route_traffic"],
            dim_route,
        )
    return parents


def build_record_lineage_specs(
    tables: Mapping[str, pd.DataFrame],
    artifacts: pd.DataFrame,
    *,
    silver_dir: Path = PATHS.silver,
    dim_route: pd.DataFrame | None = None,
) -> list[LineageSpec]:
    """Build one complete, conservative lineage declaration per record."""

    aggregate_map = _aggregate_artifact_map(artifacts, silver_dir=silver_dir)
    raw_artifacts, by_file = _artifact_maps(artifacts)
    parent_maps = _parent_maps(tables, dim_route=dim_route)
    attestations = _scd2_attestation_artifacts(
        tables, artifacts, silver_dir=silver_dir
    )
    specs: list[LineageSpec] = []

    for table_name in sorted(tables):
        frame = tables[table_name]
        if "record_id" not in frame:
            raise ValueError(f"Record-bearing table has no record_id: {table_name}")
        if frame["record_id"].duplicated().any():
            raise ValueError(f"Duplicate record_id values in {table_name}")
        for _, row in frame.iterrows():
            record_id = str(row["record_id"])
            artifact_ids = _artifacts_for_row(
                row, aggregate_map=aggregate_map, by_file=by_file
            )
            artifact_ids = tuple(
                sorted(set(artifact_ids) | set(attestations.get(record_id, ())))
            )
            parent_ids = parent_maps.get(table_name, {}).get(record_id, ())
            is_derived = bool(row.get("is_derived", False)) or table_name in ANALYTICAL_TABLES
            source_hash = str(row.get("source_hash", "")).lower()
            source_files = {
                source_file
                for column in ("source_file", "source_files")
                if column in row.index
                for source_file in _source_files(row.get(column))
            }
            is_direct_artifact = source_hash in raw_artifacts or bool(
                source_files & set(by_file)
            )
            source_system = str(row.get("source_system", ""))
            # ``derived_gold`` hashes are transform fingerprints, not complete
            # documentary lineage.  Use the exact metric parents resolved
            # above, or an explicit declaration; never present a template
            # source hash as if it proved every formula input.
            if source_system == "derived_gold":
                artifact_ids = ()
            is_curated = source_system in {
                "peer_profile",
                "curated_primary_sources",
            }

            if artifact_ids and is_direct_artifact and not is_derived and not parent_ids:
                lineage_type = "direct_artifact"
                note = None
            elif artifact_ids or parent_ids:
                lineage_type = "curated" if is_curated else "derived"
                note = None
            else:
                lineage_type = "curated" if is_curated else "derived"
                note = (
                    "Registro curado sin artefacto público único; la ausencia de "
                    "enlace directo se conserva explícitamente."
                    if is_curated
                    else "Derivación reproducible sin correspondencia exacta a un "
                    "artefacto o registro padre en la metadata disponible."
                )
            specs.append(
                LineageSpec(
                    record_id=record_id,
                    table_name=table_name,
                    lineage_type=lineage_type,
                    artifact_ids=tuple(artifact_ids),
                    parent_record_ids=tuple(parent_ids),
                    lineage_note=note,
                )
            )
    return specs


def lineage_evidence(
    tables: Mapping[str, pd.DataFrame],
    artifacts: pd.DataFrame,
    bridge: pd.DataFrame,
) -> dict[str, Any]:
    """Summarize record coverage without treating declarations as artifacts."""

    rows: dict[str, dict[str, int]] = {}
    for table_name, frame in sorted(tables.items()):
        subset = bridge[bridge["table_name"].eq(table_name)]
        rows[table_name] = {
            "records": int(frame["record_id"].nunique()),
            "bridge_rows": int(len(subset)),
            "records_resolved_to_artifact": int(
                subset.loc[subset["artifact_id"].notna(), "record_id"].nunique()
            ),
            "records_resolved_to_parent": int(
                subset.loc[subset["parent_record_id"].notna(), "record_id"].nunique()
            ),
            "records_declared_without_artifact": int(
                subset.loc[
                    subset["lineage_status"].eq("declared_without_artifact"),
                    "record_id",
                ].nunique()
            ),
        }
    total_records = sum(item["records"] for item in rows.values())
    declared_records = int(bridge[["table_name", "record_id"]].drop_duplicates().shape[0])
    return {
        "catalog_sources": int(len(build_dim_source())),
        "bronze_artifacts": int(len(artifacts)),
        "record_tables": rows,
        "total_records": total_records,
        "records_with_lineage_declaration": declared_records,
        "coverage_pct": 1.0 if total_records == 0 else declared_records / total_records,
    }


def run(*, verify_bronze_files: bool = True) -> dict[str, Any]:
    """Build, validate and atomically publish the Stage 9 lineage metadata."""

    from src.transform.validate_stage9 import validate_lineage_frames

    contracts = load_contracts()
    dim_source = build_dim_source()
    dim_source_artifact = build_dim_source_artifact(
        verify_files=verify_bronze_files
    )
    tables = load_record_tables(contracts=contracts)
    dim_route_path = PATHS.gold / "dim_route.parquet"
    dim_route = pd.read_parquet(dim_route_path) if dim_route_path.is_file() else None
    specs = build_record_lineage_specs(
        tables,
        dim_source_artifact,
        dim_route=dim_route,
    )
    bridge = build_bridge_record_lineage(specs, dim_source_artifact)
    evidence = validate_lineage_frames(
        tables=tables,
        artifacts=dim_source_artifact,
        bridge=bridge,
        contracts=contracts,
    )

    outputs = {
        "dim_source": dim_source,
        "dim_source_artifact": dim_source_artifact,
        "bridge_record_lineage": bridge,
    }
    # Source priority is catalog metadata too.  Stage 6 may already have
    # materialized it for SQL; writing the same deterministic frame here keeps
    # a direct Stage 9 invocation complete.
    if "dim_source_priority" in contracts["tables"]:
        outputs["dim_source_priority"] = build_dim_source_priority()
    validated: dict[str, pd.DataFrame] = {}
    for table_name, frame in outputs.items():
        validated[table_name] = validate_table(table_name, frame)
    for table_name, frame in validated.items():
        write_parquet_atomic(frame, PATHS.gold / f"{table_name}.parquet")

    contract_counts = validate_all_gold(max_stage=9)
    views = build_warehouse(max_stage=9)
    dictionary = generate_dictionary()

    result = {
        "parser_version": "stage9_v1.0.0",
        **lineage_evidence(tables, dim_source_artifact, bridge),
        "validation": evidence,
        "contract_counts": contract_counts,
        "warehouse_views": views,
        "dictionary_bytes": len(dictionary.encode("utf-8")),
    }
    evidence_path = PATHS.quality / "stage9_lineage.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    evidence_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    return result


def main() -> int:
    print(json.dumps(run(), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
