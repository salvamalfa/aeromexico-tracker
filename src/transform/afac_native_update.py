"""Append native AFAC fact versions without rebuilding historical finance.

Source capture time remains ingested_at. A method correction has its own
explicit effective time (valid_from), never a fabricated download timestamp.
"""

import json

import pandas as pd

from src.config import PATHS
from src.ingest.stage4_common import write_parquet_atomic
from src.parse.afac.market_scope import TOTAL_FORMULA, TOTAL_KEY
from src.transform.stage6_contracts import add_record_id, validate_table
from src.transform.stage6_dimensions import build_dim_carrier, build_dim_period
from src.transform.stage6_facts import _afac_rows

KEYS = ["carrier_key", "period_id", "metric_key", "segment", "source_system"]
DETAIL_FORMULA = "SUM(AFAC passengers) across service_type for carrier, period and market"


def semantic_formula(value):
    return " ".join(str(value or "").split())


def append_versions(baseline, candidates, effective_at):
    """Preserve closed records and non-AFAC rows; repeat input is a no-op."""
    effective = pd.to_datetime(effective_at, utc=True).tz_convert(None)
    if pd.isna(effective):
        raise ValueError("An explicit AFAC correction effective time is required")
    candidates = candidates[candidates["is_current"]].copy()
    if pd.to_datetime(candidates.ingested_at, utc=True).dt.tz_convert(None).gt(effective).any():
        raise ValueError("AFAC correction time cannot precede source capture")
    if candidates.duplicated(KEYS).any():
        raise ValueError("Duplicate native AFAC candidate grain")
    if not candidates.metric_key.eq("passengers_afac").all() or not candidates.source_system.eq("afac").all():
        raise ValueError("Native AFAC update cannot replace another metric or source")
    for row in candidates.itertuples():
        required = TOTAL_FORMULA if row.carrier_key == TOTAL_KEY else DETAIL_FORMULA
        if semantic_formula(row.derivation_formula) != required:
            raise ValueError("Native AFAC method must be a supported canonical formula")
    output = baseline.copy(deep=True)
    selected = output.metric_key.eq("passengers_afac") & output.source_system.eq("afac")
    scope = selected & output.period_id.isin(candidates.period_id) & output.is_current
    current = output[scope].set_index(KEYS)
    incoming = candidates.set_index(KEYS)
    if current.index.has_duplicates:
        raise ValueError("AFAC baseline has duplicate current versions")
    if set(current.index) - set(incoming.index):
        raise ValueError("Native AFAC edition would silently remove an existing carrier cell")
    added = []
    for key, row in incoming.iterrows():
        previous = current.loc[key] if key in current.index else None
        if previous is not None:
            if (
                previous.value == row.value
                and semantic_formula(previous.derivation_formula) == semantic_formula(row.derivation_formula)
                and bool(previous.is_preliminary) == bool(row.is_preliminary)
                and bool(previous.is_estimated) == bool(row.is_estimated)
            ):
                continue
            if effective <= pd.Timestamp(previous.valid_from) or effective < pd.Timestamp(row.ingested_at):
                raise ValueError("AFAC correction time must follow existing versions and source capture")
            mask = scope.copy()
            for field, value in zip(KEYS, key, strict=True):
                mask &= output[field].eq(value)
            output.loc[mask, "valid_to"] = effective - pd.Timedelta(microseconds=1)
            output.loc[mask, "is_current"] = False
        record = {**dict(zip(KEYS, key, strict=True)), **row.to_dict()}
        record.update(
            valid_from=effective,
            valid_to=pd.NaT,
            is_current=True,
            restatement_count=0 if previous is None else int(previous.restatement_count) + 1,
        )
        added.append(record)
    if not added:
        return output, 0
    fresh = add_record_id("fact_carrier_metrics", pd.DataFrame(added))
    return pd.concat([output, fresh[output.columns]], ignore_index=True), len(added)


def run():
    """Granular normal pipeline step; requires existing Gold and explicit as-of."""
    selection = json.loads((PATHS.data / "afac_native_update.json").read_bytes())
    if (
        set(selection) != {"schema_version", "effective_at"}
        or selection["schema_version"] != "afac_native_update_v1"
    ):
        raise ValueError("Unsupported AFAC native update binding")
    path = PATHS.gold / "fact_carrier_metrics.parquet"
    baseline = pd.read_parquet(path)
    candidates, exceptions = _afac_rows()
    latest = baseline.loc[selected_mask(baseline) & baseline.is_current, "period_id"].max()
    if candidates.period_id.max() < latest:
        raise ValueError("An older native AFAC edition cannot roll back the current dataset coverage")
    output, added = append_versions(baseline, candidates, selection["effective_at"])
    # Validate all results before writes. Preserve all existing dimension rows;
    # add only new source identities and periods required by this AFAC edition.
    writes = {}
    if added:
        writes["fact_carrier_metrics"] = validate_table("fact_carrier_metrics", output)
    for name, key, build in (
        ("dim_carrier", "carrier_key", build_dim_carrier),
        ("dim_period", "period_id", build_dim_period),
    ):
        existing = pd.read_parquet(PATHS.gold / f"{name}.parquet")
        fresh = build()
        fresh = fresh[~fresh[key].isin(existing[key])]
        if not fresh.empty:
            writes[name] = validate_table(
                name, pd.concat([existing, fresh[existing.columns]], ignore_index=True)
            )
    writes.update(provenance(baseline, output))
    for name, frame in writes.items():
        write_parquet_atomic(frame, PATHS.gold / f"{name}.parquet")
    write_parquet_atomic(exceptions, PATHS.quality / "stage6_entity_exceptions.parquet")
    return dict(
        network_used=False,
        added_versions=added,
        preserved_non_afac_records=int((~selected_mask(baseline)).sum()),
        gold_tables_written=sorted(writes),
        publication="not_authorized",
    )


def selected_mask(frame):
    return frame.metric_key.eq("passengers_afac") & frame.source_system.eq("afac")


def provenance(baseline, output):
    """Append documentary lineage for new AFAC records, retaining prior links."""
    from src.transform.stage9 import build_record_lineage_specs
    from src.transform.stage9_lineage import build_bridge_record_lineage, build_dim_source_artifact

    artifacts = pd.read_parquet(PATHS.gold / "dim_source_artifact.parquet")
    observed = build_dim_source_artifact(verify_files=True)
    fresh_artifacts = observed[~observed.artifact_id.isin(artifacts.artifact_id)]
    combined = pd.concat([artifacts, fresh_artifacts], ignore_index=True)
    fresh = output[~output.record_id.isin(baseline.record_id)]
    writes = {}
    if not fresh_artifacts.empty:
        writes["dim_source_artifact"] = validate_table("dim_source_artifact", combined)
    if not fresh.empty:
        specs = build_record_lineage_specs({"fact_carrier_metrics": fresh}, combined)
        links = build_bridge_record_lineage(specs, combined)
        if links.artifact_id.isna().any() or not links.has_direct_artifact.all():
            raise ValueError("Native AFAC versions require physical Bronze documentary lineage")
        previous = pd.read_parquet(PATHS.gold / "bridge_record_lineage.parquet")
        writes["bridge_record_lineage"] = validate_table(
            "bridge_record_lineage", pd.concat([previous, links], ignore_index=True)
        )
    return writes


def warehouse():
    from src.transform.stage6_warehouse import build_warehouse

    return {"views": build_warehouse(max_stage=9), "network_used": False}
