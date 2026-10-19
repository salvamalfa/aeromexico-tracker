"""Macro Gold aggregates with explicit units and unchanged documentary fingerprints."""

from __future__ import annotations

import pandas as pd

from src.config import PATHS


def build_fact_macro() -> pd.DataFrame:
    from src.transform.stage6_facts import stable_hash

    source = pd.read_parquet(PATHS.silver / "macro_indicators.parquet").copy()
    fuel = pd.read_parquet(PATHS.silver / "fuel_prices.parquet").rename(
        columns={"price_usd_per_gallon": "value"}
    )
    fuel["indicator_key"] = "jet_fuel_usd_per_gallon"
    fuel["source_system"] = "eia"
    source = pd.concat([source, fuel[source.columns]], ignore_index=True)
    source["date"] = pd.to_datetime(source["date"])
    rows = []
    units = {
        "usd_mxn_fix": "mxn_per_usd",
        "usd_mxn": "mxn_per_usd",
        "jet_fuel_usd_per_gallon": "usd_per_gallon",
        "policy_rate": "percent",
    }
    for period_type, period_values in (
        ("month", source["date"].dt.to_period("M")),
        ("quarter", source["date"].dt.to_period("Q")),
    ):
        work = source.assign(_period=period_values)
        for (period, indicator), group in work.groupby(["_period", "indicator_key"]):
            period_id = (
                f"{period.year}M{period.month:02d}"
                if period_type == "month"
                else f"{period.year}Q{period.quarter}"
            )
            lineage_hash = stable_hash(sorted(set(group["source_hash"].astype(str))))
            common = dict(
                period_id=period_id,
                period_type=period_type,
                indicator_key=indicator,
                unit=units.get(indicator, "index"),
                source_system=str(group["source_system"].iloc[-1]),
                source_file="silver/macro_indicators.parquet"
                if indicator != "jet_fuel_usd_per_gallon"
                else "silver/fuel_prices.parquet",
                source_hash=lineage_hash,
                ingested_at=pd.to_datetime(group["ingested_at"], utc=True).max().tz_convert(None),
            )
            rows.append({**common, "value": float(group["value"].mean()), "aggregation": "average"})
            rows.append(
                {
                    **common,
                    "value": float(group.sort_values("date")["value"].iloc[-1]),
                    "aggregation": "close",
                }
            )
    output = pd.DataFrame(rows)
    output["calendar_period_id"] = output["period_id"]
    output["fiscal_period_id"] = output["period_id"]
    columns = [
        "period_id",
        "period_type",
        "calendar_period_id",
        "fiscal_period_id",
        "indicator_key",
        "value",
        "unit",
        "aggregation",
        "source_system",
        "source_file",
        "source_hash",
        "ingested_at",
    ]
    return output[columns].sort_values(["period_id", "indicator_key", "aggregation"]).reset_index(drop=True)
