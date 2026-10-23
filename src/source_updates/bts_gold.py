"""Monthly observed T-100 segments, standard Gold contracts and full native lineage."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.source_updates.bts_native import COUNTS, GRAIN
from src.source_updates.catalog import ROOT
from src.source_updates.h10_gold import period_frame
from src.transform.stage6_contracts import validate_table
from src.transform.stage6_facts import stable_hash
from src.transform.stage9_lineage import (
    LineageSpec,
    add_record_ids,
    build_bridge_record_lineage,
    build_dim_source_artifact,
)
from src.transform.validate_stage9 import validate_lineage_frames

FACT_GRAIN = ["carrier_key", "route_key", "period_id", "aircraft_type", "service_class"]
SUMS = [
    "departures_scheduled",
    "departures_performed",
    "seats",
    "passengers",
    "freight",
    "mail",
    "asm_miles",
    "rpm_miles",
]


def frames(workspace, product, period, native, details):
    if product != "bts_segments" or native.empty or native.duplicated(GRAIN).any():
        raise ValueError("BTS complete nonduplicate native grain required")
    native = add_record_ids(native.copy(), table_name="bts_t100_segment", natural_key_columns=GRAIN)
    selected = native.loc[native.period_id.eq(period)].copy()
    if selected.empty or selected.passengers.gt(selected.seats).any():
        raise ValueError("BTS selected-month native rows missing or contain invalid passenger/seat relation")
    if selected[COUNTS].isna().any().any() or selected[COUNTS].lt(0).any().any():
        raise ValueError("BTS selected month contains missing/negative native quantities")
    selected = selected.rename(columns={"class": "service_class"})
    rows, parents = [], {}
    for key, group in selected.groupby(FACT_GRAIN, sort=True, dropna=False):
        row = dict(zip(FACT_GRAIN, key, strict=True))
        for field in SUMS:
            total = sum(int(v) for v in group[field])
            if total > 2**53:
                raise ValueError("BTS aggregate exactness bound exceeded")
            row[field] = float(total)
        row["freight_kg"] = row.pop("freight") * 0.45359237
        row["mail_kg"] = row.pop("mail") * 0.45359237
        row["ask_km"] = row["asm_miles"] * 1.609344
        row["rpk_km"] = row["rpm_miles"] * 1.609344
        row["distance_miles"] = float(group.distance.median())
        row["distance_km"] = row["distance_miles"] * 1.609344
        row["load_factor"] = row["rpm_miles"] / row["asm_miles"] if row["asm_miles"] else np.nan
        row.update(
            calendar_period_id=period,
            fiscal_period_id=period,
            source_system="bts_t100",
            source_file="silver/bts_t100_segment.parquet",
            source_hash=stable_hash(sorted(group.source_hash.unique())),
            ingested_at=group.ingested_at.max().tz_convert(None).as_unit("ns"),
        )
        rows.append(row)
        parents[key] = tuple(sorted(group.record_id))
    facts = add_record_ids(
        pd.DataFrame(rows), table_name="fact_route_traffic", natural_key_columns=FACT_GRAIN
    )
    facts = validate_table("fact_route_traffic", facts)
    for column in SUMS:
        if column in {"freight", "mail"}:
            continue
        if sum(int(v) for v in facts[column]) != sum(int(v) for v in selected[column]):
            raise ValueError("BTS native/Gold aggregation does not reconcile")
    routes = []
    for route, group in selected.groupby("route_key", sort=True):
        if len(group[["origin", "dest", "origin_country", "dest_country"]].drop_duplicates()) != 1:
            raise ValueError("BTS directional route identity/country conflicts")
        first = group.iloc[0]
        distance = float(group.distance.median())
        routes.append(
            dict(
                route_key=route,
                origin_iata=first.origin,
                dest_iata=first.dest,
                origin_country=first.origin_country,
                dest_country=first.dest_country,
                distance_miles=distance,
                distance_km=distance * 1.609344,
                is_domestic_mx=False,
                is_transborder_us=True,
                is_international=True,
                market_key="-".join(sorted([first.origin, first.dest])),
            )
        )
    route_dimension = validate_table("dim_route", pd.DataFrame(routes))
    carrier_reference = validate_table("dim_carrier", pd.read_parquet(ROOT / "data/gold/dim_carrier.parquet"))
    carriers = (
        carrier_reference.loc[carrier_reference.carrier_key.isin(facts.carrier_key)]
        .sort_values("carrier_key")
        .reset_index(drop=True)
    )
    if set(facts.carrier_key) != set(carriers.carrier_key):
        raise ValueError("BTS carrier absent from approved carrier dimension reference")
    carriers["valid_to"] = carriers.valid_to.astype(object).where(carriers.valid_to.notna(), None)
    periods = period_frame(period)
    start, end = periods.iloc[0].period_start_date, periods.iloc[0].period_end_date
    if any(r.valid_from > start or pd.notna(r.valid_to) and r.valid_to < end for r in carriers.itertuples()):
        raise ValueError("BTS carrier reference validity does not cover projected month")
    if (
        not facts.route_key.isin(route_dimension.route_key).all()
        or not facts.period_id.isin(periods.period_id).all()
    ):
        raise ValueError("BTS orphan directional route/period")
    artifacts = validate_table(
        "dim_source_artifact",
        build_dim_source_artifact(
            workspace / "data/bronze/_manifest.jsonl",
            catalog_path=ROOT / "config/source_catalog.yaml",
            verify_files=True,
        ),
    )
    by_file = artifacts.set_index("source_file").artifact_id.to_dict()
    specs = [
        LineageSpec(
            record_id=r.record_id,
            table_name="bts_t100_segment",
            lineage_type="direct_artifact",
            artifact_ids=(by_file[r.source_file],),
            lineage_note=(
                "Native BTS row; CSV member and row locator preserved. "
                "All service codes literal; no coverage inference."
            ),
        )
        for r in native.itertuples(index=False)
    ]
    for r in facts.itertuples(index=False):
        key = tuple(getattr(r, c) for c in FACT_GRAIN)
        specs.append(
            LineageSpec(
                record_id=r.record_id,
                table_name="fact_route_traffic",
                lineage_type="derived",
                artifact_ids=tuple(sorted(by_file.values())),
                parent_record_ids=parents[key],
                lineage_note=(
                    "Sum of every selected-month native configuration/entity contributor; "
                    "distances median, ASM/RPM sum, pounds to kg and miles to km. "
                    "Carrier references fingerprinted in receipt. Observed MX/US operator segments only."
                ),
            )
        )
    bridge = validate_table("bridge_record_lineage", build_bridge_record_lineage(specs, artifacts))
    lineage = validate_lineage_frames(
        tables={"fact_route_traffic": facts, "bts_t100_segment": native},
        artifacts=artifacts,
        bridge=bridge,
        contracts={
            "tables": {"fact_route_traffic": {"grain": FACT_GRAIN}, "bts_t100_segment": {"grain": GRAIN}}
        },
    )
    evidence = {
        **details,
        "lineage": lineage,
        "gold_rows": len(facts),
        "gold_periods": sorted(facts.period_id.unique()),
        "native_rows_projected": len(selected),
        "native_rows_outside_projection": len(native) - len(selected),
        "native_sum_reconciliations": {c: sum(int(v) for v in selected[c]) for c in SUMS},
        "distance_aggregation": "native_unweighted_median_never_sum",
        "zero_capacity_load_factor": "null_not_zero",
        "identity_basis": "exact_six_fields_crosswalk_plus_approved_carrier_dimension",
        "latest_source_availability_verified": False,
        "complete_month_certified": False,
    }
    return {
        "silver/bts_t100_segment": native,
        "gold/fact_route_traffic": facts,
        "gold/dim_route": route_dimension,
        "gold/dim_carrier": carriers,
        "gold/dim_period": periods,
        "gold/dim_source_artifact": artifacts,
        "gold/bridge_record_lineage": bridge,
    }, evidence
