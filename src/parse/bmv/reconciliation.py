"""Reconcile BMV IFRS facts against the Stage 1 SEC earnings-release parser."""

from __future__ import annotations

import math

import polars as pl

from src.config import PATHS


CONCEPT_METRIC_MAP = {
    "ifrs-full_Revenue": "total_revenue",
    "ifrs-full_ProfitLossFromOperatingActivities": "operating_income",
    "ifrs-full_ProfitLossBeforeTax": "income_before_tax",
    "ifrs-full_IncomeTaxExpenseContinuingOperations": "income_tax",
    "ifrs-full_ProfitLoss": "net_income",
}


def _single_row(frame: pl.DataFrame, description: str) -> dict[str, object]:
    if frame.height != 1:
        values = frame.select("value").unique().get_column("value").to_list() if "value" in frame.columns else []
        if frame.height > 1 and len(values) == 1:
            return frame.row(0, named=True)
        raise ValueError(f"Expected one {description}; found {frame.height}")
    return frame.row(0, named=True)


def build_reconciliation(bmv: pl.DataFrame) -> pl.DataFrame:
    sec = pl.read_parquet(PATHS.silver / "sec_financials.parquet")
    common_periods = sorted(
        set(
            bmv.filter(
                (pl.col("ticker") == "AERO")
                & (pl.col("package_report_type") == "quarter")
                & (pl.col("period_type") == "quarter")
                & (~pl.col("is_ytd"))
            )["period_id"].to_list()
        ).intersection(sec["period_id"].to_list())
    )
    rows: list[dict[str, object]] = []
    for period_id in common_periods:
        for concept, metric_key in CONCEPT_METRIC_MAP.items():
            bmv_selected = bmv.filter(
                (pl.col("ticker") == "AERO")
                & (pl.col("package_period_id") == period_id)
                & (pl.col("period_id") == period_id)
                & (pl.col("concept") == concept)
                & (pl.col("dimension_count") == 0)
                & (pl.col("currency") == "USD")
                & (~pl.col("is_ytd"))
                & pl.col("value").is_not_null()
            )
            sec_selected = sec.filter(
                (pl.col("period_id") == period_id)
                & (pl.col("metric_key") == metric_key)
            )
            if bmv_selected.is_empty() or sec_selected.is_empty():
                continue
            bmv_row = _single_row(bmv_selected, f"BMV {concept} for {period_id}")
            if sec_selected.height != 1:
                raise ValueError(f"Expected one SEC {metric_key} for {period_id}; found {sec_selected.height}")
            sec_row = sec_selected.row(0, named=True)
            bmv_value = float(bmv_row["value"])
            sec_value = float(sec_row["value_normalized"])
            absolute_difference = bmv_value - sec_value
            denominator = max(abs(bmv_value), abs(sec_value), 1.0)
            relative_difference = abs(absolute_difference) / denominator
            is_material = relative_difference > 0.01
            is_explained = (not is_material) or abs(absolute_difference) <= 500_000
            rows.append(
                {
                    "carrier_key": "AEROMEXICO",
                    "period_id": period_id,
                    "concept": concept,
                    "sec_metric_key": metric_key,
                    "bmv_value_usd": bmv_value,
                    "sec_value_usd": sec_value,
                    "absolute_difference_usd": absolute_difference,
                    "relative_difference": relative_difference,
                    "is_material": is_material,
                    "explanation": (
                        "Relative difference exceeds 1% only because the SEC table rounds small USD amounts to the nearest million; absolute difference is within USD 0.5 million."
                        if is_material and is_explained
                        else (
                            "Material difference requires source review."
                            if is_material
                            else "Difference is consistent with rounded SEC earnings-release presentation."
                        )
                    ),
                    "is_explained": is_explained,
                    "requires_review": is_material and not is_explained,
                    "bmv_is_derived": bmv_row["is_derived"],
                    "bmv_source_file": bmv_row["source_file"],
                    "bmv_source_hash": bmv_row["source_hash"],
                    "sec_source_file": sec_row["source_file"],
                    "sec_source_hash": sec_row["source_hash"],
                    "parser_version": "bmv_sec_reconciliation_v1",
                }
            )
    if not rows:
        raise ValueError("No common BMV/SEC facts were available for reconciliation")
    frame = pl.DataFrame(rows, strict=False).sort(["period_id", "concept"])
    if not all(math.isfinite(value) for value in frame["relative_difference"].to_list()):
        raise ValueError("Non-finite BMV/SEC reconciliation difference")
    return frame
