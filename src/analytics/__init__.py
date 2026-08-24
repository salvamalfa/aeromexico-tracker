"""Forecasting, clustering, NLP, anomaly detection, and business studies."""

from __future__ import annotations

import json

from src.analytics.anomalies import run_anomalies
from src.analytics.build_notebook import build as build_notebook
from src.analytics.clustering import run_clustering
from src.analytics.common import ANALYTICS_DIR, model_run_id, write_gold, write_json
from src.analytics.eda import run_eda
from src.analytics.forecast import run_forecast
from src.analytics.nlp_reports import run_nlp
from src.analytics.reporting import render_eda, render_findings
from src.analytics.studies import run_all
from src.transform.generate_data_dictionary import generate as generate_dictionary
from src.transform.stage6_contracts import validate_all_gold
from src.transform.stage6_warehouse import build_warehouse


def run() -> dict[str, object]:
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    eda = run_eda()
    forecasts, performance, forecast_metadata = run_forecast()
    assignments, cluster_metadata = run_clustering()
    language, nlp_metadata = run_nlp()
    analytics_run_id = model_run_id({"task": "stage7_business_studies", "version": 1})
    studies, study_details = run_all(analytics_run_id)
    anomalies = run_anomalies(eda["seasonality"], assignments)

    write_gold("fact_forecasts", forecasts)
    write_gold("dim_model_performance", performance)
    write_gold("fact_report_language", language)
    write_gold("fact_anomalies", anomalies)
    write_gold("dim_cluster_assignments", assignments)
    write_gold("fact_study_results", studies)
    contracts = validate_all_gold(max_stage=7)
    views = build_warehouse(max_stage=7)
    generate_dictionary()
    render_eda(eda)
    render_findings(performance, forecast_metadata, cluster_metadata, nlp_metadata, anomalies, studies)
    build_notebook()

    write_json(ANALYTICS_DIR / "clustering_metadata.json", cluster_metadata)
    write_json(ANALYTICS_DIR / "nlp_metadata.json", nlp_metadata)
    write_json(ANALYTICS_DIR / "study_details.json", study_details)
    summary = {
        "parser_version": "stage7_v1.0.0",
        "forecast": forecast_metadata,
        "clusters": cluster_metadata,
        "nlp": nlp_metadata,
        "anomalies": len(anomalies),
        "unexplained_anomalies": int((~anomalies["event_matched"]).sum()),
        "studies": studies["study_key"].tolist(),
        "tables": {name: contracts[name] for name in contracts if name in {
            "fact_forecasts", "dim_model_performance", "fact_report_language",
            "fact_anomalies", "dim_cluster_assignments", "fact_study_results",
        }},
        "views": [view for view in views if view.startswith(("v_forecast", "v_latest_business", "v_cluster", "v_report", "v_anomaly"))],
    }
    write_json(ANALYTICS_DIR / "stage7_build.json", summary)
    return summary


def main() -> int:
    print(json.dumps(run(), indent=2, ensure_ascii=False, default=str))
    return 0
