"""Financial health page."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.components.kpi_card import metric_context
from src.dashboard.components.metric_chart import time_series_chart
from src.dashboard.components.narrative import callout
from src.dashboard.components.ui import page_header, source_note
from src.dashboard.data import events, metric_definition, query_df
from src.dashboard.pages.common import aeromexico_quarters
from src.dashboard.theme import AERO_BLUE, CHART_LAYOUT, GOLD, GRID, MAGENTA, ORANGE


def render() -> None:
    page_header("Finanzas", "¿Qué dicen resultados, costos, balance y mercado sobre la salud financiera?", eyebrow="06 · P&L, balance y acción")
    quarters = aeromexico_quarters()
    pnl = quarters.dropna(subset=["total_revenue", "operating_income", "net_income"])
    figure = go.Figure()
    colors = {"total_revenue": AERO_BLUE, "operating_income": GOLD, "net_income": MAGENTA}
    labels = {"total_revenue": "Ingreso total", "operating_income": "Utilidad operativa", "net_income": "Utilidad neta"}
    for metric in labels:
        figure.add_bar(x=pnl["period_id"], y=pnl[metric] / 1_000_000, name=labels[metric], marker_color=colors[metric])
    figure.update_layout(**CHART_LAYOUT, barmode="group", title={"text": "Resultados trimestrales<br><sup>Millones de USD; cifras preferidas de la capa consolidada</sup>", "x": 0.01}, height=450)
    figure.update_yaxes(gridcolor=GRID, title="US$ millones")
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
    metric_context(["total_revenue", "operating_income", "net_income", "operating_margin"])

    cost_keys = ["jet_fuel_expense", "wages_salaries_benefits", "maintenance_expense", "aircraft_leasing_expense", "selling_administrative_expense"]
    latest = quarters.iloc[-1]
    costs = pd.DataFrame({"Componente": [metric_definition(key)["metric_name_es"] for key in cost_keys], "USD": [latest.get(key) for key in cost_keys]}).dropna()
    if len(costs):
        cost_figure = go.Figure(go.Bar(x=costs["USD"] / 1_000_000, y=costs["Componente"], orientation="h", marker_color=ORANGE, text=costs["USD"] / 1_000_000, texttemplate="%{text:,.1f}", textposition="outside"))
        cost_figure.update_layout(**CHART_LAYOUT, title={"text": f"Estructura de costos · {latest['period_id']}<br><sup>Componentes reportados, millones de USD</sup>", "x": 0.01}, height=420, showlegend=False)
        cost_figure.update_xaxes(gridcolor=GRID, rangemode="tozero")
        st.plotly_chart(cost_figure, width="stretch", config={"displayModeBar": False})
        metric_context(cost_keys, label="Cómo leer los componentes de costo")

    balance_keys = ["cash_and_cash_equivalents", "total_assets", "total_liabilities", "total_equity"]
    balance = quarters.dropna(subset=["cash_and_cash_equivalents"])
    time_series_chart(balance, x="date", series={key: metric_definition(key)["metric_name_es"] for key in balance_keys if key in balance}, title="Balance reportado", subtitle="USD; la cobertura varía por concepto y periodo", y_title="USD")
    metric_context(balance_keys)

    market = query_df("SELECT date, adj_close FROM fact_market_data WHERE carrier_key='AEROMEXICO' ORDER BY date")
    if len(market):
        result_events = events()
        result_events = result_events[result_events["event_category"].isin(["earnings", "market"])]
        time_series_chart(market, x="date", series={"adj_close": "AERO"}, title="Precio ajustado de AERO", subtitle="Historia disponible desde el relisting de noviembre de 2025", y_title="Precio", events=result_events)
        callout("Una cotización más alta refleja el precio de mercado de la acción, no prueba por sí sola una mejora operativa. Una caída tampoco equivale automáticamente a deterioro del negocio; el periodo disponible aún es corto.", label="Cómo leer la acción")
    event_finding = query_df("SELECT finding_es, caveat FROM fact_study_results WHERE study_key='earnings_event_study'").iloc[0]
    callout(event_finding["finding_es"], label="Reacción a resultados")
    st.caption(event_finding["caveat"])
    st.info("Conciliación: SEC/IR controla métricas operativas; BMV XBRL conserva estados financieros y reexpresiones. Las discrepancias reportado-derivado permanecen en Salud de datos.")
    source_note("SEC EDGAR, BMV XBRL y mercado. No hay recomendación de inversión ni retorno anormal estimado.")
