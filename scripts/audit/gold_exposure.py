"""Reproducible inventory plus a conservative, explicitly curated UI rubric.

Text references are dependency leads, never evidence of actual visualization.
Review the classification against the rendered UI when product views change.
"""

from __future__ import annotations

import csv
import json
import subprocess

import pandas as pd

from src.config import PATHS

DIRECT = {
    "fact_carrier_metrics": "Economía unitaria, ocupación, pasajeros y participación AFAC",
    "fact_route_traffic": "Tráfico realizado T-100: KPI y agregados por ruta",
    "fact_route_traffic_summary": "Tráfico resumido por ruta/mes en Vuelos",
    "fact_domestic_scheduled_route_movements": "Programación AICM nacional por ruta en Vuelos",
    "fact_aicm_international_scheduled_route_movements": "Programación AICM internacional por ruta en Vuelos",
    "fact_international_route_observations": "Observaciones oficiales internacionales por ruta en Vuelos",
    "fact_oma_documented_routes": "Servicio documentado OMA en la red internacional",
}
CONTEXT = {
    "fact_aifa_shared_route_presence": "Presencia documentada y cobertura de rutas compartidas AIFA",
    "fact_domestic_exclusive_market_inferences": "Inferencia de operador en mercado exclusivo; pasajeros no mostrados como vuelos",
    "fact_dashboard_coverage": "Cobertura y validación del dashboard",
    "fact_data_quality_issues": "Incidencias de datos y validación de fuentes",
}
EXPLAIN = {
    "fact_airport_traffic": "Pasajeros por aeropuerto y mes; incluye aeropuertos extranjeros GAP; detalle OMA en cuarentena",
    "fact_airport_group_traffic": "Pasajeros nacionales/internacionales/totales por grupo y mes, México",
    "fact_macro": "Series de combustible, tipo de cambio e indicadores macroeconómicos",
    "fact_market_data": "Precios y volúmenes de instrumentos financieros por fecha",
    "dim_events": "Cronología de 22 hechos regulatorios/corporativos para contexto de anomalías",
    "fact_report_language": "Indicadores lingüísticos de 11 reportes; tono de reportes, no satisfacción",
    "fact_anomalies": "23 señales estadísticas por investigar; no errores confirmados",
    "dim_cluster_assignments": "407 asignaciones de agrupación de series operativas",
    "fact_study_results": "7 resultados precomputados de estudios estadísticos",
    "fact_spread_decomposition": "4 descomposiciones de cambio de margen unitario, identidades contables",
    "fact_forecasts": "24 pronósticos precomputados con horizontes/bandas",
    "dim_model_performance": "5 evaluaciones de modelos y baselines",
}
ARCHIVE_REVIEW = {"dim_cluster_assignments", "fact_study_results", "fact_report_language"}


def main():
    out = PATHS.root / "docs/referencias/gold-exposure-20261015"
    out.mkdir(parents=True, exist_ok=True)
    tracked = subprocess.check_output(
        ["git", "ls-files", "data/gold"], cwd=PATHS.root, text=True
    ).splitlines()
    public = [PATHS.root / value for value in tracked if value.endswith(".parquet")]
    rows = []
    for path in public:
        name = path.stem
        frame = pd.read_parquet(path)
        analytic = name.startswith("fact_") or name in {
            "dim_events",
            "dim_cluster_assignments",
            "dim_model_performance",
        }
        baseline = (
            "directa"
            if name in DIRECT
            else "contexto_validacion"
            if name in CONTEXT
            else "sin_vista_propia"
            if analytic
            else "linaje"
            if name.startswith("bridge_")
            else "referencia_calendario"
        )
        after = (
            "directa_parcial" if name in {"fact_airport_traffic", "fact_airport_group_traffic"} else baseline
        )
        refs = subprocess.run(
            ["rg", "-l", name, "src", "sql", "config", "tests"],
            cwd=PATHS.root,
            capture_output=True,
            text=True,
        ).stdout.splitlines()
        # The audit script itself is not an operational consumer.
        refs = [r for r in refs if r != "scripts/audit/gold_exposure.py"]
        period = next(
            (col for col in ["period_id", "date", "event_date", "trained_through_period"] if col in frame),
            None,
        )
        rows.append(
            dict(
                table=name,
                rows=len(frame),
                bytes=path.stat().st_size,
                analytical=analytic,
                before=baseline,
                market_candidate=after,
                content=DIRECT.get(
                    name, CONTEXT.get(name, EXPLAIN.get(name, "Linaje y claves de referencia"))
                ),
                recommendation="evaluar_archivo_futuro_con_dependencias"
                if name in ARCHIVE_REVIEW
                else "visualizar_mercado"
                if name in {"fact_airport_traffic", "fact_airport_group_traffic"}
                else "conservar",
                period_min=str(frame[period].dropna().astype(str).min()) if period else "",
                period_max=str(frame[period].dropna().astype(str).max()) if period else "",
                dependency_leads=";".join(refs),
            )
        )
    with (out / "tables.csv").open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    analytical = [r for r in rows if r["analytical"]]
    summary = {
        "public_tables": len(rows),
        "lineage_tables": sum(r["before"] == "linaje" for r in rows),
        "public_bytes": sum(r["bytes"] for r in rows),
        "denominator": "Todas las tablas fact_ públicas más dim_events, dim_cluster_assignments, dim_model_performance; excluye linaje, dimensiones de referencia y calendarios.",
        "analytical_tables": len(analytical),
        "baseline_direct": len(DIRECT),
        "baseline_context_or_validation": len(CONTEXT),
        "market_direct": len(DIRECT) + 2,
        "news_additional_gold_tables": 0,
        "baseline_direct_pct": round(len(DIRECT) / len(analytical) * 100, 1),
        "market_direct_pct": round((len(DIRECT) + 2) / len(analytical) * 100, 1),
        "private_flight_gold": {
            "count": sum(1 for p in PATHS.gold.glob("*.parquet") if p not in public),
            "total_bytes": sum(p.stat().st_size for p in PATHS.gold.glob("*.parquet") if p not in public),
            "per_file_metadata_redacted": True,
        },
        "rubric_note": "Aproximación estática conservadora, no telemetría de usuarios ni porcentaje de filas/columnas expuestas. Directa puede ser un agregado o subconjunto; contexto/validación no equivale a visualización. La disponibilidad por periodo y tipo de cifra limita el mapa. Noticias usa JSON de evidencia y no aumenta este denominador.",
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
