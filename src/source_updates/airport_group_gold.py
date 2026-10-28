"""Mexico-only standard airport facts, native precision and physical lineage."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.source_updates.airport_group_native import GRAIN
from src.source_updates.catalog import ROOT
from src.source_updates.h10_gold import period_frame
from src.transform.silver_contracts import validate_silver_table
from src.transform.stage6_contracts import validate_table
from src.transform.stage9_lineage import (
    LineageSpec,
    add_record_ids,
    build_bridge_record_lineage,
    build_dim_source_artifact,
)
from src.transform.validate_stage9 import validate_lineage_frames


def frames(workspace, product, period, native, details):
    validate_silver_table("airport_group_native", native)
    native = add_record_ids(native, table_name="airport_group_native", natural_key_columns=GRAIN)
    selected = native.loc[native.period_type.eq("month") & native.country.eq("MX")]
    rows = []
    for (p, entity), group in selected.groupby(["period_id", "entity_key"], sort=True):
        first = group.iloc[0]
        values = group.set_index("market").source_value
        factor = 1000 if first.unit == "thousand_passengers" else 1
        from decimal import Decimal

        counts = {m: int(Decimal(values[m]) * factor) for m in ["domestic", "international", "total"]}
        rows.append(
            dict(
                period_id=p,
                airport_iata="ALL_" + first.operator_group if entity == "MX" else entity,
                airport_name=first.airport_name,
                operator_group=first.operator_group,
                country="MX",
                is_group_total=entity == "MX",
                passengers_domestic=counts["domestic"],
                passengers_international=counts["international"],
                passengers_total=counts["total"],
                cargo_tons=np.nan,
                operations=None,
                source_system=first.source_system,
                source_file=first.source_file,
                source_hash=first.source_hash,
                ingested_at=first.ingested_at,
                parser_version=first.parser_version,
                source_precision_passengers=first.precision_passengers,
                value_status=first.value_status,
                is_preliminary=first.is_preliminary,
                source_definition=first.source_definition,
                rounding_error_bound_passengers=600
                if entity == "MX" and factor == 1000
                else 50
                if factor == 1000
                else 0,
            )
        )
    silver = pd.DataFrame(rows)
    validate_silver_table("airport_traffic", silver)
    fact_columns = [
        "airport_iata",
        "period_id",
        "operator_group",
        "country",
        "passengers_domestic",
        "passengers_international",
        "passengers_total",
        "cargo_tons",
        "operations",
        "source_system",
        "source_file",
        "source_hash",
        "ingested_at",
    ]

    def facts(frame, table, grain):
        frame = frame.reset_index(drop=True).copy()
        frame["calendar_period_id"] = frame.period_id
        frame["fiscal_period_id"] = frame.period_id
        frame["ingested_at"] = (
            pd.to_datetime(frame.ingested_at, utc=True).dt.tz_convert(None).astype("datetime64[ns]")
        )
        return validate_table(table, add_record_ids(frame, table_name=table, natural_key_columns=grain))

    airport_facts = facts(
        silver.loc[~silver.is_group_total, fact_columns],
        "fact_airport_traffic",
        ["airport_iata", "period_id", "operator_group", "source_system"],
    )
    group_rows = silver.loc[silver.is_group_total, fact_columns].drop(
        columns=["airport_iata", "operator_group"]
    )
    group_rows["airport_group_key"] = silver.operator_group.iloc[0]
    group_facts = facts(
        group_rows, "fact_airport_group_traffic", ["airport_group_key", "period_id", "source_system"]
    )
    periods = validate_table(
        "dim_period",
        pd.concat([period_frame(p) for p in sorted(silver.period_id.unique())], ignore_index=True),
    )
    dims = []
    for row in silver.loc[~silver.is_group_total].drop_duplicates("airport_iata").itertuples(index=False):
        dims.append(
            dict(
                airport_iata=row.airport_iata,
                airport_icao=None,
                name=row.airport_name,
                city=None,
                country="MX",
                latitude=np.nan,
                longitude=np.nan,
                elevation=np.nan,
                type=None,
                operator_group=row.operator_group,
                source_system=row.source_system,
                source_file=row.source_file,
                source_hash=row.source_hash,
                ingested_at=row.ingested_at,
                parser_version=row.parser_version,
            )
        )
    airports = validate_table("dim_airport", pd.DataFrame(dims))
    first = group_facts.iloc[0]
    group_dim = validate_table(
        "dim_airport_group",
        pd.DataFrame(
            [
                dict(
                    airport_group_key=first.airport_group_key,
                    airport_group_name=first.airport_group_key + " Mexico",
                    country="MX",
                    source_system=first.source_system,
                    source_file=first.source_file,
                    source_hash=first.source_hash,
                    ingested_at=first.ingested_at,
                )
            ]
        ),
    )
    if (
        not airport_facts.airport_iata.isin(airports.airport_iata).all()
        or not group_facts.airport_group_key.isin(group_dim.airport_group_key).all()
        or not pd.concat([airport_facts.period_id, group_facts.period_id]).isin(periods.period_id).all()
    ):
        raise ValueError("Airport group Gold orphan airport/group/period")
    artifacts = validate_table(
        "dim_source_artifact",
        build_dim_source_artifact(
            workspace / "data/bronze/_manifest.jsonl",
            catalog_path=ROOT / "config/source_catalog.yaml",
            verify_files=True,
        ),
    )
    by_file = artifacts.set_index("source_file").artifact_id.to_dict()
    tables = {
        "airport_group_native": native,
        "fact_airport_traffic": airport_facts,
        "fact_airport_group_traffic": group_facts,
    }
    specs = []
    for name, frame in tables.items():
        for row in frame.itertuples(index=False):
            is_mexico_derived = product == "gap_traffic" and (
                name == "fact_airport_group_traffic"
                or name == "airport_group_native"
                and row.entity_key == "MX"
            )
            parents = ()
            if is_mexico_derived:
                support = native.loc[
                    native.country.eq("MX") & native.airport_iata.notna() & native.period_id.eq(row.period_id)
                ]
                if name == "airport_group_native":
                    support = support.loc[support.market.eq(row.market)]
                parents = tuple(support.record_id)
                if len(parents) != (12 if name == "airport_group_native" else 36):
                    raise ValueError("Calculated Mexico group must retain all native airport contributors")
            rounded = product == "gap_traffic"
            note = (
                (
                    "GAP preliminary terminal passengers; CBX included in TIJ international, "
                    "never added again. "
                    "Native thousands to passengers x1000; rounded to 100 passengers, not exact counts. "
                    + (
                        "Mexico is sum of12 rounded airports (bound600 passengers/market), excludes Jamaica."
                        if is_mexico_derived
                        else "Individual value rounding bound50 passengers; native country preserved."
                    )
                )
                if rounded
                else (
                    "ASUR reported integer passengers. Gold Mexico only:9 airports. "
                    "Transit/general excluded only MX/CO; worldwide total not Mexico."
                )
            )
            if details.get("source_representation") == "authorized_visible_reconstruction":
                note = details["provenance_warning"] + " " + note
            specs.append(
                LineageSpec(
                    record_id=row.record_id,
                    table_name=name,
                    lineage_type="derived" if is_mexico_derived else "direct_artifact",
                    artifact_ids=tuple(by_file.values())
                    if details.get("source_representation") == "authorized_visible_reconstruction"
                    else (by_file[row.source_file],),
                    parent_record_ids=parents,
                    lineage_note=note,
                )
            )
    bridge = validate_table("bridge_record_lineage", build_bridge_record_lineage(specs, artifacts))
    lineage = validate_lineage_frames(
        tables=tables,
        artifacts=artifacts,
        bridge=bridge,
        contracts={
            "tables": {
                "airport_group_native": {"grain": GRAIN},
                "fact_airport_traffic": {
                    "grain": ["airport_iata", "period_id", "operator_group", "source_system"]
                },
                "fact_airport_group_traffic": {"grain": ["airport_group_key", "period_id", "source_system"]},
            }
        },
    )
    return {
        "silver/airport_group_native": native,
        "silver/airport_traffic": silver,
        "gold/fact_airport_traffic": airport_facts,
        "gold/fact_airport_group_traffic": group_facts,
        "gold/dim_airport": airports,
        "gold/dim_airport_group": group_dim,
        "gold/dim_period": periods,
        "gold/dim_source_artifact": artifacts,
        "gold/bridge_record_lineage": bridge,
    }, {
        **details,
        "lineage": lineage,
        "gold_rows": len(airport_facts) + len(group_facts),
        "gold_country_scope": "MX_only",
        "rounded_gold_values_not_exact_counts": product == "gap_traffic",
        "rounding_semantics_in_silver_and_every_record_lineage": True,
        "missing_cargo_and_operations_remain_null": True,
    }
