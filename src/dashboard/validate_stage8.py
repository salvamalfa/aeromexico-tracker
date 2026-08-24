"""Executable Definition of Done for the Stage 8 dashboard."""

from __future__ import annotations

import json
from pathlib import Path
import time

import pandas as pd
from streamlit.testing.v1 import AppTest

from src.config import PATHS
from src.dashboard.check_manual_freshness import check as check_freshness
from src.dashboard.data import query_df
from src.dashboard.theme import AERO_BLUE, CARRIER_COLORS, INK, MAGENTA, MUTED, WHITE
from src.ingest.stage4_common import write_parquet_atomic
from src.transform.stage6_contracts import table_definitions, validate_all_gold


PAGES = [
    "resumen", "economia_unitaria", "capacidad_demanda", "competencia", "red_rutas",
    "finanzas", "forecast", "lenguaje_reportes", "salud_datos", "glosario",
]
DASHBOARD_METRICS = {
    "total_revenue", "adjusted_ebitdar", "ebitdar_margin", "operating_income",
    "operating_margin", "net_income", "load_factor_total", "rask", "cask",
    "trasm", "casm_ex_fuel", "unit_margin", "break_even_load_factor", "asm_total",
    "rpm_total", "passengers", "passengers_afac", "fleet_size", "jet_fuel_expense",
    "wages_salaries_benefits", "maintenance_expense", "aircraft_leasing_expense",
    "selling_administrative_expense", "cash_and_cash_equivalents", "total_assets",
    "total_liabilities", "total_equity",
}


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(left: str, right: str = WHITE) -> float:
    values = sorted((_luminance(left), _luminance(right)), reverse=True)
    return (values[0] + 0.05) / (values[1] + 0.05)


def _run_page(page: str) -> tuple[AppTest, float, float]:
    source = f"from src.dashboard.pages.{page} import render\nrender()"
    started = time.perf_counter()
    app = AppTest.from_string(source, default_timeout=30).run()
    initial = time.perf_counter() - started
    started = time.perf_counter()
    app.run(timeout=30)
    rerun = time.perf_counter() - started
    return app, initial, rerun


def _visible_text(app: AppTest) -> str:
    values: list[str] = []
    for element in app:
        try:
            value = element.value
        except (AttributeError, KeyError):
            continue
        if isinstance(value, (str, int, float)):
            values.append(str(value))
    return " ".join(values)


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

    app_source = (PATHS.root / "src" / "dashboard" / "app.py").read_text(encoding="utf-8")
    add("ten_pages", app_source.count("st.Page(") == 10, app_source.count("st.Page("), 10)
    page_results: dict[str, dict[str, float | int]] = {}
    page_apps: dict[str, AppTest] = {}
    for page in PAGES:
        app, initial, rerun = _run_page(page)
        page_apps[page] = app
        page_results[page] = {"exceptions": len(app.exception), "initial_seconds": round(initial, 4), "rerun_seconds": round(rerun, 4)}
    add("pages_render_without_exceptions", all(item["exceptions"] == 0 for item in page_results.values()), page_results, "0 exceptions")
    add("dashboard_performance", max(item["initial_seconds"] for item in page_results.values()) < 3 and max(item["rerun_seconds"] for item in page_results.values()) < 1, page_results, "initial <3s and rerun <1s")

    competition_text = _visible_text(page_apps["competencia"])
    add("competition_warnings", all(term in competition_text for term in ["IFRS", "US-GAAP", "Ryanair", "marzo", "stage length"]), competition_text[:900], "all comparability warnings visible")
    forecast_text = _visible_text(page_apps["forecast"])
    forecast_source = (PATHS.root / "src" / "dashboard" / "pages" / "forecast.py").read_text(encoding="utf-8")
    metric_labels = [metric.label for metric in page_apps["forecast"].metric]
    disclosure_ok = "MAPE en test" in metric_labels and "Bandas 80% y 95%" in forecast_source
    add("forecast_disclosure_visible", disclosure_ok, {"metric_labels": metric_labels, "page_text": forecast_text[:500]}, "MAPE and intervals visible")

    issues = pd.read_parquet(PATHS.gold / "fact_data_quality_issues.parquet")
    health_text = _visible_text(page_apps["salud_datos"])
    add("real_data_health", f"Issues abiertos · {len(issues)}" in health_text, len(issues), "visible exact issue count")

    metric_chart_source = (PATHS.root / "src" / "dashboard" / "components" / "metric_chart.py").read_text(encoding="utf-8")
    add("event_annotations", "figure.add_vline" in metric_chart_source and "figure.add_annotation" in metric_chart_source, "vertical line + label", "both")
    add("offline_data_access", "http" not in (PATHS.root / "src" / "dashboard" / "data.py").read_text(encoding="utf-8").lower(), "Parquet + in-memory DuckDB", "no network client")

    text_colors = {"ink": INK, "muted": MUTED, "aero": AERO_BLUE, "magenta": MAGENTA}
    carrier_contrast = {carrier: round(contrast(color), 2) for carrier, color in CARRIER_COLORS.items()}
    add("wcag_contrast", all(contrast(color) >= 4.5 for color in text_colors.values()) and all(value >= 3.0 for value in carrier_contrast.values()), {"text": {name: round(contrast(color), 2) for name, color in text_colors.items()}, "marks": carrier_contrast}, "text >=4.5, graphical marks >=3.0")
    add("carrier_color_consistency", set(CARRIER_COLORS) >= {"AEROMEXICO", "VOLARIS", "VIVA_AEROBUS", "DELTA", "RYANAIR"}, CARRIER_COLORS, "five fixed carrier colors")
    kpi_source = (PATHS.root / "src" / "dashboard" / "components" / "kpi_card.py").read_text(encoding="utf-8")
    add("metric_color_semantics", "higher_is_better" in kpi_source and '"inverse"' in kpi_source, "dim_metric-driven delta_color", "higher_is_better")
    footer_source = (PATHS.root / "src" / "dashboard" / "components" / "ui.py").read_text(encoding="utf-8")
    add("independent_disclaimer", "No es consejo de inversión" in footer_source and "independiente y no oficial" in footer_source, "present", "both phrases")

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
        "pages": page_results,
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
