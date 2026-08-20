"""Stage 1 acceptance checks for SEC silver datasets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import math

import polars as pl

from src.config import PATHS


@dataclass(frozen=True, slots=True)
class CheckResult:
    check: str
    passed: bool
    actual: float | int | str
    expected: float | int | str
    tolerance: str


def _one_value(
    frame: pl.DataFrame,
    *,
    period_id: str,
    metric_key: str,
    column: str,
) -> float:
    selected = frame.filter(
        (pl.col("period_type") == "quarter")
        & (pl.col("period_id") == period_id)
        & (pl.col("metric_key") == metric_key)
    )
    if selected.height != 1:
        raise ValueError(
            f"Expected one {metric_key} row for {period_id}; got {selected.height}"
        )
    return float(selected[column][0])


def _relative_check(name: str, actual: float, expected: float, tolerance: float) -> CheckResult:
    passed = math.isclose(actual, expected, rel_tol=tolerance, abs_tol=0.0)
    return CheckResult(name, passed, actual, expected, f"relative <= {tolerance:.2%}")


def _absolute_check(name: str, actual: float, expected: float, tolerance: float) -> CheckResult:
    passed = abs(actual - expected) <= tolerance
    return CheckResult(name, passed, actual, expected, f"absolute <= {tolerance:g}")


def validate_anchors(
    operating: pl.DataFrame, financial: pl.DataFrame
) -> list[CheckResult]:
    return [
        _relative_check("2026Q1 total_revenue USDm", _one_value(financial, period_id="2026Q1", metric_key="total_revenue", column="value_raw"), 1341.0, 0.01),
        _relative_check("2026Q1 adjusted_ebitdar USDm", _one_value(financial, period_id="2026Q1", metric_key="adjusted_ebitdar", column="value_raw"), 335.8, 0.01),
        _absolute_check("2026Q1 ebitdar_margin", _one_value(financial, period_id="2026Q1", metric_key="ebitdar_margin", column="value_normalized"), 0.250, 0.005),
        _relative_check("2026Q1 operating_income USDm", _one_value(financial, period_id="2026Q1", metric_key="operating_income", column="value_raw"), 141.8, 0.01),
        _absolute_check("2026Q1 operating_margin", _one_value(financial, period_id="2026Q1", metric_key="operating_margin", column="value_normalized"), 0.106, 0.005),
        _relative_check("2026Q1 casm_ex_fuel cents", _one_value(operating, period_id="2026Q1", metric_key="casm_ex_fuel", column="value_raw"), 10.2, 0.01),
        _relative_check("2026Q1 trasm cents", _one_value(operating, period_id="2026Q1", metric_key="trasm", column="value_raw"), 15.6, 0.01),
        _absolute_check("2026Q1 load_factor", _one_value(operating, period_id="2026Q1", metric_key="load_factor_total", column="value_normalized"), 0.844, 0.005),
        _absolute_check("2026Q1 fleet_size", _one_value(operating, period_id="2026Q1", metric_key="fleet_size", column="value_normalized"), 166.0, 0.0),
        _relative_check("2026Q1 passengers", _one_value(operating, period_id="2026Q1", metric_key="passengers", column="value_normalized"), 5_800_000.0, 0.02),
        _absolute_check("2025Q1 load_factor", _one_value(operating, period_id="2025Q1", metric_key="load_factor_total", column="value_normalized"), 0.823, 0.005),
    ]


def validate_invariants(operating: pl.DataFrame) -> dict[str, object]:
    quarterly = operating.filter(pl.col("period_type") == "quarter")
    pivot = quarterly.pivot(
        on="metric_key",
        index=["period_id", "accession_number"],
        values="value_normalized",
        aggregate_function="first",
    )
    capacity = pivot.drop_nulls(["asm_total", "rpm_total", "load_factor_total"])
    capacity = capacity.with_columns(
        (pl.col("rpm_total") / pl.col("asm_total")).alias("load_factor_derived")
    )
    rpk_ask_failures = capacity.filter(pl.col("rpm_total") > pl.col("asm_total")).height
    load_factor_failures = capacity.filter(
        (pl.col("load_factor_total") - pl.col("load_factor_derived")).abs() > 0.005
    ).height
    costs = pivot.drop_nulls(["casm", "casm_ex_fuel"])
    cost_failures = costs.filter(pl.col("casm_ex_fuel") >= pl.col("casm")).height
    positive_failures = pivot.filter(
        (pl.col("trasm").is_not_null() & (pl.col("trasm") <= 0))
        | (pl.col("casm").is_not_null() & (pl.col("casm") <= 0))
    ).height
    core_periods = sorted(
        quarterly.filter(pl.col("metric_key") == "load_factor_total")["period_id"].to_list()
    )
    expected_periods = [
        "2024Q3",
        "2024Q4",
        "2025Q1",
        "2025Q2",
        "2025Q3",
        "2025Q4",
        "2026Q1",
        "2026Q2",
    ]
    return {
        "capacity_rows_checked": capacity.height,
        "rpk_le_ask_failures": rpk_ask_failures,
        "load_factor_formula_failures": load_factor_failures,
        "casm_ex_fuel_failures": cost_failures,
        "positive_cost_revenue_failures": positive_failures,
        "quarterly_periods": core_periods,
        "quarterly_periods_expected": expected_periods,
        "missing_period_failures": 0 if core_periods == expected_periods else 1,
        "passed": not any(
            (rpk_ask_failures, load_factor_failures, cost_failures, positive_failures)
        )
        and core_periods == expected_periods,
    }


def validate_quality() -> dict[str, object]:
    operating = pl.read_parquet(PATHS.silver / "sec_operating_metrics.parquet")
    financial = pl.read_parquet(PATHS.silver / "sec_financials.parquet")
    filings = pl.read_parquet(PATHS.silver / "sec_filings_index.parquet")
    report_text = pl.read_parquet(PATHS.silver / "sec_report_text.parquet")
    crosscheck = pl.read_parquet(PATHS.silver / "sec_crosscheck.parquet")
    anchors = validate_anchors(operating, financial)
    invariants = validate_invariants(operating)
    lineage_columns = [
        "source_system",
        "source_file",
        "source_hash",
        "ingested_at",
        "parser_version",
    ]
    natural_key = ["accession_number", "period_id", "metric_key", "segment"]
    result = {
        "anchors": [asdict(check) for check in anchors],
        "anchors_passed": all(check.passed for check in anchors),
        "invariants": invariants,
        "operating_rows": operating.height,
        "financial_rows": financial.height,
        "filing_rows": filings.height,
        "six_k_rows": filings.filter(pl.col("form_type") == "6-K").height,
        "unclassified_filings": filings.filter(pl.col("content_type").is_null()).height,
        "operating_duplicate_keys": operating.group_by(natural_key).len().filter(pl.col("len") > 1).height,
        "financial_duplicate_keys": financial.group_by(natural_key[:-1]).len().filter(pl.col("len") > 1).height,
        "null_normalized_units": operating.filter(pl.col("unit_normalized").is_null()).height + financial.filter(pl.col("unit_normalized").is_null()).height,
        "null_lineage_values": sum(
            operating[column].null_count() + financial[column].null_count()
            for column in lineage_columns
        ),
        "report_text_rows": report_text.height,
        "crosscheck_rows": crosscheck.height,
        "material_crosscheck_rows": crosscheck.filter(pl.col("is_material")).height,
    }
    result["passed"] = bool(
        result["anchors_passed"]
        and invariants["passed"]
        and result["filing_rows"] == 62
        and result["six_k_rows"] == 12
        and result["unclassified_filings"] == 0
        and result["operating_duplicate_keys"] == 0
        and result["financial_duplicate_keys"] == 0
        and result["null_normalized_units"] == 0
        and result["null_lineage_values"] == 0
        and result["report_text_rows"] >= 11
        and result["crosscheck_rows"] >= 1
    )
    return result


def main() -> int:
    result = validate_quality()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
