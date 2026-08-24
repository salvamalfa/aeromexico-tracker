"""Quarterly-report language page."""

from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.components.kpi_card import metric_context
from src.dashboard.components.metric_chart import time_series_chart
from src.dashboard.components.narrative import callout
from src.dashboard.components.ui import page_header, source_note, unavailable
from src.dashboard.data import query_df
from src.dashboard.pages.common import period_date
from src.dashboard.theme import AERO_BLUE, CHART_LAYOUT, GOLD, GRID, MAGENTA


def render() -> None:
    page_header("Lenguaje de reportes", "¿Cómo cambia el tono y el foco de los comunicados de Aeroméxico?", eyebrow="08 · Lo que se dice, sin leer mentes")
    st.warning("Corpus pequeño y descriptivo. Loughran-McDonald se calibró principalmente con 10-K estadounidenses. Las métricas describen palabras; no infieren intención, confianza ni veracidad de la administración.")
    language = query_df("SELECT * FROM v_report_language ORDER BY report_type, period_id")
    report_type = st.segmented_control("Tipo de documento", ["earnings", "traffic"], default="earnings", format_func=lambda value: "Resultados" if value == "earnings" else "Tráfico")
    subset = language[language["report_type"].eq(report_type)].copy()
    subset["date"] = subset["period_id"].map(period_date)
    time_series_chart(subset, x="date", series={"lm_positive_ratio": "Positivo", "lm_negative_ratio": "Negativo", "lm_uncertainty_ratio": "Incertidumbre"}, title="Tono financiero por documento", subtitle="Proporción de palabras del léxico; no es un score emocional", y_title="Proporción", percent=True)
    callout("Una proporción negativa o de incertidumbre más alta significa que el documento usa más términos de esas categorías financieras. No significa automáticamente que el trimestre fue peor ni que la administración ocultó algo.")

    figure = go.Figure()
    figure.add_bar(x=subset["period_id"], y=subset["word_count"], name="Palabras", marker_color=AERO_BLUE)
    figure.update_layout(**CHART_LAYOUT, title={"text": "Longitud de los reportes<br><sup>Palabras tokenizadas por documento</sup>", "x": 0.01}, height=380, showlegend=False)
    figure.update_yaxes(gridcolor=GRID, title="Palabras", rangemode="tozero")
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    selected_period = st.selectbox("Explorar vocabulario", subset["period_id"].tolist()[::-1])
    row = subset[subset["period_id"].eq(selected_period)].iloc[0]
    columns = st.columns(3)
    columns[0].markdown("**Términos dominantes**")
    columns[0].write(" · ".join(json.loads(row["top_terms_json"])))
    columns[1].markdown("**Términos que aparecen**")
    columns[1].write(" · ".join(json.loads(row["new_terms_json"])[:15]) or "Sin comparativo previo del mismo tipo")
    columns[2].markdown("**Términos que desaparecen**")
    columns[2].write(" · ".join(json.loads(row["dropped_terms_json"])[:15]) or "Sin comparativo previo del mismo tipo")

    earnings = language[language["report_type"].eq("earnings")][["period_id", "lm_positive_ratio", "lm_negative_ratio", "lm_uncertainty_ratio"]]
    actual = query_df(
        """SELECT period_id, MAX(value) FILTER (WHERE metric_key='operating_margin') AS operating_margin
        FROM v_carrier_default WHERE carrier_key='AEROMEXICO' AND period_type='quarter' GROUP BY period_id"""
    )
    comparison = earnings.merge(actual, on="period_id", how="left")
    st.dataframe(comparison.rename(columns={"period_id": "Periodo", "lm_positive_ratio": "Positivo", "lm_negative_ratio": "Negativo", "lm_uncertainty_ratio": "Incertidumbre", "operating_margin": "Margen operativo"}), hide_index=True, width="stretch", column_config={"Positivo": st.column_config.NumberColumn(format="percent"), "Negativo": st.column_config.NumberColumn(format="percent"), "Incertidumbre": st.column_config.NumberColumn(format="percent"), "Margen operativo": st.column_config.NumberColumn(format="percent")})
    metric_context(["operating_margin"], label="Cómo leer el margen operativo de contraste")
    unavailable("Comparación lingüística con peers", "Los textos de Volaris y Delta no fueron ingeridos; sus cifras operativas no sustituyen documentos.")
    source_note("sec_report_text y diccionario oficial Loughran-McDonald. Las listas de términos conservan orden TF-IDF, no frecuencia bruta.")
