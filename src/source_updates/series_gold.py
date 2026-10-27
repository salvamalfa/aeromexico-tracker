"""Rebuild complete selected-series Silver/Gold and documentary lineage offline."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import numpy as np
import pandas as pd

from src.ingest.market.prices import TICKERS
from src.source_updates.catalog import ROOT
from src.source_updates.h10_gold import period_frame
from src.source_updates.series_native import UNITS, window
from src.transform.silver_contracts import validate_silver_table
from src.transform.stage6_contracts import validate_table
from src.transform.stage6_dimensions import CURATED_CARRIERS
from src.transform.stage6_facts import stable_hash
from src.transform.stage9_lineage import (
    LineageSpec,
    add_record_ids,
    build_bridge_record_lineage,
    build_dim_source_artifact,
)
from src.transform.validate_stage9 import validate_lineage_frames


def periods(period: str) -> pd.DataFrame:
    start, end, months = window(period)
    parts = [period_frame(m) for m in months]
    if "Q" in period:
        row = parts[-1].iloc[0].to_dict()
        q = pd.Period(str(end), freq="Q")
        row.update(
            period_id=period,
            period_type="quarter",
            period_start_date=start,
            period_end_date=end,
            month=None,
            days_in_period=(end - start).days + 1,
            prior_period_id=str(q - 1),
            prior_year_period_id=f"{end.year - 1}Q{q.quarter}",
            calendar_period_id=period,
            fiscal_period_id=period,
            is_covid_period=start <= date(2021, 12, 31) and end >= date(2020, 3, 1),
        )
        parts.append(pd.DataFrame([row]))
    return validate_table("dim_period", pd.concat(parts, ignore_index=True))


def macro_facts(product: str, period: str, silver: dict) -> pd.DataFrame:
    source = silver["macro_indicators" if product == "banxico" else "fuel_prices"].copy()
    if product == "fuel":
        source = source.rename(columns={"price_usd_per_gallon": "value"})
    _, _, months = window(period)
    rows = []
    for target in months + ([period] if "Q" in period else []):
        start, end, _ = window(target)
        selected = source.loc[source.date.between(pd.Timestamp(start), pd.Timestamp(end))]
        for indicator, group in selected.groupby("indicator_key", sort=True):
            # Weight every native observation equally, never monthly averages.
            values = [Decimal(str(value)) for value in group.source_value]
            average = float(sum(values) / len(values))
            common = dict(
                period_id=target,
                period_type="month" if "M" in target else "quarter",
                calendar_period_id=target,
                fiscal_period_id=target,
                indicator_key=indicator,
                unit=UNITS[indicator],
                source_system=str(group.source_system.iloc[0]),
                source_file="silver/macro_indicators.parquet"
                if product == "banxico"
                else "silver/fuel_prices.parquet",
                source_hash=stable_hash(sorted(set(group.source_hash))),
                ingested_at=pd.to_datetime(group.ingested_at, utc=True).max().tz_convert(None),
            )
            rows.extend(
                [
                    {**common, "aggregation": "average", "value": average},
                    {
                        **common,
                        "aggregation": "close",
                        "value": float(group.sort_values("date").value.iloc[-1]),
                    },
                ]
            )
    facts = add_record_ids(
        pd.DataFrame(rows),
        table_name="fact_macro",
        natural_key_columns=["period_id", "indicator_key", "aggregation"],
    )
    return validate_table("fact_macro", facts)


def market_facts(period: str, source: pd.DataFrame) -> pd.DataFrame:
    # Keep all preserved history through the window end for returns and warmup.
    source = source.sort_values(["carrier_key", "date"]).copy()
    source["return_1d"] = source.groupby("carrier_key").adj_close.pct_change(fill_method=None)
    source["year"] = source.date.dt.year
    first = source.groupby(["carrier_key", "year"]).adj_close.transform("first")
    source["return_ytd"] = source.adj_close / first - 1
    source["volatility_30d"] = source.groupby("carrier_key").return_1d.transform(
        lambda s: s.rolling(30, min_periods=20).std() * np.sqrt(252)
    )
    source["calendar_period_id"] = source.date.dt.strftime("%Y-%m-%d")
    source["fiscal_period_id"] = source.calendar_period_id
    start, end, _ = window(period)
    source = source.loc[source.date.between(pd.Timestamp(start), pd.Timestamp(end))]
    columns = [
        "carrier_key",
        "ticker",
        "date",
        "calendar_period_id",
        "fiscal_period_id",
        "close",
        "adj_close",
        "volume",
        "currency",
        "return_1d",
        "return_ytd",
        "volatility_30d",
        "source_system",
        "source_file",
        "source_hash",
        "ingested_at",
    ]
    facts = add_record_ids(
        source[columns].reset_index(drop=True),
        table_name="fact_market_data",
        natural_key_columns=["carrier_key", "date"],
    )
    return validate_table("fact_market_data", facts)


def frames(workspace, product: str, period: str, silver: dict, details: dict) -> tuple[dict, dict]:
    for name, frame in silver.items():
        validate_silver_table(name, frame)
    if product == "equities":
        facts = market_facts(period, silver["market_prices"])
        name = "fact_market_data"
    else:
        facts = macro_facts(product, period, silver)
        name = "fact_macro"
    artifacts = validate_table(
        "dim_source_artifact",
        build_dim_source_artifact(
            workspace / "data/bronze/_manifest.jsonl",
            catalog_path=ROOT / "config/source_catalog.yaml",
            verify_files=True,
        ),
    )
    by_file = artifacts.set_index("source_file").artifact_id.to_dict()
    specs = []
    for row in facts.itertuples(index=False):
        if product == "equities":
            files = {row.source_file}
            if row.ticker == "AERO":
                files.add(details["identity_source_file"])
        else:
            table = silver["macro_indicators" if product == "banxico" else "fuel_prices"]
            start, end, _ = window(row.period_id)
            group = table.loc[
                table.indicator_key.eq(row.indicator_key)
                & table.date.between(pd.Timestamp(start), pd.Timestamp(end))
            ]
            files = set(group.source_file)
        if not files or not files <= set(by_file):
            raise ValueError("Every value and identity input must resolve to a verified original")
        specs.append(
            LineageSpec(
                record_id=row.record_id,
                table_name=name,
                lineage_type="derived",
                artifact_ids=tuple(by_file[f] for f in sorted(files)),
                lineage_note=(
                    "Exact retained observations and declared source units; observed-window aggregates, "
                    "not complete publication calendar. AERO additionally requires "
                    "its physical SEC identity original."
                ),
            )
        )
    bridge = validate_table("bridge_record_lineage", build_bridge_record_lineage(specs, artifacts))
    lineage = validate_lineage_frames(tables={name: facts}, artifacts=artifacts, bridge=bridge)
    outputs = {
        **{f"silver/{k}": v for k, v in silver.items()},
        f"gold/{name}": facts,
        "gold/dim_source_artifact": artifacts,
        "gold/bridge_record_lineage": bridge,
    }
    if product == "equities":
        carriers = pd.DataFrame(
            [
                dict(
                    carrier_key=k,
                    **CURATED_CARRIERS[k],
                    valid_from=date(1900, 1, 1),
                    valid_to=None,
                    is_current=True,
                )
                for k in TICKERS.values()
            ]
        )
        carriers = validate_table("dim_carrier", carriers)
        # Arrow restores an all-null date object column as None, not pandas NaT.
        carriers["valid_to"] = carriers.valid_to.astype(object).where(carriers.valid_to.notna(), None)
        if not facts.carrier_key.isin(carriers.carrier_key).all():
            raise ValueError("Orphan market issuer")
        outputs["gold/dim_carrier"] = carriers
    else:
        dimension = periods(period)
        if not facts.period_id.isin(dimension.period_id).all():
            raise ValueError("Orphan macro period")
        outputs["gold/dim_period"] = dimension
    return outputs, {
        **details,
        "lineage": lineage,
        "gold_rows": len(facts),
        "aggregation_basis": "all_native_observations_not_monthly_mean_of_means",
        "calendar_completeness_certified": False,
    }
