"""H.10-only candidate Silver and monthly Gold, using existing contracts and lineage."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pandas as pd

from src.ingest.macro.banxico import FED_H10_SERIES_ID
from src.source_updates.catalog import ROOT
from src.source_updates.h10_capture import month_bounds
from src.transform.silver_contracts import validate_silver_table
from src.transform.stage6_contracts import validate_table
from src.transform.stage6_dimensions import gregorian_easter
from src.transform.stage6_facts import stable_hash
from src.transform.stage9_lineage import (
    LineageSpec,
    add_record_ids,
    build_bridge_record_lineage,
    build_dim_source_artifact,
)
from src.transform.validate_stage9 import validate_lineage_frames


def period_frame(period: str) -> pd.DataFrame:
    start, end = month_bounds(period)
    previous = pd.Period(start, freq="M") - 1
    easter = gregorian_easter(end.year)
    window = [easter + timedelta(days=offset) for offset in range(-7, 2)]
    return validate_table(
        "dim_period",
        pd.DataFrame(
            [
                {
                    "period_id": period,
                    "period_type": "month",
                    "period_start_date": start,
                    "period_end_date": end,
                    "year": end.year,
                    "quarter": (end.month - 1) // 3 + 1,
                    "month": end.month,
                    "days_in_period": end.day,
                    "is_covid_period": start.year in {2020, 2021} and start >= date(2020, 3, 1),
                    "prior_period_id": f"{previous.year}M{previous.month:02d}",
                    "prior_year_period_id": f"{end.year - 1}M{end.month:02d}",
                    "fiscal_period_id": period,
                    "calendar_period_id": period,
                    "easter_date": easter,
                    "easter_quarter": (easter.month - 1) // 3 + 1,
                    "easter_days_in_q1": sum(day.month <= 3 for day in window),
                    "easter_days_in_q2": sum(4 <= day.month <= 6 for day in window),
                }
            ]
        ),
    )


def frames(workspace, period: str, observations: list[dict], evidence: dict) -> tuple[dict, dict]:
    primary, reference = evidence["csv"], evidence["history"]
    fx = pd.DataFrame(observations)
    fx["date"] = pd.to_datetime(fx.date)
    fx["rate_close"] = fx.rate_close.astype(float)
    fx = fx.assign(
        currency_pair="USD/MXN",
        unit="mxn_per_usd",
        series_id=FED_H10_SERIES_ID,
        indicator_key="usd_mxn",
        source="federal_reserve_h10",
        source_system="federal_reserve_h10",
        source_file=primary["source_file"],
        source_hash=primary["sha256"],
        crosscheck_source_file=reference["source_file"],
        crosscheck_source_hash=reference["sha256"],
        ingested_at=pd.Timestamp(primary["downloaded_at"]),
        parser_version="h10_certification_v1",
    )
    macro = fx.rename(columns={"rate_close": "value"}).drop(columns="currency_pair")
    validate_silver_table("fx_rates", fx)
    validate_silver_table("macro_indicators", macro)
    valid = [row for row in observations if row["observation_status"] == "observed"]
    values = [Decimal(row["source_value"]) for row in valid]
    average = float(sum(values) / len(values))
    common = {
        "period_id": period,
        "period_type": "month",
        "calendar_period_id": period,
        "fiscal_period_id": period,
        "indicator_key": "usd_mxn",
        "unit": "mxn_per_usd",
        "source_system": "federal_reserve_h10",
        "source_file": "silver/macro_indicators.parquet",
        "source_hash": stable_hash(sorted({primary["sha256"], reference["sha256"]})),
        "ingested_at": max(pd.Timestamp(row["downloaded_at"]) for row in evidence.values()).tz_convert(None),
    }
    fact = add_record_ids(
        pd.DataFrame(
            [
                {**common, "aggregation": "average", "value": average},
                {**common, "aggregation": "close", "value": float(values[-1])},
            ]
        ),
        table_name="fact_macro",
        natural_key_columns=["period_id", "indicator_key", "aggregation"],
    )
    fact = validate_table("fact_macro", fact)
    periods = period_frame(period)
    if not fact.period_id.isin(periods.period_id).all():
        raise ValueError("H.10 Gold period has no matching dimension")
    artifacts = validate_table(
        "dim_source_artifact",
        build_dim_source_artifact(
            workspace / "data/bronze/_manifest.jsonl",
            catalog_path=ROOT / "config/source_catalog.yaml",
            verify_files=True,
        ),
    )
    selected = set(row["source_file"] for row in evidence.values())
    identifiers = tuple(artifacts.loc[artifacts.source_file.isin(selected), "artifact_id"])
    if len(identifiers) != len(selected):
        raise ValueError("H.10 lineage does not resolve every contributing original")
    bridge = validate_table(
        "bridge_record_lineage",
        build_bridge_record_lineage(
            [
                LineageSpec(
                    record_id=record,
                    table_name="fact_macro",
                    lineage_type="derived",
                    artifact_ids=identifiers,
                    lineage_note="Monthly H.10 noon buying quotes; ND excluded, retained explicitly in Silver. Not FIX or a trading close.",
                )
                for record in fact.record_id
            ],
            artifacts,
        ),
    )
    lineage = validate_lineage_frames(tables={"fact_macro": fact}, artifacts=artifacts, bridge=bridge)
    return {
        "silver/fx_rates": fx,
        "silver/macro_indicators": macro,
        "gold/fact_macro": fact,
        "gold/dim_period": periods,
        "gold/dim_source_artifact": artifacts,
        "gold/bridge_record_lineage": bridge,
    }, lineage
