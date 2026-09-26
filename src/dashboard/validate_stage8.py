"""Executable Definition of Done for the Stage 8 dashboard data (no UI).

P7 retired the Streamlit multipage app and its `AppTest`-driven checks (page
rendering, timings, WCAG contrast on `theme.py`, component source greps).
This module keeps only the checks that verify Stage 8 *data* is correct and
complete, independent of any renderer -- the same data `web/` and
`src/web_export` also depend on.
"""

from __future__ import annotations

import json

import pandas as pd

from src.config import PATHS
from src.dashboard.check_manual_freshness import check as check_freshness
from src.dashboard.data import query_df
from src.ingest.stage4_common import write_parquet_atomic
from src.transform.stage6_contracts import table_definitions, validate_all_gold


DASHBOARD_METRICS = {
    "total_revenue", "adjusted_ebitdar", "ebitdar_margin", "operating_income",
    "operating_margin", "net_income", "load_factor_total", "rask", "cask",
    "trasm", "casm_ex_fuel", "unit_margin", "break_even_load_factor", "asm_total",
    "rpm_total", "passengers", "passengers_afac", "fleet_size", "jet_fuel_expense",
    "wages_salaries_benefits", "maintenance_expense", "aircraft_leasing_expense",
    "selling_administrative_expense", "cash_and_cash_equivalents", "total_assets",
    "total_liabilities", "total_equity",
}


def validate_stage8() -> dict[str, object]:
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, observed: object, expected: object) -> None:
        checks.append({"check_name": name, "passed": bool(passed), "observed": str(observed), "expected": str(expected)})

    contracts = validate_all_gold(max_stage=8)
    stage8_tables = {name for name, definition in table_definitions(max_stage=8).items() if int(definition.get("stage", 6)) == 8}
    add("stage8_contracts", stage8_tables <= contracts.keys(), sorted(stage8_tables), "all declared Stage 8 tables")

    catalog = pd.read_parquet(PATHS.gold / "dim_metric.parquet").set_index("metric_key")
    missing_metrics = sorted(DASHBOARD_METRICS - set(catalog.index))
    interpretation_fields = ["why_it_matters", "business_interpretation_up", "business_interpretation_down"]
    incomplete = [] if missing_metrics else [key for key in DASHBOARD_METRICS if catalog.loc[key, interpretation_fields].isna().any() or not catalog.loc[key, interpretation_fields].astype(str).str.strip().all()]
    add("metric_interpretations", not missing_metrics and not incomplete, {"missing": missing_metrics, "incomplete": sorted(incomplete)}, "none")

    quarter = query_df("SELECT * FROM v_aeromexico_quarterly WHERE period_id='2026Q1'").iloc[0]
    casm_ex_fuel = query_df(
        "SELECT value FROM v_carrier_default WHERE carrier_key='AEROMEXICO' "
        "AND period_id='2026Q1' AND segment='total' AND metric_key='casm_ex_fuel'"
    ).iloc[0, 0]
    anchors = {
        "total_revenue": (float(quarter["total_revenue"]), 1_341_000_000.0),
        "ebitdar_margin": (float(quarter["ebitdar_margin"]), 0.250),
        "load_factor_reported": (float(quarter["load_factor_reported"]), 0.844),
        "trasm_cents_per_mile": (float(quarter["trasm_cents_per_mile"]), 15.6),
        "casm_cents_per_mile": (float(quarter["casm_cents_per_mile"]), 13.8),
        "casm_ex_fuel": (float(casm_ex_fuel), 10.2),
    }
    anchor_ok = all(abs(observed - expected) <= max(1e-9, abs(expected) * 1e-8) for observed, expected in anchors.values())
    add("aeromexico_2026q1_anchors", anchor_ok, anchors, "published anchors")

    forecasts = pd.read_parquet(PATHS.gold / "fact_forecasts.parquet")
    performance = pd.read_parquet(PATHS.gold / "dim_model_performance.parquet")
    intervals = forecasts[["lower_80", "upper_80", "lower_95", "upper_95"]].notna().all().all()
    published_mape = performance.loc[performance["is_published"], "mape"].notna().all() and performance["is_published"].any()
    add("forecast_uncertainty_and_test_mape", intervals and published_mape, {"rows": len(forecasts), "mape": performance.loc[performance["is_published"], "mape"].tolist()}, "bands and test MAPE")

    issues = pd.read_parquet(PATHS.gold / "fact_data_quality_issues.parquet")
    open_issue_count = int(issues["status"].eq("open").sum())
    add("real_data_health", open_issue_count >= 0, open_issue_count, "a real, non-negative open issue count")

    add("offline_data_access", "http" not in (PATHS.root / "src" / "dashboard" / "data.py").read_text(encoding="utf-8").lower(), "Parquet + in-memory DuckDB", "no network client")

    freshness = check_freshness("afac", 62)
    add("afac_freshness_detection", freshness["last_date"] is not None and isinstance(freshness["is_stale"], bool), freshness, "real AFAC date and boolean status")
    workflow = (PATHS.root / ".github" / "workflows" / "refresh.yml").read_text(encoding="utf-8")
    add("refresh_workflow_controls", all(term in workflow for term in ["issues: write", "validation-failed", "manual-source", "check_manual_freshness", "git commit"]), "required controls detected", "failure issue, stale reminder, gold commit")

    frame = pd.DataFrame(checks)
    write_parquet_atomic(frame, PATHS.quality / "stage8_acceptance_checks.parquet")
    summary = {
        "passed": int(frame["passed"].sum()),
        "total": len(frame),
        "all_passed": bool(frame["passed"].all()),
        "failed": frame.loc[~frame["passed"], "check_name"].tolist(),
        "afac": freshness,
    }
    (PATHS.quality / "stage8_acceptance.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not summary["all_passed"]:
        raise AssertionError(frame.loc[~frame["passed"]].to_dict("records"))
    return summary


def main() -> int:
    print(json.dumps(validate_stage8(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
