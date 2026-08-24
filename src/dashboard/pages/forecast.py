"""Published forecast and honest backtest page."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.components.kpi_card import metric_context
from src.dashboard.components.narrative import callout
from src.dashboard.components.ui import page_header, source_note, unavailable
from src.dashboard.data import query_df
from src.dashboard.pages.common import period_date, study
from src.dashboard.theme import AERO_BLUE, CHART_LAYOUT, GRID, MAGENTA


def render() -> None:
    page_header("Forecast", "¿Qué trayectoria sugiere la historia mensual y cuánta incertidumbre rodea esa señal?", eyebrow="07 · Hacia adelante, con error visible")
    forecast = query_df("SELECT * FROM v_forecast_published ORDER BY period_id, is_backtest DESC")
    if forecast.empty:
        unavailable("No hay forecast publicado", "Ningún candidato superó al naive estacional en test.")
        return
    forecast["date"] = forecast["period_id"].map(period_date)
    history = query_df(
        """
        SELECT period_id, value AS actual_value FROM v_carrier_default
        WHERE carrier_key='AEROMEXICO' AND metric_key='passengers_afac' AND segment='total'
        ORDER BY period_id DESC LIMIT 36
        """
    ).sort_values("period_id")
    history["date"] = history["period_id"].map(period_date)
    backtest = forecast[forecast["is_backtest"]]
    future = forecast[~forecast["is_backtest"]]
    figure = go.Figure()
    if len(future):
        figure.add_trace(go.Scatter(x=pd.concat([future["date"], future["date"][::-1]]), y=pd.concat([future["upper_95"], future["lower_95"][::-1]]), fill="toself", fillcolor="rgba(11,58,102,0.10)", line={"color": "rgba(255,255,255,0)"}, name="Intervalo 95%", hoverinfo="skip"))
        figure.add_trace(go.Scatter(x=pd.concat([future["date"], future["date"][::-1]]), y=pd.concat([future["upper_80"], future["lower_80"][::-1]]), fill="toself", fillcolor="rgba(11,58,102,0.20)", line={"color": "rgba(255,255,255,0)"}, name="Intervalo 80%", hoverinfo="skip"))
    figure.add_trace(go.Scatter(x=history["date"], y=history["actual_value"], mode="lines+markers", name="Observado", line={"color": AERO_BLUE, "width": 2.5}))
    figure.add_trace(go.Scatter(x=backtest["date"], y=backtest["forecast_value"], mode="lines+markers", name="Backtest", line={"color": MAGENTA, "dash": "dot"}))
    figure.add_trace(go.Scatter(x=future["date"], y=future["forecast_value"], mode="lines+markers", name="Pronóstico", line={"color": AERO_BLUE, "dash": "dash", "width": 2.5}))
    chart_layout = {**CHART_LAYOUT, "margin": {"l": 48, "r": 24, "t": 82, "b": 92}}
    figure.update_layout(**chart_layout, title={"text": "Pasajeros mensuales: observado, backtest y pronóstico<br><sup>Bandas 80% y 95%; julio 2026 a junio 2027</sup>", "x": 0.01}, height=560, legend={"orientation": "h", "y": -0.16, "yanchor": "top", "x": 0})
    figure.update_yaxes(gridcolor=GRID, title="Pasajeros", rangemode="tozero")
    figure.update_xaxes(showgrid=False)
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
    metric_context(["passengers_afac"])

    performance = query_df("SELECT * FROM dim_model_performance WHERE is_published").iloc[0]
    columns = st.columns(4)
    columns[0].metric("MAPE en test", f"{performance['mape']:.2%}")
    columns[1].metric("sMAPE en test", f"{performance['smape']:.2%}")
    columns[2].metric("MASE", f"{performance['mase']:.3f}")
    columns[3].metric("Orígenes de test", f"{int(performance['observations'])}")
    callout(f"El modelo {performance['model_name'].upper()} obtuvo sMAPE de {performance['smape']:.2%}, frente a 3.36% del naive estacional. La ventaja se midió en los últimos doce meses, nunca en entrenamiento.")

    fuel = study("fuel_sensitivity")
    scenario = float(fuel["estimate"]) * 0.20 if pd.notna(fuel["estimate"]) else None
    st.subheader("Escenario ilustrativo: jet fuel +20%")
    if scenario is not None:
        st.metric("Cambio implícito de CASK", f"{scenario:+.1%}")
        st.warning(f"No es guidance ni forecast financiero. Es una elasticidad descriptiva de confianza {fuel['confidence']} con siete trimestres: {fuel['caveat']}")
    unavailable("Guidance comparable", "No se capturó una serie estructurada de guidance de compañía; no se creó una comparación artificial.")
    source_note("fact_forecasts y dim_model_performance. El dashboard consume resultados preentrenados; nunca entrena al abrirse.")
