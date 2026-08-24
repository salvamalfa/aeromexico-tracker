"""Network and routes page."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.dashboard.components.comparison_chart import ranked_bar
from src.dashboard.components.echarts import ranked_bar as echarts_ranked_bar
from src.dashboard.components.kpi_card import metric_context
from src.dashboard.components.narrative import callout
from src.dashboard.components.ui import page_header, source_note
from src.dashboard.data import query_df
from src.dashboard.pages.common import study
from src.dashboard.theme import AERO_BLUE, CHART_LAYOUT, GRID, MAGENTA


def render() -> None:
    page_header("Red y rutas", "¿Dónde vuela Aeroméxico hacia Estados Unidos y qué tan concentrada está esa red?", eyebrow="05 · Mercados y dependencia")
    routes = query_df(
        """
        SELECT r.*, ao.latitude AS origin_lat, ao.longitude AS origin_lon,
               ad.latitude AS dest_lat, ad.longitude AS dest_lon
        FROM v_dashboard_route_latest12 r
        LEFT JOIN dim_airport ao ON r.origin_iata=ao.airport_iata
        LEFT JOIN dim_airport ad ON r.dest_iata=ad.airport_iata
        WHERE r.carrier_key='AEROMEXICO'
        ORDER BY r.asm_miles DESC
        """
    ).dropna(subset=["origin_lat", "origin_lon", "dest_lat", "dest_lon"])
    figure = go.Figure()
    top = routes.head(30)
    for row in top.itertuples(index=False):
        figure.add_trace(go.Scatter(
            x=[row.origin_lon, row.dest_lon], y=[row.origin_lat, row.dest_lat], mode="lines",
            line={"color": AERO_BLUE, "width": max(1, min(8, row.seats / max(top["seats"].max(), 1) * 8))},
            opacity=0.45, hovertext=f"{row.market_key}: {row.seats:,.0f} asientos", hoverinfo="text", showlegend=False,
        ))
    airports = query_df(
        """
        SELECT DISTINCT airport_iata, latitude, longitude FROM dim_airport
        WHERE airport_iata IN (SELECT origin_iata FROM v_dashboard_route_latest12 WHERE carrier_key='AEROMEXICO'
                               UNION SELECT dest_iata FROM v_dashboard_route_latest12 WHERE carrier_key='AEROMEXICO')
        """
    ).dropna()
    figure.add_trace(go.Scatter(x=airports["longitude"], y=airports["latitude"], mode="markers+text", text=airports["airport_iata"], textposition="top center", marker={"color": MAGENTA, "size": 7}, name="Aeropuertos"))
    figure.update_layout(**CHART_LAYOUT, title={"text": "Principales rutas México-Estados Unidos<br><sup>Últimos 12 meses T-100; líneas ponderadas por asientos, mapa esquemático sin fondo externo</sup>", "x": 0.01}, height=560, xaxis_title="Longitud", yaxis_title="Latitud", showlegend=False)
    figure.update_xaxes(gridcolor=GRID)
    figure.update_yaxes(gridcolor=GRID, scaleanchor="x", scaleratio=1)
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    echarts_ranked_bar(routes.head(10), category="market_key", value="asm_miles", title="Top mercados por ASM", subtitle="Últimos 12 meses T-100; mercados bidireccionales")
    metric_context(["asm_total", "load_factor_total"])
    faa = study("faa_category2")
    concentration = study("network_concentration")
    columns = st.columns(2)
    with columns[0]:
        callout(faa["finding_es"], label="Categoría 2 de la FAA")
        st.caption(f"Confianza {faa['confidence']}: {faa['caveat']}")
    with columns[1]:
        callout(concentration["finding_es"], label="Concentración de red")
        st.caption(f"Confianza {concentration['confidence']}: {concentration['caveat']}")
    clusters = query_df("SELECT cluster_name, assignments FROM v_cluster_summary WHERE exercise='routes' ORDER BY assignments DESC")
    ranked_bar(clusters, category="cluster_name", value="assignments", title="Perfiles de ruta", subtitle="407 observaciones ruta-año; k=3, silueta 0.325, ARI 1.000")
    source_note("BTS T-100. La visualización cubre la red México-Estados Unidos, no toda la red global de Aeroméxico.")
