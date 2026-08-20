"""Offline acceptance checks for the AFAC Stage 3 outputs."""

from __future__ import annotations

import json

import polars as pl

from src.config import PATHS


def validate_afac() -> dict[str, object]:
    facts = pl.read_parquet(PATHS.silver / "afac_monthly_stats.parquet")
    totals = pl.read_parquet(PATHS.quality / "afac_total_checks.parquet")
    reconciliation = pl.read_parquet(
        PATHS.quality / "afac_sec_reconciliation.parquet"
    )
    natural_key = [
        "period_id",
        "source_carrier_name",
        "market",
        "service_type",
        "metric_key",
    ]
    duplicate_keys = facts.group_by(natural_key).len().filter(pl.col("len") > 1).height
    correlation = float(
        reconciliation.select(pl.corr("afac_passengers", "sec_passengers")).item()
    )
    result = {
        "silver_rows": facts.height,
        "period_count": facts["period_id"].n_unique(),
        "period_min": facts["period_id"].min(),
        "period_max": facts["period_id"].max(),
        "negative_values": facts.filter(pl.col("value") < 0).height,
        "null_values": facts.filter(pl.col("value").is_null()).height,
        "duplicate_natural_keys": duplicate_keys,
        "total_checks": totals.height,
        "failed_total_checks": totals.filter(~pl.col("passed")).height,
        "maximum_total_relative_difference": totals["relative_difference"].max(),
        "sec_overlap_months": reconciliation.height,
        "sec_correlation": correlation,
        "estimated_rows_without_footnote": facts.filter(
            pl.col("is_estimated") & pl.col("footnote_text").is_null()
        ).height,
    }
    failures = {
        key: value
        for key, value in result.items()
        if key
        in {
            "negative_values",
            "null_values",
            "duplicate_natural_keys",
            "failed_total_checks",
            "estimated_rows_without_footnote",
        }
        and value != 0
    }
    if correlation <= 0.95:
        failures["sec_correlation"] = correlation
    if result["period_min"] != "2015M01" or result["period_max"] < "2026M06":
        failures["period_coverage"] = (
            result["period_min"],
            result["period_max"],
        )
    if failures:
        raise ValueError(f"AFAC validation failed: {failures}")
    return result


def main() -> int:
    print(json.dumps(validate_afac(), indent=2, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
