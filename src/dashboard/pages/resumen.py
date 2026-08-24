"""Executive summary page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard.components.kpi_card import kpi_card, metric_context
from src.dashboard.components.metric_chart import time_series_chart
from src.dashboard.components.narrative import callout, executive_narrative
from src.dashboard.components.ui import page_header, source_note
from src.dashboard.data import events
from src.dashboard.pages.common import aeromexico_quarters


KPI_KEYS = ["total_revenue", "ebitdar_margin", "load_factor_total", "trasm", "casm_ex_fuel", "unit_margin"]


def render() -> None:
    page_header("Resumen ejecutivo", "¿Cómo le fue a Aeroméxico este trimestre y qué explica el resultado?", eyebrow="01 · Estado del negocio")
    quarters = aeromexico_quarters()
    options = quarters["period_id"].tolist()[::-1]
    selected_period = st.selectbox("Trimestre", options, index=0)
    current = quarters[quarters["period_id"].eq(selected_period)].iloc[0]
    prior_period = f"{int(selected_period[:4]) - 1}{selected_period[4:]}"
    prior_rows = quarters[quarters["period_id"].eq(prior_period)]
    prior = None if prior_rows.empty else prior_rows.iloc[0]
    callout(executive_narrative(current, prior))

    columns = st.columns(3)
    for index, metric_key in enumerate(KPI_KEYS):
        yoy = None
        if prior is not None and pd.notna(current.get(metric_key)) and pd.notna(prior.get(metric_key)) and prior.get(metric_key) != 0:
            yoy = current.get(metric_key) / prior.get(metric_key) - 1
        with columns[index % 3]:
            kpi_card(metric_key, current.get(metric_key), period_id=selected_period, yoy_change=yoy, source="Comunicado de resultados / SEC EDGAR; vista gold consolidada")

    st.subheader("El spread unitario resume precio menos costo")
    spread = quarters.dropna(subset=["rask", "cask"]).copy()
    spread["unit_margin_calculated"] = spread["rask"] - spread["cask"]
    relevant_events = events()
    relevant_events = relevant_events[pd.to_datetime(relevant_events["event_date"]).between(spread["date"].min(), spread["date"].max())]
    time_series_chart(
        spread, x="date", series={"unit_margin_calculated": "Spread RASK-CASK"},
        title="Spread RASK-CASK por trimestre", subtitle="Centavos de USD por ASK-km; eventos materiales marcados", y_title="¢ por ASK-km", events=relevant_events,
    )
    metric_context(["rask", "cask", "unit_margin"])
    source_note("v_carrier_default, dim_metric y dim_events. La cifra reportada prevalece cuando difiere materialmente de una reconstrucción.")
