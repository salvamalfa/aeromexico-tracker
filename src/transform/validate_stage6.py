"""Executable Definition of Done for Stage 6."""

from __future__ import annotations

import json

import duckdb
import numpy as np
import pandas as pd

from src.config import PATHS
from src.ingest.stage4_common import write_parquet_atomic
from src.transform.stage6_contracts import table_definitions, validate_all_gold
from src.transform.stage6_facts import stage_length_adjusted


REQUIRED_VIEWS = {
    "v_aeromexico_quarterly", "v_peer_comparison", "v_market_share_mx",
    "v_route_performance", "v_unit_economics", "v_data_health",
    "v_restatements", "v_events_timeline", "v_carrier_standalone",
    "v_carrier_consolidated", "v_carrier_default", "v_carrier_metrics_wide",
}


def validate_stage6() -> dict[str, object]:
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, observed: object, expected: object) -> None:
        checks.append(dict(check_name=name, passed=bool(passed), observed=str(observed), expected=str(expected)))

    contract_rows = validate_all_gold(max_stage=6)
    stage6_tables = table_definitions(max_stage=6)
    add("all_gold_contracts", len(contract_rows) == len(stage6_tables), len(contract_rows), len(stage6_tables))

    carrier = pd.read_parquet(PATHS.gold / "dim_carrier.parquet")
    period = pd.read_parquet(PATHS.gold / "dim_period.parquet")
    metric = pd.read_parquet(PATHS.gold / "dim_metric.parquet")
    route = pd.read_parquet(PATHS.gold / "dim_route.parquet")
    airport = pd.read_parquet(PATHS.gold / "dim_airport.parquet")
    fact = pd.read_parquet(PATHS.gold / "fact_carrier_metrics.parquet")
    route_fact = pd.read_parquet(PATHS.gold / "fact_route_traffic.parquet")
    airport_fact = pd.read_parquet(PATHS.gold / "fact_airport_traffic.parquet")
    market = pd.read_parquet(PATHS.gold / "fact_market_data.parquet")
    macro = pd.read_parquet(PATHS.gold / "fact_macro.parquet")
    issues = pd.read_parquet(PATHS.gold / "fact_data_quality_issues.parquet")
    exceptions = pd.read_parquet(PATHS.quality / "stage6_entity_exceptions.parquet")

    add("carrier_keys_nonnull", fact["carrier_key"].notna().all() and route_fact["carrier_key"].notna().all() and market["carrier_key"].notna().all(), int(fact["carrier_key"].isna().sum() + route_fact["carrier_key"].isna().sum() + market["carrier_key"].isna().sum()), 0)
    add("carrier_fk", set(fact["carrier_key"]) | set(route_fact["carrier_key"]) | set(market["carrier_key"]) <= set(carrier["carrier_key"]), sorted((set(fact["carrier_key"]) | set(route_fact["carrier_key"]) | set(market["carrier_key"])) - set(carrier["carrier_key"])), [])
    add("period_fk", set(fact["period_id"]) <= set(period["period_id"]), len(set(fact["period_id"]) - set(period["period_id"])), 0)
    dual_period_frames = [fact, route_fact, airport_fact, market, macro, issues]
    dual_period_ok = all({"calendar_period_id", "fiscal_period_id"} <= set(frame.columns) for frame in dual_period_frames)
    dual_period_ok = dual_period_ok and all(
        frame.loc[frame.get("period_id", pd.Series(index=frame.index, dtype="object")).notna(), ["calendar_period_id", "fiscal_period_id"]].notna().all().all()
        for frame in dual_period_frames
        if "period_id" in frame
    )
    add("dual_period_axes", dual_period_ok, len(dual_period_frames), "calendar_period_id and fiscal_period_id on every fact")
    add("metric_fk", set(fact["metric_key"]) <= set(metric["metric_key"]), len(set(fact["metric_key"]) - set(metric["metric_key"])), 0)
    add("route_fk", set(route_fact["route_key"]) <= set(route["route_key"]), len(set(route_fact["route_key"]) - set(route["route_key"])), 0)
    airport_codes = set(airport["airport_iata"].dropna())
    unresolved = sorted((set(route["origin_iata"]) | set(route["dest_iata"])) - airport_codes)
    add("airport_fk", not unresolved, unresolved, [])
    add("entity_exceptions_documented", len(exceptions) > 0 and exceptions["reason"].notna().all(), len(exceptions), ">0 documented exceptions")

    numeric_nonnegative = {
        "route_passengers": route_fact["passengers"], "route_seats": route_fact["seats"],
        "market_volume": market["volume"],
    }
    add("business_nonnegative", all(series.dropna().ge(0).all() for series in numeric_nonnegative.values()), {name: float(series.min()) for name, series in numeric_nonnegative.items()}, "all >= 0")
    add("market_prices_positive", market[["close", "adj_close"]].gt(0).all().all(), float(market[["close", "adj_close"]].min().min()), ">0")
    add("route_load_factor_formula", np.allclose(route_fact["load_factor"].fillna(-1), (route_fact["rpm_miles"] / route_fact["asm_miles"].replace(0, np.nan)).fillna(-1), rtol=0, atol=1e-12), len(route_fact), "all rows")

    current = fact[fact["is_current"] & fact["period_type"].eq("quarter") & fact["segment"].eq("total")]
    lf = current[current["metric_key"].isin(["load_factor_total", "load_factor_derived"])].pivot_table(index=["carrier_key", "period_id"], columns="metric_key", values="value", aggfunc="first").dropna()
    lf["difference_pp"] = (lf["load_factor_derived"] - lf["load_factor_total"]).abs() * 100
    lf_pass_rate = float(lf["difference_pp"].lt(0.5).mean()) if len(lf) else 0.0
    add("load_factor_reconciliation", lf_pass_rate > 0.95, {"rows": len(lf), "pass_rate": lf_pass_rate, "max_pp": float(lf["difference_pp"].max()) if len(lf) else None}, ">95% under 0.5 pp")

    bmv = current[current["source_system"].eq("bmv_xbrl") & current["metric_key"].isin(["total_revenue", "operating_income", "net_income"])].copy()
    bmv["year"] = bmv["period_id"].str[:4]
    annual = fact[fact["is_current"] & fact["source_system"].eq("bmv_xbrl") & fact["period_type"].eq("year") & fact["metric_key"].isin(["total_revenue", "operating_income", "net_income"])].copy()
    annual["year"] = annual["period_id"]
    quarter_sums = bmv.groupby(["carrier_key", "year", "metric_key"], as_index=False).agg(quarter_sum=("value", "sum"), quarters=("period_id", "nunique"))
    reconciliation = quarter_sums[quarter_sums["quarters"].eq(4)].merge(annual[["carrier_key", "year", "metric_key", "value"]].rename(columns={"value": "annual"}), on=["carrier_key", "year", "metric_key"])
    reconciliation["difference_pct"] = (reconciliation["quarter_sum"] - reconciliation["annual"]).abs() / reconciliation["annual"].abs().replace(0, np.nan)
    annual_pass = len(reconciliation) > 0 and reconciliation["difference_pct"].fillna(0).le(0.001).all()
    add("quarters_equal_annual", annual_pass, {"rows": len(reconciliation), "max_difference_pct": float(reconciliation["difference_pct"].max()) if len(reconciliation) else None}, "all complete years <=0.1%")

    currency_rows = fact[fact["source_system"].isin(["sec_edgar", "aeromexico_ir", "viva_ir", "peer_profile", "bmv_xbrl"]) & fact["currency"].notna()]
    fx_present = currency_rows["fx_rate_used"].notna().all()
    bmv_balance = currency_rows[currency_rows["metric_key"].isin(["total_assets", "total_liabilities", "total_equity", "cash_and_cash_equivalents"])]
    bmv_pnl = currency_rows[currency_rows["metric_key"].isin(["total_revenue", "operating_income", "net_income"])]
    add("fx_rate_recorded", fx_present, int(currency_rows["fx_rate_used"].isna().sum()), 0)
    add("fx_rate_type", bmv_balance["fx_rate_type"].eq("close").all() and bmv_pnl["fx_rate_type"].eq("average").all(), {"balance": sorted(bmv_balance["fx_rate_type"].dropna().unique()), "pnl": sorted(bmv_pnl["fx_rate_type"].dropna().unique())}, "balance=close, pnl=average")
    add("stage_length_formula", abs(stage_length_adjusted(10.0, 1834.0) - 10.0) < 1e-12 and stage_length_adjusted(10.0, None) is None, stage_length_adjusted(10.0, 1834.0), 10.0)
    unit_keys = current[current["metric_key"].isin(["rask", "cask"])][["carrier_key", "period_id", "metric_key"]].copy()
    unit_keys["metric_key"] = "sla_" + unit_keys["metric_key"]
    sla_keys = current[current["metric_key"].isin(["sla_rask", "sla_cask"])][["carrier_key", "period_id", "metric_key"]]
    add("stage_length_rows", set(map(tuple, unit_keys.to_numpy())) == set(map(tuple, sla_keys.to_numpy())), len(sla_keys), "one SLA row per raw RASK/CASK row; NULL allowed when stage length is unavailable")

    dashboard_metrics = metric[metric["is_dashboard_metric"]]
    interpretations_complete = dashboard_metrics[["business_interpretation_up", "business_interpretation_down", "why_it_matters", "caveats"]].notna().all().all() and dashboard_metrics["glossary_section"].notna().all()
    add("dashboard_metric_interpretations", interpretations_complete, len(dashboard_metrics), "100% non-null and linked to glossary")
    add("seasonal_series", fact["metric_key"].eq("passengers_afac_sa").sum() >= 120, int(fact["metric_key"].eq("passengers_afac_sa").sum()), ">=120 monthly rows, explicitly marked")

    connection = duckdb.connect(str(PATHS.warehouse), read_only=True)
    try:
        views = {row[0] for row in connection.execute("SELECT table_name FROM information_schema.views WHERE table_schema='main'").fetchall()}
        anchor = connection.execute("SELECT total_revenue, adjusted_ebitdar, operating_margin, load_factor_reported FROM v_aeromexico_quarterly WHERE period_id='2026Q1'").fetchone()
    finally:
        connection.close()
    add("consumption_views", REQUIRED_VIEWS <= views, sorted(REQUIRED_VIEWS - views), [])
    expected_anchor = (1_341_000_000.0, 335_800_000.0, 0.106, 0.844)
    anchor_pass = anchor is not None and np.allclose(anchor, expected_anchor, rtol=0, atol=[1, 1, 1e-9, 1e-9])
    add("aeromexico_2026q1_anchor", anchor_pass, anchor, expected_anchor)
    add("data_dictionary", (PATHS.root / "docs" / "diccionario-datos.md").stat().st_size > 10_000, (PATHS.root / "docs" / "diccionario-datos.md").stat().st_size, ">10000 bytes")
    build = json.loads((PATHS.quality / "stage6_build.json").read_text(encoding="utf-8"))
    add("bigquery_decision", build["bigquery_decision"] == "DuckDB local only; no BigQuery mirror", build["bigquery_decision"], "DuckDB local only; no BigQuery mirror")
    add("default_scope", build["carrier_scope_default"] == "consolidated", build["carrier_scope_default"], "consolidated")

    checks_frame = pd.DataFrame(checks)
    write_parquet_atomic(checks_frame, PATHS.quality / "stage6_acceptance_checks.parquet")
    summary = {
        "passed": int(checks_frame["passed"].sum()),
        "total": len(checks_frame),
        "all_passed": bool(checks_frame["passed"].all()),
        "failed": checks_frame.loc[~checks_frame["passed"], "check_name"].tolist(),
        "load_factor_rows": len(lf),
        "annual_reconciliations": len(reconciliation),
        "quality_issues": len(issues),
        "contract_rows": contract_rows,
    }
    (PATHS.quality / "stage6_acceptance.json").write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    if not summary["all_passed"]:
        failed = checks_frame[~checks_frame["passed"]].to_dict("records")
        raise AssertionError(f"Stage 6 acceptance failed: {failed}")
    return summary


def main() -> int:
    print(json.dumps(validate_stage6(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
