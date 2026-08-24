"""Capacity and demand page."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.components.kpi_card import metric_context
from src.dashboard.components.metric_chart import time_series_chart
from src.dashboard.components.narrative import callout
from src.dashboard.components.ui import page_header, source_note
from src.dashboard.data import query_df
from src.dashboard.pages.common import period_date
from src.dashboard.theme import AERO_BLUE, CHART_LAYOUT, GRID, MAGENTA


def render() -> None:
    page_header("Capacidad y demanda", "¿La aerolínea está creciendo de forma sana, o poniendo asientos más rápido de lo que crece la demanda?", eyebrow="03 · Volumen y utilización")
    callout("Cuando RPM crece más lento que ASM, el factor de ocupación tiende a caer. Cuando demanda y capacidad avanzan juntas, el crecimiento es más balanceado; el precio todavía decide si fue rentable.")
    operational = query_df(
        """
        SELECT period_id, metric_key, segment, value
        FROM v_carrier_default
        WHERE carrier_key='AEROMEXICO' AND period_type='month'
          AND metric_key IN ('asm_total','rpm_total','load_factor_total','passengers','passengers_afac','passengers_afac_sa')
        ORDER BY period_id
        """
    )
    total = operational[operational["segment"].eq("total")].pivot_table(index="period_id", columns="metric_key", values="value", aggfunc="first").reset_index()
    total["date"] = total["period_id"].map(period_date)
    recent = total.dropna(subset=["asm_total", "rpm_total"])
    time_series_chart(recent, x="date", series={"asm_total": "ASM", "rpm_total": "RPM"}, title="Capacidad ofrecida y demanda volada", subtitle="Serie mensual reportada; mismas unidades de millas", y_title="Millas")
    metric_context(["asm_total", "rpm_total", "load_factor_total"])

    seasonally_adjusted = st.toggle("Mostrar pasajeros desestacionalizados", value=False)
    passenger_column = "passengers_afac_sa" if seasonally_adjusted else "passengers_afac"
    passenger = total.dropna(subset=[passenger_column])
    time_series_chart(passenger, x="date", series={passenger_column: "Pasajeros AFAC"}, title="Pasajeros mensuales de Aeroméxico", subtitle="Desestacionalizado por STL" if seasonally_adjusted else "Observado; conserva el choque y recuperación de COVID", y_title="Pasajeros")
    metric_context([passenger_column])

    segments = operational[operational["metric_key"].eq("passengers") & operational["segment"].isin(["domestic", "international"])].pivot_table(index="period_id", columns="segment", values="value", aggfunc="first").reset_index()
    if len(segments):
        segments["date"] = segments["period_id"].map(period_date)
        figure = go.Figure()
        figure.add_bar(x=segments["date"], y=segments.get("domestic"), name="Doméstico", marker_color=AERO_BLUE)
        figure.add_bar(x=segments["date"], y=segments.get("international"), name="Internacional", marker_color=MAGENTA)
        figure.update_layout(**CHART_LAYOUT, barmode="stack", title={"text": "Mezcla de pasajeros<br><sup>Serie mensual reportada desde octubre de 2024</sup>", "x": 0.01}, height=410)
        figure.update_yaxes(gridcolor=GRID, title="Pasajeros", rangemode="tozero")
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
        metric_context(["passengers"])
    source_note("AFAC y comunicados SEC/IR consolidados. La serie AFAC larga es observada; STL se ofrece como una vista derivada separada.")
