"""Acceptance checks and source reconciliations for Stage 5."""

from __future__ import annotations

import json

import polars as pl

from src.config import PATHS
from src.parse.sec.common import write_parquet_atomic


def build_t100_aeromexico_validation() -> tuple[pl.DataFrame, dict[str, float]]:
    reported = (
        pl.read_parquet(PATHS.silver / "sec_operating_metrics.parquet")
        .filter(
            (pl.col("carrier_key") == "AEROMEXICO")
            & (pl.col("period_type") == "month")
            & (pl.col("metric_key") == "asm_total")
            & (pl.col("segment") == "international")
        )
        .with_columns(
            (
                pl.col("period_start_date").dt.year().cast(pl.String)
                + pl.lit("Q")
                + pl.col("period_start_date").dt.quarter().cast(pl.String)
            ).alias("period_id")
        )
        .group_by("period_id")
        .agg(
            pl.col("period_start_date").dt.month().n_unique().alias("reported_months"),
            pl.col("value_normalized").sum().alias("reported_international_asm"),
        )
        .filter(pl.col("reported_months") == 3)
    )
    t100 = (
        pl.read_parquet(PATHS.silver / "bts_t100_segment.parquet")
        .filter(pl.col("carrier_key") == "AEROMEXICO")
        .with_columns(
            (
                pl.col("year").cast(pl.String)
                + pl.lit("Q")
                + pl.col("quarter").cast(pl.String)
            ).alias("period_id")
        )
        .group_by("period_id")
        .agg(
            pl.col("month").n_unique().alias("t100_months"),
            pl.col("asm_miles").sum().alias("t100_us_asm"),
        )
        .filter(pl.col("t100_months") == 3)
    )
    validation = reported.join(t100, on="period_id", how="inner").with_columns(
        (pl.col("t100_us_asm") / pl.col("reported_international_asm")).alias(
            "us_share_of_reported_international_asm"
        )
    ).sort("period_id")
    if validation.height < 3:
        raise ValueError("Fewer than three complete quarters available for T-100 stability")
    ratios = validation["us_share_of_reported_international_asm"]
    mean = float(ratios.mean())
    coefficient_of_variation = float(ratios.std(ddof=0) / mean)
    quarter_changes = validation.with_columns(
        pl.col("us_share_of_reported_international_asm")
        .pct_change()
        .abs()
        .alias("absolute_qoq_change")
    )["absolute_qoq_change"].drop_nulls()
    max_qoq_change = float(quarter_changes.max()) if quarter_changes.len() else 0.0
    summary = {
        "quarters": float(validation.height),
        "mean_ratio": mean,
        "coefficient_of_variation": coefficient_of_variation,
        "max_absolute_qoq_change": max_qoq_change,
        "is_stable": coefficient_of_variation <= 0.15 and max_qoq_change <= 0.25,
    }
    if not summary["is_stable"]:
        raise ValueError(f"T-100 Aeromexico ASM proportion is unstable: {summary}")
    write_parquet_atomic(
        validation, PATHS.silver / "bts_t100_aeromexico_validation.parquet"
    )
    return validation, summary


def validate_stage5() -> dict[str, object]:
    checks: list[dict[str, object]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        checks.append({"check": name, "passed": bool(passed), "detail": detail})

    t100 = pl.read_parquet(PATHS.silver / "bts_t100_segment.parquet")
    check("t100_starts_2015", int(t100["year"].min()) == 2015, str(t100["year"].min()))
    check(
        "t100_mexico_us_only",
        t100.filter(
            ~(
                ((pl.col("origin_country") == "MX") & (pl.col("dest_country") == "US"))
                | ((pl.col("origin_country") == "US") & (pl.col("dest_country") == "MX"))
            )
        ).is_empty(),
        f"rows={t100.height}",
    )
    check("t100_no_unmapped", t100["carrier_key"].null_count() == 0, "null carrier keys")
    check(
        "t100_nonnegative_capacity",
        t100.filter((pl.col("seats") < 0) | (pl.col("passengers") < 0)).is_empty(),
        "seats and passengers",
    )
    _, stability = build_t100_aeromexico_validation()
    check("t100_aeromexico_stable", bool(stability["is_stable"]), json.dumps(stability))

    identities = pl.read_parquet(PATHS.silver / "sec_peer_identities.parquet")
    check(
        "sec_ciks_verified",
        identities.height == 4 and identities["is_verified"].all(),
        f"verified={identities.height}",
    )
    if (PATHS.silver / "peer_operating_metrics.parquet").exists():
        peers = pl.read_parquet(PATHS.silver / "peer_operating_metrics.parquet")
        quarters = (
            peers.filter(pl.col("period_type") == "quarter")
            .group_by("carrier_key")
            .agg(pl.col("period_id").n_unique().alias("quarters"))
        )
        for row in quarters.iter_rows(named=True):
            check(
                f"{str(row['carrier_key']).lower()}_eight_quarters",
                int(row["quarters"]) >= 8,
                f"quarters={row['quarters']}",
            )
        delta = pl.read_parquet(PATHS.silver / "delta_companyfacts_reconciliation.parquet")
        check(
            "delta_companyfacts_within_0_1pct",
            delta.height > 0 and float(delta["absolute_difference_pct"].max()) <= 0.001,
            f"max={delta['absolute_difference_pct'].max()}",
        )
        ryanair = pl.read_parquet(PATHS.silver / "ryanair_fiscal_reconciliation.parquet")
        check(
            "ryanair_fiscal_within_1pct",
            ryanair.height >= 3
            and float(ryanair["passenger_difference_pct"].max()) <= 0.01
            and float(ryanair["load_factor_difference_pp"].max()) <= 1.0,
            (
                f"years={ryanair.height}, passenger_max="
                f"{ryanair['passenger_difference_pct'].max()}, load_factor_pp_max="
                f"{ryanair['load_factor_difference_pp'].max()}"
            ),
        )
    result = {
        "passed": sum(bool(row["passed"]) for row in checks),
        "total": len(checks),
        "checks": checks,
    }
    if result["passed"] != result["total"]:
        failures = [row for row in checks if not row["passed"]]
        raise ValueError(f"Stage 5 validation failed: {failures}")
    return result


def main() -> int:
    print(json.dumps(validate_stage5(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
