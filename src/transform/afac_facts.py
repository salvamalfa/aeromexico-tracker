"""Native AFAC monthly facts and reconciled Mexican totals for Stage 6."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import PATHS
from src.parse.afac.market_scope import TOTAL_FORMULA, TOTAL_KEY
from src.transform.stage6_facts import FACT_COLUMNS, _build_afac_aggregate_history


def build_afac_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    source = pd.read_parquet(PATHS.silver / "afac_monthly_stats.parquet")
    unknown = source["carrier_key"].isna() | source["carrier_key"].fillna("").str.startswith("OTHER_AFAC_")
    exceptions = (
        source[unknown]
        .groupby(["source_system", "source_carrier_name", "is_domestic_carrier"], dropna=False)
        .agg(
            rows=("value", "size"),
            first_period=("period_id", "min"),
            last_period=("period_id", "max"),
            passengers=("value", "sum"),
        )
        .reset_index()
    )
    exceptions["reason"] = (
        "Identidad AFAC sin correspondencia prioritaria; clave estable y nacionalidad "
        "de la sección nativa conservadas. Sólo la sección mexicana participa en el denominador mexicano."
    )
    native_totals = source[source["carrier_key"].eq(TOTAL_KEY)].copy()
    if native_totals.empty or not native_totals["footnote_text"].eq(TOTAL_FORMULA).all():
        raise ValueError(
            "Native reconciled Mexican AFAC TOTAL rows are required; rebuild selected annual inputs"
        )
    details = source[~source["carrier_key"].eq(TOTAL_KEY)].copy()
    if details["carrier_key"].isna().any():
        raise ValueError("AFAC native carrier identities must retain stable unknown-source keys")
    scope = ["period_id", "service_type", "market", "source_file"]
    actual = details[details["is_domestic_carrier"].eq(True)].groupby(scope)["value"].sum()
    expected = native_totals.set_index(scope)["value"]
    if expected.index.has_duplicates or set(actual.index) != set(expected.index):
        raise ValueError("AFAC Mexican TOTAL coverage differs from native carrier rows")
    if not actual.sort_index().equals(expected.sort_index()):
        raise ValueError("AFAC Mexican TOTAL differs from native carrier rows")
    for _, group in native_totals.groupby(["period_id", "source_file"]):
        if set(zip(group.service_type, group.market, strict=True)) != {
            (service, market)
            for service in ("scheduled", "charter")
            for market in ("domestic", "international")
        }:
            raise ValueError("AFAC Mexican TOTAL requires four native service/market margins")
    mapped = details
    aggregate = _build_afac_aggregate_history(
        mapped,
        ["carrier_key", "period_id", "market"],
    )
    total = _build_afac_aggregate_history(
        mapped,
        ["carrier_key", "period_id"],
    )
    total["market"] = "total"
    aggregate = pd.concat([aggregate, total], ignore_index=True)
    market = _build_afac_aggregate_history(native_totals, ["period_id", "market"])
    market_total = _build_afac_aggregate_history(native_totals, ["period_id"])
    market_total["market"] = "total"
    market = pd.concat([market, market_total], ignore_index=True)
    market["carrier_key"] = "MARKET_TOTAL_MX"
    aggregate = pd.concat([aggregate, market[aggregate.columns]], ignore_index=True)
    ingested = pd.to_datetime(aggregate["ingested_at"], utc=True).dt.tz_convert(None)
    rows = pd.DataFrame(
        {
            "carrier_key": aggregate["carrier_key"],
            "period_id": aggregate["period_id"],
            "calendar_period_id": aggregate["period_id"],
            "fiscal_period_id": aggregate["period_id"],
            "period_type": "month",
            "period_start_date": pd.to_datetime(aggregate["period_start_date"]).dt.date,
            "period_end_date": pd.to_datetime(aggregate["period_end_date"]).dt.date,
            "metric_key": "passengers_afac",
            "segment": aggregate["market"],
            "value": aggregate["value"].astype(float),
            "value_metric": np.nan,
            "value_imperial": np.nan,
            "value_as_reported": aggregate["value"].astype(float),
            "unit_as_reported": "passengers",
            "unit_normalized": "count",
            "currency": None,
            "value_original_currency": np.nan,
            "value_usd": np.nan,
            "fx_rate_used": np.nan,
            "fx_rate_type": None,
            "is_derived": True,
            "is_preliminary": aggregate["is_preliminary"],
            "is_estimated": aggregate["is_estimated"],
            "derivation_formula": "SUM(AFAC passengers) across service_type for carrier, period and market",
            "source_system": "afac",
            "source_file": "silver/afac_monthly_stats.parquet",
            "source_hash": aggregate["source_hash"],
            "ingested_at": ingested,
            "confidence": 1.0,
        }
    )
    # The aggregate helper already assigned version intervals. Preserve them
    # while mapping the source-neutral snapshot to the Gold fact schema.
    rows["valid_from"] = aggregate["valid_from"].to_numpy()
    rows["valid_to"] = aggregate["valid_to"].to_numpy()
    rows["is_current"] = aggregate["is_current"].to_numpy()
    rows["restatement_count"] = aggregate["restatement_count"].to_numpy()
    rows.loc[rows["carrier_key"].eq(TOTAL_KEY), "derivation_formula"] = TOTAL_FORMULA
    return rows[FACT_COLUMNS], exceptions
