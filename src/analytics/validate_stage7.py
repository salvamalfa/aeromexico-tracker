"""Executable Definition of Done for Stage 7."""

from __future__ import annotations

import json

import duckdb
import pandas as pd

from src.analytics.common import ANALYTICS_DIR, MODELS_DIR
from src.config import PATHS
from src.ingest.stage4_common import write_parquet_atomic
from src.transform.stage6_contracts import table_definitions, validate_all_gold


EXPECTED_STUDIES = {
    "spread_decomposition", "faa_category2", "aeromexico_vs_volaris",
    "fuel_sensitivity", "earnings_event_study", "route_seasonality",
    "network_concentration",
}
EXPECTED_VIEWS = {
    "v_forecast_published", "v_latest_business_findings", "v_cluster_summary",
    "v_report_language", "v_anomaly_investigation",
}


def validate_stage7() -> dict[str, object]:
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, observed: object, expected: object) -> None:
        checks.append({"check_name": name, "passed": bool(passed), "observed": str(observed), "expected": str(expected)})

    contracts = validate_all_gold(max_stage=7)
    stage7_names = {name for name, definition in table_definitions(max_stage=7).items() if int(definition.get("stage", 6)) == 7}
    add("stage7_contracts", stage7_names <= contracts.keys(), sorted(stage7_names & contracts.keys()), sorted(stage7_names))

    forecast = pd.read_parquet(PATHS.gold / "fact_forecasts.parquet")
    performance = pd.read_parquet(PATHS.gold / "dim_model_performance.parquet")
    language = pd.read_parquet(PATHS.gold / "fact_report_language.parquet")
    anomalies = pd.read_parquet(PATHS.gold / "fact_anomalies.parquet")
    clusters = pd.read_parquet(PATHS.gold / "dim_cluster_assignments.parquet")
    studies = pd.read_parquet(PATHS.gold / "fact_study_results.parquet")
    build = json.loads((ANALYTICS_DIR / "stage7_build.json").read_text(encoding="utf-8"))

    published = performance[performance["is_published"]]
    add("published_beats_seasonal_naive", published["beats_seasonal_naive"].all(), published[["model_name", "smape"]].to_dict("records"), "every published model beats baseline on test")
    add("performance_is_test_only", performance["evaluation_split"].eq("test").all(), sorted(performance["evaluation_split"].unique()), ["test"])
    interval_ok = len(forecast) == 0 or (
        forecast[["lower_80", "upper_80", "lower_95", "upper_95"]].notna().all().all()
        and forecast["lower_95"].le(forecast["lower_80"]).all()
        and forecast["lower_80"].le(forecast["forecast_value"]).all()
        and forecast["forecast_value"].le(forecast["upper_80"]).all()
        and forecast["upper_80"].le(forecast["upper_95"]).all()
    )
    add("forecast_intervals", interval_ok, len(forecast), "ordered 80% and 95% intervals")
    backtest = forecast[forecast["is_backtest"]]
    leakage_ok = len(backtest) == 0 or (backtest["trained_through_period"] < backtest["period_id"]).all()
    add("no_temporal_leakage", leakage_ok, int((backtest["trained_through_period"] >= backtest["period_id"]).sum()) if len(backtest) else 0, 0)

    add("cluster_business_names", clusters["cluster_name"].notna().all() and ~clusters["cluster_name"].str.match(r"(?i)^cluster\s*\d+").any(), sorted(clusters["cluster_name"].unique()), "interpretable names")
    add("cluster_silhouette_and_stability", clusters[["silhouette", "stability_ari"]].notna().all().all(), clusters.groupby("exercise")[["silhouette", "stability_ari"]].first().to_dict("index"), "non-null")
    add("cluster_k_justified", all("k_justification" in item for item in build["clusters"] if item.get("status") in {None, "published_descriptive"}), build["clusters"], "justification per published exercise")
    add("cluster_names_delegated_review", clusters["name_validation_status"].eq("selected_under_user_delegated_authority").all(), sorted(clusters["name_validation_status"].unique()), "selected_under_user_delegated_authority")

    limitations = build["nlp"]["limitations"]
    add("nlp_limitations", len(limitations) >= 3 and build["nlp"]["peer_comparison_status"] == "unavailable", limitations, ">=3 explicit warnings and peer gap")
    ratio_columns = [column for column in language.columns if column.startswith("lm_") and column.endswith("_ratio")]
    add("nlp_ratios_valid", len(ratio_columns) >= 5 and language[ratio_columns].ge(0).all().all() and language[ratio_columns].le(1).all().all(), ratio_columns, ">=5 ratios in [0,1]")

    add("seven_studies", set(studies["study_key"]) == EXPECTED_STUDIES, sorted(studies["study_key"]), sorted(EXPECTED_STUDIES))
    add("written_findings", studies["finding_es"].str.len().gt(40).all(), studies["finding_es"].str.len().min(), ">40 chars each")
    add("anomalies_event_crosswalk", {"event_matched", "event_title", "event_date"} <= set(anomalies.columns), len(anomalies), "event match fields")

    model_dir = MODELS_DIR / build["forecast"]["model_run_id"]
    metadata = json.loads((model_dir / "metadata.json").read_text(encoding="utf-8"))
    add("model_reproducibility", metadata["config"]["seed"] == 1561861 and bool(metadata["code_version"]), metadata, "seed, code version, windows, performance")
    notebook = PATHS.root / "notebooks" / "01_eda.ipynb"
    add("notebook_executed", notebook.exists() and '"execution_count":' in notebook.read_text(encoding="utf-8") and '"outputs": [' in notebook.read_text(encoding="utf-8"), notebook.exists(), "executed notebook")
    add("analytical_reports", all((PATHS.root / "docs" / "analytics" / name).stat().st_size > 2000 for name in ["eda-hallazgos.md", "hallazgos.md"]), "present", ">2000 bytes each")

    connection = duckdb.connect(str(PATHS.warehouse), read_only=True)
    try:
        views = {row[0] for row in connection.execute("SELECT table_name FROM information_schema.views WHERE table_schema='main'").fetchall()}
    finally:
        connection.close()
    add("analytical_views", EXPECTED_VIEWS <= views, sorted(EXPECTED_VIEWS - views), [])

    check_frame = pd.DataFrame(checks)
    write_parquet_atomic(check_frame, PATHS.quality / "stage7_acceptance_checks.parquet")
    summary = {
        "passed": int(check_frame["passed"].sum()), "total": len(check_frame),
        "all_passed": bool(check_frame["passed"].all()),
        "failed": check_frame.loc[~check_frame["passed"], "check_name"].tolist(),
        "published_models": published["model_name"].tolist(),
        "forecast_rows": len(forecast), "cluster_rows": len(clusters),
        "language_rows": len(language), "anomaly_rows": len(anomalies), "study_rows": len(studies),
    }
    (PATHS.quality / "stage7_acceptance.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    if not summary["all_passed"]:
        raise AssertionError(check_frame.loc[~check_frame["passed"]].to_dict("records"))
    return summary


def main() -> int:
    print(json.dumps(validate_stage7(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
