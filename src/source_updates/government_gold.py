"""Government report native evidence, standard Silver/Gold and physical lineage."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.source_updates.catalog import ROOT
from src.source_updates.government_traffic import GRAIN
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
    selected = native.loc[native.period_type.eq("month")]
    rows = []
    for p, group in selected.groupby("period_id", sort=True):
        pivot = group.pivot(index="metric_key", columns="market", values="value")
        if product == "aicm_traffic":
            passengers = pivot.loc["passengers"]
            operations = pivot.loc["operations", "total"]
            cargo = pivot.loc["cargo", "total"]
        else:
            passengers = pivot.loc["passengers_commercial"] + pivot.loc["passengers_general"]
            operations = sum(
                pivot.loc[k, "total"]
                for k in ["operations_commercial", "operations_general", "operations_cargo"]
            )
            cargo = pivot.loc["cargo", "total"] / 1000
        first = group.iloc[0]
        rows.append(
            dict(
                period_id=p,
                airport_iata=first.airport_iata,
                airport_name="Mexico City" if product == "aicm_traffic" else "Felipe Angeles",
                operator_group="GOVERNMENT",
                country="MX",
                is_group_total=False,
                passengers_domestic=int(passengers.domestic),
                passengers_international=int(passengers.international),
                passengers_total=int(passengers.total),
                operations=int(operations),
                cargo_tons=float(cargo),
                source_system=first.source_system,
                source_file=first.source_file,
                source_hash=first.source_hash,
                ingested_at=first.ingested_at,
                parser_version=first.parser_version,
                passenger_scope="commercial" if product == "aicm_traffic" else "commercial_and_general",
                operations_scope="commercial_and_general"
                if product == "aicm_traffic"
                else "commercial_general_and_cargo",
            )
        )
    silver = pd.DataFrame(rows)
    validate_silver_table("airport_traffic", silver)
    facts = silver.drop(
        columns=["airport_name", "is_group_total", "parser_version", "passenger_scope", "operations_scope"]
    ).copy()
    facts["calendar_period_id"] = facts.period_id
    facts["fiscal_period_id"] = facts.period_id
    facts["ingested_at"] = (
        pd.to_datetime(facts.ingested_at, utc=True).dt.tz_convert(None).astype("datetime64[ns]")
    )
    facts = add_record_ids(
        facts,
        table_name="fact_airport_traffic",
        natural_key_columns=["airport_iata", "period_id", "operator_group", "source_system"],
    )
    facts = validate_table("fact_airport_traffic", facts)
    native = add_record_ids(native, table_name="government_native", natural_key_columns=GRAIN)
    dimension = validate_table(
        "dim_period",
        pd.concat([period_frame(p) for p in sorted(silver.period_id.unique())], ignore_index=True),
    )
    first = facts.iloc[0]
    airport = validate_table(
        "dim_airport",
        pd.DataFrame(
            [
                dict(
                    airport_iata=first.airport_iata,
                    airport_icao=None,
                    name=str(silver.airport_name.iloc[0]),
                    city=None,
                    country="MX",
                    latitude=np.nan,
                    longitude=np.nan,
                    elevation=np.nan,
                    type=None,
                    operator_group="GOVERNMENT",
                    source_system=first.source_system,
                    source_file=first.source_file,
                    source_hash=first.source_hash,
                    ingested_at=first.ingested_at,
                    parser_version=str(silver.parser_version.iloc[0]),
                )
            ]
        ),
    )
    if (
        not facts.period_id.isin(dimension.period_id).all()
        or not facts.airport_iata.isin(airport.airport_iata).all()
    ):
        raise ValueError("Government Gold has orphan airport/period")
    artifacts = validate_table(
        "dim_source_artifact",
        build_dim_source_artifact(
            workspace / "data/bronze/_manifest.jsonl",
            catalog_path=ROOT / "config/source_catalog.yaml",
            verify_files=True,
        ),
    )
    by_file = artifacts.set_index("source_file").artifact_id.to_dict()
    bridge = validate_table(
        "bridge_record_lineage",
        build_bridge_record_lineage(
            [
                LineageSpec(
                    record_id=row.record_id,
                    table_name=name,
                    lineage_type="direct_artifact",
                    artifact_ids=(by_file[row.source_file],),
                    lineage_note="Exact retained government report. Airport totals, not airline traffic. "
                    "Native scope and units preserved.",
                )
                for name, frame in [("fact_airport_traffic", facts), ("government_native", native)]
                for row in frame.itertuples(index=False)
            ],
            artifacts,
        ),
    )
    lineage = validate_lineage_frames(
        tables={"fact_airport_traffic": facts, "government_native": native},
        artifacts=artifacts,
        bridge=bridge,
        contracts={
            "tables": {
                "fact_airport_traffic": {
                    "grain": ["airport_iata", "period_id", "operator_group", "source_system"]
                },
                "government_native": {"grain": GRAIN},
            }
        },
    )
    return {
        "silver/government_native": native,
        "silver/airport_traffic": silver,
        "gold/fact_airport_traffic": facts,
        "gold/dim_airport": airport,
        "gold/dim_period": dimension,
        "gold/dim_source_artifact": artifacts,
        "gold/bridge_record_lineage": bridge,
    }, {
        **details,
        "lineage": lineage,
        "gold_rows": len(facts),
        "native_monthly_and_YTD_kept_separate": True,
        "complete_month_certified": True,
        "latest_source_availability_verified": False,
    }
