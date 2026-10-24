"""Explicit source Gold observations, native parents and physical Stage 9 lineage."""

from __future__ import annotations

import json
from decimal import Decimal

import pandas as pd

from src.source_updates import afac_carrier_source, volaris_sec_source
from src.source_updates.carrier_source_contract import (
    FIELDS,
    GRAIN,
    NATIVE,
    TABLES,
    clean,
    identifier,
    validate,
)
from src.source_updates.catalog import ROOT
from src.transform.stage6_contracts import validate_table
from src.transform.stage9_lineage import LineageSpec, build_bridge_record_lineage, build_dim_source_artifact
from src.transform.validate_stage9 import validate_lineage_frames

MODULES = {"volaris_sec": volaris_sec_source, "afac_carriers": afac_carrier_source}


def projection(native, product):
    MODULES[product].validate(native)
    validate(native, product)
    selected = MODULES[product].project(native)
    rows = []
    for raw in selected.to_dict("records"):
        r = clean({k: raw[k] for k in FIELDS})
        parents = raw.get("_parent_ids", [raw["record_id"]])
        r.update(
            value=float(Decimal(str(r["value"])) * Decimal(str(r["scale"]))),
            source_unit=r["unit"],
            unit="fraction" if r["unit"] == "percent" else r["unit"],
            native_parent_record_ids=json.dumps(sorted(parents)),
            normalization="verified_PDF_month_value_with_database_support"
            if product == "afac_carriers" and r["service_type"] == "scheduled"
            else "reported_value_times_explicit_scale",
        )
        r["record_id"] = identifier(r, gold=True)
        rows.append(r)
    facts = pd.DataFrame(rows).sort_values("record_id").reset_index(drop=True)
    validate(facts, product, gold=True)
    # This is a source-observation table, never the production fact_carrier_metrics.
    if facts.duplicated(
        ["statement", "period_id", "metric_key", "entity_as_reported", "segment", "service_type"]
    ).any():
        raise ValueError("Carrier Gold has duplicate semantic observations")
    return facts


def verify_projection(native, facts, product):
    validate(facts, product, gold=True)
    expected = projection(native, product)
    try:
        pd.testing.assert_frame_equal(facts, expected, check_exact=True)
    except AssertionError as exc:
        raise ValueError("Carrier Gold values, units, selection or complete native ancestry differ") from exc


def frames(workspace, product, period, native, details):
    if product not in MODULES or set(native.edition) != {period}:
        raise ValueError("Carrier source product/edition mismatch")
    native = native.copy()
    expected = native.apply(lambda r: identifier(r), axis=1)
    if "record_id" in native and not native.record_id.equals(expected):
        raise ValueError("Native carrier source IDs differ from physical grain")
    native["record_id"] = expected
    MODULES[product].validate(native)
    validate(native, product)
    facts = projection(native, product)
    artifacts = validate_table(
        "dim_source_artifact",
        build_dim_source_artifact(
            workspace / "data/bronze/_manifest.jsonl",
            catalog_path=ROOT / "config/source_catalog.yaml",
            verify_files=True,
        ),
    )
    expected_artifacts = 4 if product == "volaris_sec" else 2
    if len(artifacts) != expected_artifacts:
        raise ValueError("Carrier source dossier physical artifact inventory differs")
    by_file = artifacts.set_index("source_file").artifact_id.to_dict()
    hashes = artifacts.set_index("source_file").artifact_sha256.to_dict()
    if any(hashes.get(r.source_file) != r.source_hash for r in native.itertuples(index=False)):
        raise ValueError("Carrier native source does not match its physical artifact")
    specs = []
    for r in native.itertuples(index=False):
        specs.append(
            LineageSpec(
                record_id=r.record_id,
                table_name=NATIVE[product],
                lineage_type="direct_artifact",
                artifact_ids=(by_file[r.source_file],),
                lineage_note="Exact retained source cell/token. Source dates, literal entity, reported "
                "units and unknown/dash status preserved. No new capture or approval.",
            )
        )
    indexed = native.set_index("record_id")
    for r in facts.itertuples(index=False):
        parents = json.loads(r.native_parent_record_ids)
        if not set(parents) <= set(indexed.index):
            raise ValueError("Carrier Gold has an unknown native parent")
        parent_files = set(indexed.loc[parents].source_file)
        ids = (
            tuple(by_file.values())
            if product == "volaris_sec"
            else tuple(sorted(by_file[f] for f in parent_files))
        )
        specs.append(
            LineageSpec(
                record_id=r.record_id,
                table_name=TABLES[product],
                lineage_type="derived",
                artifact_ids=ids,
                parent_record_ids=tuple(parents),
                lineage_note="Exact native parent(s), explicit scale only; AFAC PDF month values "
                "have matching database support when present. SEC index/submissions/6-K "
                "support filing identity. No quarter from YTD, booked/transported or "
                "operator/group substitution. No publication approval.",
            )
        )
    bridge = validate_table("bridge_record_lineage", build_bridge_record_lineage(specs, artifacts))
    lineage = validate_lineage_frames(
        tables={NATIVE[product]: native, TABLES[product]: facts},
        artifacts=artifacts,
        bridge=bridge,
        contracts={"tables": {name: {"grain": GRAIN} for name in [NATIVE[product], TABLES[product]]}},
    )
    return {
        f"silver/{NATIVE[product]}": native.reset_index(drop=True),
        f"gold/{TABLES[product]}": facts,
        "gold/dim_source_artifact": artifacts,
        "gold/bridge_record_lineage": bridge,
    }, {
        **details,
        "lineage": lineage,
        "native_rows": len(native),
        "gold_rows": len(facts),
        "source_observations_not_production_carrier_fact": True,
        "unresolved_native_values_not_projected": int(native.value.isna().sum()),
        "agent_eligible": False,
    }
