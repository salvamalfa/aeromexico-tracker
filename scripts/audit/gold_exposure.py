"""Reproducible inventory plus a conservative, explicitly curated UI rubric.

Text references are dependency leads, never evidence of actual visualization.
Review the classification against the rendered UI when product views change.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
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
    "dim_events": "Cronología de hechos regulatorios/corporativos para contexto de anomalías",
    "fact_report_language": "Indicadores lingüísticos de reportes; tono de reportes, no satisfacción",
    "fact_anomalies": "Señales estadísticas por investigar; no errores confirmados",
    "dim_cluster_assignments": "Asignaciones de agrupación de series operativas",
    "fact_study_results": "Resultados precomputados de estudios estadísticos",
    "fact_spread_decomposition": "Componentes de descomposición de cambio de margen unitario, identidades contables",
    "fact_forecasts": "Pronósticos precomputados con horizontes/bandas",
    "dim_model_performance": "Evaluaciones de modelos y baselines",
}
ARCHIVE_REVIEW = {"dim_cluster_assignments", "fact_study_results", "fact_report_language"}


SEARCH_ROOTS = ("src", "sql", "config", "tests", "scripts/chat", ".agents/skills", "web/src")


def dependency_references(root: Path, name: str) -> list[str]:
    """Search working files with Git, already required by the inventory.

    Include untracked candidates and hidden skills; standard excludes apply to
    untracked files. Unexpected Git errors invalidate the audit.
    """
    result = subprocess.run(
        [
            "git",
            "grep",
            "--untracked",
            "--exclude-standard",
            "-n",
            "-w",
            "-I",
            "-e",
            name,
            "--",
            *SEARCH_ROOTS,
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Dependency search failed: {result.stderr}")
    return result.stdout.splitlines()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="New evidence directory; historical cuts are never overwritten",
    )
    parser.add_argument(
        "--private-root",
        type=Path,
        help="Optional private sibling checkout; read only, aggregate metadata only",
    )
    args = parser.parse_args()
    out = args.out.resolve()
    if out.exists() and any(out.iterdir()):
        parser.error("Output must be empty: preserve the previous audit cut")
    out.mkdir(parents=True, exist_ok=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PATHS.root, text=True).strip()
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
        refs = dependency_references(PATHS.root, name)

        # Categories may overlap; a literal is only a dependency lead.
        def locations(prefixes=(), contains=None):
            return ";".join(
                ":".join(r.split(":", 2)[:2])
                for r in refs
                if (not prefixes and contains is None)
                or r.startswith(prefixes)
                or (contains is not None and contains in r.split(":", 1)[0])
            )

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
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                content=DIRECT.get(
                    name, CONTEXT.get(name, EXPLAIN.get(name, "Linaje y claves de referencia"))
                ),
                recommendation="evaluar_archivo_futuro_con_dependencias"
                if name in ARCHIVE_REVIEW
                else "conservar",
                period_column=period or "",
                period_types=";".join(sorted(frame["period_type"].dropna().astype(str).unique()))
                if "period_type" in frame
                else "",
                period_min=str(frame[period].dropna().astype(str).min()) if period else "",
                period_max=str(frame[period].dropna().astype(str).max()) if period else "",
                dependency_leads=locations(),
                frontend_export_leads=locations(("src/dashboard/", "src/web_export/", "web/src/")),
                derived_leads=locations(("src/analytics/", "src/transform/", "sql/", "scripts/chat/")),
                control_leads=locations(("tests/", "config/", "src/source_updates/"), contains="validat"),
                thesis_skill_leads=locations(("src/analysis_agent/", ".agents/skills/")),
            )
        )
    analytical = [r for r in rows if r["analytical"]]
    private = {
        "count": None,
        "total_bytes": None,
        "status": "not_checked",
        "per_file_metadata_redacted": True,
    }
    if args.private_root:
        private_root = args.private_root.resolve()
        private_paths = [
            "derived/aerodatabox/fact_route_carrier_domestic_estimate.parquet",
            "derived/aerodatabox/fact_aeromexico_domestic_capacity_estimate.parquet",
            "derived/aerodatabox_international/fact_route_carrier_international_estimate.parquet",
            "derived/aerodatabox_international/fact_aeromexico_international_capacity_estimate.parquet",
        ]
        sizes = []
        for relative in private_paths:
            committed = subprocess.check_output(["git", "show", f"HEAD:{relative}"], cwd=private_root)
            actual = (private_root / relative).read_bytes()
            if (
                not committed.startswith(b"PAR1")
                or hashlib.sha256(actual).digest() != hashlib.sha256(committed).digest()
            ):
                raise ValueError("Private combined Gold missing/materialization or Git hash mismatch; stop")
            sizes.append(len(actual))
        private.update(count=len(sizes), total_bytes=sum(sizes), status="4_of_4_match_git")
    with (out / "tables.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "public_commit": commit,
        "working_tree_note": "Table SHA-256 captures actual bytes; dependency leads refer to the working tree. UI rubric is manually reviewed, not telemetry.",
        "period_note": "Period bounds are lexical over the selected column; mixed grains and compound study periods are not a freshness/completeness check.",
        "continues": "docs/referencias/gold-exposure-20261015/summary.json",
        "public_tables": len(rows),
        "lineage_tables": sum(r["before"] == "linaje" for r in rows),
        "public_bytes": sum(r["bytes"] for r in rows),
        "denominator": "Todas las tablas fact_ públicas más dim_events, dim_cluster_assignments, dim_model_performance; excluye linaje, dimensiones de referencia y calendarios.",
        "analytical_tables": len(analytical),
        "baseline_direct": sum(r["before"] == "directa" for r in analytical),
        "baseline_context_or_validation": sum(r["before"] == "contexto_validacion" for r in analytical),
        "broad_use": sum(r["before"] in {"directa", "contexto_validacion"} for r in analytical),
        "without_own_view": sum(r["before"] == "sin_vista_propia" for r in analytical),
        "market_direct": sum(r["before"] == "directa" for r in analytical),
        "news_additional_gold_tables": 0,
        "baseline_direct_pct": round(
            sum(r["before"] == "directa" for r in analytical) / len(analytical) * 100, 1
        ),
        "market_direct_pct": round(
            sum(r["before"] == "directa" for r in analytical) / len(analytical) * 100, 1
        ),
        "private_flight_gold": private,
        "rubric_note": "Aproximación estática conservadora, no telemetría de usuarios ni porcentaje de filas/columnas expuestas. Directa puede ser un agregado o subconjunto; contexto/validación no equivale a visualización. La disponibilidad por periodo y tipo de cifra limita el mapa. Noticias usa JSON de evidencia y no aumenta este denominador.",
    }
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
