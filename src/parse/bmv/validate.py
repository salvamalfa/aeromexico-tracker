"""Stage 2 acceptance checks for BMV XBRL silver datasets."""

from __future__ import annotations

import json
import math

import polars as pl

from src.config import PATHS


PNL_COMPONENTS = {
    "ifrs-full_Revenue": 1.0,
    "ifrs-full_CostOfSales": -1.0,
    "ifrs-full_OtherIncome": 1.0,
    "ifrs-full_DistributionCosts": -1.0,
    "ifrs-full_AdministrativeExpense": -1.0,
    "ifrs-full_OtherExpenseByFunction": -1.0,
}
PNL_RESULT = "ifrs-full_ProfitLossFromOperatingActivities"
BALANCE_COMPONENTS = {
    "ifrs-full_Liabilities": 1.0,
    "ifrs-full_Equity": 1.0,
}
BALANCE_RESULT = "ifrs-full_Assets"
ACCOUNTING_TOLERANCE = 0.001


def _relative_difference(actual: float, expected: float) -> float:
    return abs(actual - expected) / max(abs(actual), abs(expected), 1.0)


def _value_index(rows: list[dict[str, object]]) -> dict[str, float]:
    values: dict[str, float] = {}
    for row in rows:
        if row["value"] is None:
            continue
        concept = str(row["concept"])
        value = float(row["value"])
        if concept in values and not math.isclose(values[concept], value, rel_tol=0, abs_tol=0):
            raise ValueError(f"Conflicting base facts for concept {concept}")
        values[concept] = value
    return values


def _check_row(
    *,
    ticker: str,
    period_id: str,
    check_type: str,
    concept: str,
    actual: float,
    expected: float,
) -> dict[str, object]:
    difference = actual - expected
    relative = _relative_difference(actual, expected)
    return {
        "ticker": ticker,
        "period_id": period_id,
        "check_type": check_type,
        "concept": concept,
        "actual": actual,
        "expected": expected,
        "difference": difference,
        "relative_difference": relative,
        "tolerance": ACCOUNTING_TOLERANCE,
        "passed": relative <= ACCOUNTING_TOLERANCE,
    }


def build_accounting_checks(facts: pl.DataFrame) -> pl.DataFrame:
    checks: list[dict[str, object]] = []
    quarterly = facts.filter(
        (pl.col("package_report_type") == "quarter")
        & (pl.col("package_period_id") == pl.col("period_id"))
        & (pl.col("period_type") == "quarter")
        & (~pl.col("is_ytd"))
        & (pl.col("dimension_count") == 0)
        & (pl.col("currency") == "USD")
        & pl.col("value").is_not_null()
    )
    for key, group in quarterly.group_by(["ticker", "package_period_id"], maintain_order=True):
        ticker, period_id = key
        values = _value_index(group.iter_rows(named=True))
        if set(PNL_COMPONENTS).union({PNL_RESULT}).issubset(values):
            expected = sum(values[concept] * weight for concept, weight in PNL_COMPONENTS.items())
            checks.append(
                _check_row(
                    ticker=ticker,
                    period_id=period_id,
                    check_type="profit_and_loss",
                    concept=PNL_RESULT,
                    actual=values[PNL_RESULT],
                    expected=expected,
                )
            )

    instants = facts.filter(
        (pl.col("package_report_type") == "quarter")
        & (pl.col("package_period_id") == pl.col("period_id"))
        & (pl.col("context_period_type") == "instant")
        & (pl.col("dimension_count") == 0)
        & (pl.col("currency") == "USD")
        & pl.col("value").is_not_null()
    )
    for key, group in instants.group_by(["ticker", "package_period_id"], maintain_order=True):
        ticker, period_id = key
        values = _value_index(group.iter_rows(named=True))
        if set(BALANCE_COMPONENTS).union({BALANCE_RESULT}).issubset(values):
            expected = sum(values[concept] * weight for concept, weight in BALANCE_COMPONENTS.items())
            checks.append(
                _check_row(
                    ticker=ticker,
                    period_id=period_id,
                    check_type="balance_sheet",
                    concept=BALANCE_RESULT,
                    actual=values[BALANCE_RESULT],
                    expected=expected,
                )
            )

    cash_flow = facts.filter(
        (pl.col("statement_type") == "520000")
        & (pl.col("dimension_count") == 0)
        & (pl.col("currency") == "USD")
        & pl.col("value").is_not_null()
    )
    for ticker in sorted(set(cash_flow["ticker"].to_list())):
        ticker_cash_flow = cash_flow.filter(pl.col("ticker") == ticker)
        package_periods = set(ticker_cash_flow["package_period_id"].to_list())
        years = sorted(
            {
                int(period[:4])
                for period in package_periods
                if isinstance(period, str) and period.endswith("Q4")
            }
        )
        for year in years:
            if not all(f"{year}Q{quarter}" in package_periods for quarter in range(1, 5)):
                continue
            full_year_rows = ticker_cash_flow.filter(
                (pl.col("package_period_id") == f"{year}Q4")
                & (pl.col("period_start_date") == pl.lit(f"{year}-01-01").str.to_date())
                & (pl.col("period_end_date") == pl.lit(f"{year}-12-31").str.to_date())
                & pl.col("is_ytd")
                & (~pl.col("is_derived"))
            )
            for full_year in full_year_rows.iter_rows(named=True):
                quarterly_values: list[float] = []
                for quarter in range(1, 5):
                    selected = ticker_cash_flow.filter(
                        (pl.col("package_period_id") == f"{year}Q{quarter}")
                        & (pl.col("period_id") == f"{year}Q{quarter}")
                        & (pl.col("concept") == full_year["concept"])
                        & (pl.col("unit") == full_year["unit"])
                        & (~pl.col("is_ytd"))
                    )
                    unique = selected["value"].unique().to_list()
                    if len(unique) != 1:
                        quarterly_values = []
                        break
                    quarterly_values.append(float(unique[0]))
                if len(quarterly_values) == 4:
                    checks.append(
                        _check_row(
                            ticker=ticker,
                            period_id=str(year),
                            check_type="quarter_sum_to_annual",
                            concept=str(full_year["concept"]),
                            actual=sum(quarterly_values),
                            expected=float(full_year["value"]),
                        )
                    )
    if not checks:
        raise ValueError("No BMV accounting validation checks could be constructed")
    return pl.DataFrame(checks, strict=False).sort(["check_type", "ticker", "period_id", "concept"])


def validate_quality() -> dict[str, object]:
    packages = pl.read_parquet(PATHS.silver / "bmv_packages_index.parquet")
    facts = pl.read_parquet(PATHS.silver / "bmv_financials.parquet")
    concepts = pl.read_parquet(PATHS.silver / "bmv_concepts.parquet")
    reconciliation = pl.read_parquet(PATHS.silver / "bmv_sec_reconciliation.parquet")
    checks = build_accounting_checks(facts)
    lineage_columns = ["source_system", "source_file", "source_hash", "ingested_at", "parser_version"]
    duplicate_keys = facts.group_by(["source_hash", "fact_id"]).len().filter(pl.col("len") > 1).height
    check_counts = {
        check_type: checks.filter(pl.col("check_type") == check_type).height
        for check_type in checks["check_type"].unique().to_list()
    }
    check_failures = {
        check_type: checks.filter((pl.col("check_type") == check_type) & (~pl.col("passed"))).height
        for check_type in checks["check_type"].unique().to_list()
    }
    aero_periods = set(packages.filter(pl.col("ticker") == "AERO")["package_period_id"].to_list())
    expected_aero = {"2025Q3", "2025Q4", "2025", "2026Q1", "2026Q2"}
    result = {
        "package_rows": packages.height,
        "aero_packages": packages.filter(pl.col("ticker") == "AERO").height,
        "volar_packages": packages.filter(pl.col("ticker") == "VOLAR").height,
        "aero_periods": sorted(aero_periods),
        "aero_expected_periods": sorted(expected_aero),
        "financial_rows": facts.height,
        "source_fact_rows": facts.filter(~pl.col("is_derived")).height,
        "derived_fact_rows": facts.filter(pl.col("is_derived")).height,
        "concept_rows": concepts.height,
        "extension_concept_rows": concepts.filter(pl.col("concept_is_extension")).height,
        "duplicate_fact_keys": duplicate_keys,
        "null_lineage_values": sum(facts[column].null_count() for column in lineage_columns),
        "accounting_check_counts": check_counts,
        "accounting_check_failures": check_failures,
        "max_accounting_relative_difference": checks["relative_difference"].max(),
        "reconciliation_rows": reconciliation.height,
        "material_reconciliation_rows": reconciliation.filter(pl.col("is_material")).height,
        "explained_material_rows": reconciliation.filter(pl.col("is_material") & pl.col("is_explained")).height,
        "unresolved_reconciliation_rows": reconciliation.filter(pl.col("requires_review")).height,
    }
    result["passed"] = bool(
        result["package_rows"] == 31
        and result["aero_packages"] == 5
        and result["volar_packages"] == 26
        and aero_periods == expected_aero
        and result["financial_rows"] > 0
        and result["derived_fact_rows"] > 0
        and result["concept_rows"] > 0
        and result["duplicate_fact_keys"] == 0
        and result["null_lineage_values"] == 0
        and all(count > 0 for count in check_counts.values())
        and all(failures == 0 for failures in check_failures.values())
        and result["reconciliation_rows"] >= 1
        and result["unresolved_reconciliation_rows"] == 0
    )
    return result


def main() -> int:
    result = validate_quality()
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
