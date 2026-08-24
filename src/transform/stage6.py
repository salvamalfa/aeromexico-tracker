"""Orchestrate the complete Stage 6 silver-to-gold build."""

from __future__ import annotations

import json

import pandas as pd

from src.config import PATHS
from src.ingest.stage4_common import write_parquet_atomic
from src.transform.generate_data_dictionary import generate as generate_dictionary
from src.transform.stage6_contracts import validate_all_gold, validate_table
from src.transform.stage6_dimensions import augment_dim_airport, build_dim_carrier, build_dim_metric, build_dim_period, build_dim_route
from src.transform.stage6_facts import (
    build_fact_airport_traffic,
    build_fact_carrier_metrics,
    build_fact_macro,
    build_fact_market_data,
    build_fact_route_traffic,
)
from src.transform.stage6_warehouse import build_warehouse


def _extend_fx_years() -> None:
    path = PATHS.gold / "dim_fx_period.parquet"
    frame = pd.read_parquet(path)
    daily = pd.read_parquet(PATHS.gold / "fx_business_calendar.parquet")
    daily["date"] = pd.to_datetime(daily["date"])
    yearly = daily.assign(year=daily["date"].dt.year).groupby("year", as_index=False).agg(
        rate_avg=("rate_close", "mean"), rate_close=("rate_close", "last"),
        rate_min=("rate_close", "min"), rate_max=("rate_close", "max"),
    )
    yearly["period_id"] = yearly["year"].astype(int).astype(str)
    yearly["period_type"] = "year"
    yearly["currency_pair"] = "USD/MXN"
    yearly["pnl_conversion_method"] = "period_average"
    yearly["balance_conversion_method"] = "period_close"
    yearly = yearly.drop(columns="year")
    output = pd.concat([frame[~frame["period_type"].eq("year")], yearly[frame.columns]], ignore_index=True).sort_values(["period_id", "currency_pair"])
    write_parquet_atomic(output, path)


def _write(table_name: str, frame: pd.DataFrame) -> None:
    validated = validate_table(table_name, frame)
    write_parquet_atomic(validated, PATHS.gold / f"{table_name}.parquet")


def run() -> dict[str, object]:
    _extend_fx_years()
    _write("dim_period", build_dim_period())
    _write("dim_carrier", build_dim_carrier())
    _write("dim_airport", augment_dim_airport())
    _write("dim_route", build_dim_route())

    carrier_metrics, issues, exceptions = build_fact_carrier_metrics()
    _write("fact_carrier_metrics", carrier_metrics)
    _write("fact_data_quality_issues", issues)
    write_parquet_atomic(exceptions, PATHS.quality / "stage6_entity_exceptions.parquet")
    _write("fact_route_traffic", build_fact_route_traffic())
    _write("fact_airport_traffic", build_fact_airport_traffic())
    _write("fact_market_data", build_fact_market_data())
    _write("fact_macro", build_fact_macro())

    metric_keys = set(carrier_metrics["metric_key"].dropna().astype(str))
    _write("dim_metric", build_dim_metric(metric_keys))
    contracts = validate_all_gold()
    views = build_warehouse()
    dictionary = generate_dictionary()
    evidence = {
        "parser_version": "stage6_v1.0.0",
        "tables": contracts,
        "views": views,
        "dictionary_bytes": len(dictionary.encode("utf-8")),
        "bigquery_decision": "DuckDB local only; no BigQuery mirror",
        "carrier_scope_default": "consolidated",
        "carrier_scope_available": ["standalone", "consolidated"],
    }
    (PATHS.quality / "stage6_build.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return evidence


def main() -> int:
    print(json.dumps(run(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
