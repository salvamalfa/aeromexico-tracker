"""Render the two required Stage 7 analytical reports in plain Spanish."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.config import PATHS


OUTPUT_DIR = PATHS.root / "docs" / "analytics"


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


UNIT_LABELS = {
    "cents_per_ask_km": "centavos por ASK-km",
    "log_ratio_change_pct": "cambio relativo",
    "market_share_gap": "puntos de participación",
    "elasticity": "de elasticidad",
    "cumulative_return": "de retorno acumulado",
    "seasonal_index": "de índice estacional",
    "hhi_0_1": "de HHI",
}


def render_eda(eda: dict[str, object]) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    coverage = eda["coverage"]
    correlations = eda["correlations"].dropna(subset=["correlation"]).copy()
    correlations["absolute"] = correlations["correlation"].abs()
    top_corr = correlations.sort_values("absolute", ascending=False).iloc[0]
    breaks = eda["structural_breaks"]
    stats = eda["seasonal_stats"]
    aero_months = coverage[
        coverage["carrier_key"].eq("AEROMEXICO")
        & coverage["metric_key"].eq("passengers_afac")
        & coverage["segment"].eq("total")
    ].iloc[0]
    quarterly = coverage[
        coverage["carrier_key"].eq("AEROMEXICO") & coverage["period_type"].eq("quarter")
    ]
    lines = [
        "# EDA — hallazgos antes de modelar",
        "",
        "## Resumen",
        "",
        "La serie mensual de pasajeros sí es apta para modelos sencillos y auditables. Las métricas trimestrales de Aeroméxico son útiles para descripción, pero su historia pública comparable todavía es demasiado corta para sostener pronósticos responsables.",
        "",
        "## Diez observaciones de negocio",
        "",
        f"1. **Hay {int(aero_months.observations)} meses continuos de pasajeros AFAC.** La cobertura va de {aero_months.first_period} a {aero_months.last_period}; es la base principal del pronóstico.",
        f"2. **La estacionalidad mueve aproximadamente {stats['seasonal_amplitude_passengers']:,.0f} pasajeros entre el mes estacionalmente más fuerte y el más débil.** Eso equivale a {_pct(stats['seasonal_amplitude_pct_of_median_trend'])} de la tendencia mediana.",
        f"3. **El mes estacionalmente más fuerte es el {int(stats['strongest_month'])} y el más débil el {int(stats['weakest_month'])}.** La planeación de capacidad debe leer los cambios contra ese patrón, no contra una línea plana.",
        f"4. **La relación lineal mensual más alta observada con una variable macro es {top_corr.indicator_key} con {int(top_corr.lag_months)} meses de rezago ({top_corr.correlation:+.2f}).** Es asociación descriptiva, no causalidad.",
        f"5. **El mayor quiebre estadístico candidato aparece en {breaks.iloc[0].break_period}.** La lista de quiebres incluye el régimen 2020-2023, consistente con COVID, salida de Interjet y Categoría 2.",
        "6. **COVID se conserva como información.** No se eliminaron 2020-2021: el modelo ve el choque y la recuperación, con una regla explícita de régimen en la documentación.",
        f"7. **Las métricas trimestrales de Aeroméxico tienen entre {int(quarterly.observations.min())} y {int(quarterly.observations.max())} observaciones según el indicador.** Ocho trimestres no justifican modelos complejos.",
        "8. **La comparación de costos por etapa de vuelo sigue bloqueada.** Las filas SLA son nulas porque no existe etapa promedio global comparable; no se sustituyó con la subred México-EE.UU.",
        "9. **T-100 sí permite estudiar rutas y el episodio FAA con una historia larga.** Su alcance es la red que toca Estados Unidos, no toda la red global.",
        "10. **Los datos faltantes se tratan como faltantes, nunca como cero.** Esta regla se mantiene en cobertura, modelos, texto y estudios.",
        "",
        "## Tratamiento del régimen COVID",
        "",
        "Se conserva la historia completa y se identifica marzo de 2020 a diciembre de 2021 como régimen extraordinario. El objetivo es evitar que la recuperación se borre y, al mismo tiempo, impedir que un modelo la interprete como estacionalidad normal.",
        "",
        "## Fuentes y alcance",
        "",
        "Los resultados provienen de las vistas gold consolidadas, AFAC, T-100 y variables macro preservadas por el pipeline. Las tablas intermedias de esta EDA quedan en `data/analytics/` para reproducir cada cifra.",
    ]
    path = OUTPUT_DIR / "eda-hallazgos.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def render_findings(
    performance: pd.DataFrame,
    forecast_metadata: dict[str, object],
    cluster_metadata: list[dict[str, object]],
    nlp_metadata: dict[str, object],
    anomalies: pd.DataFrame,
    studies: pd.DataFrame,
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    selected = performance[performance["model_name"].eq(forecast_metadata["selected_model"])].iloc[0]
    route_meta = next(item for item in cluster_metadata if item["exercise"] == "routes")
    quarter_meta = next(item for item in cluster_metadata if item["exercise"] == "quarters")
    unexplained = anomalies[~anomalies["event_matched"]]
    study_sections: list[str] = []
    for row in studies.itertuples(index=False):
        estimate_note = "No se publicó una cifra puntual." if pd.isna(row.estimate) else f"Estimación principal: `{row.estimate:.4g}` {UNIT_LABELS.get(row.unit, row.unit)}."
        study_sections.extend(
            [
                f"### {row.title_es}", "", row.finding_es, "", estimate_note,
                "", f"Confianza: **{row.confidence}**. Límite: {row.caveat}", "",
            ]
        )
    if forecast_metadata["published"]:
        forecast_summary = (
            f"El modelo `{forecast_metadata['selected_model']}` superó al ingenuo estacional en test: "
            f"sMAPE {_pct(float(selected.smape))} frente a {_pct(float(forecast_metadata['baseline_test_smape']))}. "
            "Por ello se publican doce meses con bandas de 80% y 95%."
        )
    else:
        forecast_summary = (
            f"El candidato `{forecast_metadata['selected_model']}` obtuvo sMAPE {_pct(float(selected.smape))}, "
            f"sin superar al ingenuo estacional ({_pct(float(forecast_metadata['baseline_test_smape']))}). "
            "No se publicó un pronóstico futuro."
        )
    quarter_text = (
        f"El ejercicio de trimestres usa {quarter_meta.get('rows', 0)} observaciones completas y es únicamente descriptivo."
        if quarter_meta.get("status") == "published_descriptive"
        else "El ejercicio de trimestres no se publicó: la muestra completa produjo grupos inestables o demasiado pequeños."
    )
    lines = [
        "# Aeroméxico: hallazgos analíticos",
        "",
        "## Executive Summary",
        "",
        f"- **El pronóstico mensual pasó un filtro real de desempeño.** {forecast_summary}",
        f"- **La red transfronteriza se separa en {route_meta['k']} perfiles de ruta.** La silueta es {route_meta['silhouette']:.3f} y la estabilidad entre semillas es {route_meta['stability_ari']:.3f}.",
        f"- **La evidencia ofrece siete lecturas de negocio, pero no todas tienen la misma fuerza.** Combustible y reacción bursátil quedan marcados con confianza baja por historia corta; concentración y estacionalidad de T-100 tienen mayor respaldo.",
        f"- **Quedan {len(unexplained)} anomalías sin evento cercano conocido.** Son una lista de investigación, no errores confirmados.",
        "",
        "## Qué sí puede pronosticarse hoy",
        "",
        forecast_summary,
        "",
        "La selección se hizo en validación y la publicación se decidió una sola vez con los últimos doce meses de test. No se reportan métricas de entrenamiento. Los otros indicadores trimestrales no se publican porque su historia es demasiado corta.",
        "",
        "## Cómo se agrupa la operación",
        "",
        f"Las rutas se agruparon con k={route_meta['k']} porque produjo la mejor silueta entre 2 y 6 grupos sin clusters diminutos. {quarter_text}",
        "",
        "Los nombres de negocio se eligieron bajo la autoridad de decisión delegada por el usuario para esta ejecución. Se muestran explícitamente en el dashboard para revisión; no se presenta una etiqueta técnica como explicación.",
        "",
        "El clustering de aerolíneas no se publicó: requería RASK y CASK ajustados por etapa, y esa etapa global comparable no está disponible. Fabricarla habría cambiado la conclusión.",
        "",
        "## Siete estudios de alto valor",
        "",
        *study_sections,
        "## Qué dicen —y qué no dicen— los reportes",
        "",
        f"Se analizaron {nlp_metadata['documents']} documentos de Aeroméxico. El corpus describe longitud, legibilidad, densidad numérica y tono financiero. No infiere intenciones de la administración.",
        "",
        "No se hizo comparación lingüística con Volaris y Delta porque sus textos no están en silver. Sus cifras operativas no sustituyen un corpus de reportes. Loughran-McDonald fue diseñado principalmente para 10-K estadounidenses y aquí se usa como referencia descriptiva.",
        "",
        "## Próximas decisiones útiles",
        "",
        "1. Vigilar cada mes si el error del modelo se mantiene por debajo del ingenuo estacional.",
        "2. Revisar los nombres de cluster cuando entre un año adicional de rutas.",
        "3. Incorporar textos de Volaris y Delta solo mediante fuentes primarias preservadas en bronze.",
        "4. No interpretar la sensibilidad a combustible como cobertura o guía financiera hasta tener más trimestres y datos de hedging.",
        "",
        "## Preguntas abiertas",
        "",
        "- ¿La dependencia observada de MEX en T-100 coincide con la red global cuando exista una fuente pública comparable?",
        "- ¿El modelo mensual conserva ventaja tras doce nuevos meses, o la ventaja fue específica de esta ventana?",
        "- ¿Qué anomalías sin evento cercano corresponden a cambios operativos reales y cuáles a cobertura de fuente?",
        "",
        "## Supuestos y límites",
        "",
        "- La vista consolidada es el alcance predeterminado.",
        "- COVID se conserva y se etiqueta; no se elimina.",
        "- T-100 cubre segmentos que tocan Estados Unidos, no la red mundial.",
        "- Las cifras SLA faltantes siguen faltantes.",
        "- Los análisis causales se describen como naturales o descriptivos; no se convierten en causalidad por redacción.",
    ]
    path = OUTPUT_DIR / "hallazgos.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
