"""Competitive positioning page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard.components.comparison_chart import carrier_scatter
from src.dashboard.components.kpi_card import metric_context
from src.dashboard.components.metric_chart import time_series_chart
from src.dashboard.components.narrative import callout
from src.dashboard.components.ui import page_header, source_note, unavailable
from src.dashboard.data import query_df
from src.dashboard.pages.common import period_date


def render() -> None:
    page_header("Competencia", "¿Dónde se posiciona Aeroméxico frente a las aerolíneas que compiten por el mismo pasajero?", eyebrow="04 · Network frente a ULCC")
    st.warning("Comparabilidad: Aeroméxico, Volaris, Viva y Ryanair reportan bajo IFRS; Delta usa US-GAAP. Ryanair cierra su año fiscal en marzo. La etapa promedio global no está disponible, por lo que RASK y CASK no están ajustados por stage length.")

    unit = query_df(
        """
        SELECT carrier_key, period_id,
               MAX(value) FILTER (WHERE metric_key='rask') AS rask,
               MAX(value) FILTER (WHERE metric_key='cask') AS cask,
               MAX(value) FILTER (WHERE metric_key='asm_total') AS asm_total,
               MAX(value) FILTER (WHERE metric_key='load_factor_total') AS load_factor
        FROM v_carrier_default
        WHERE period_type='quarter' AND segment='total' AND carrier_key IN ('AEROMEXICO','VOLARIS','VIVA_AEROBUS')
        GROUP BY carrier_key, period_id
        ORDER BY period_id, carrier_key
        """
    ).dropna(subset=["rask", "cask", "asm_total"])
    carrier_scatter(unit, x="cask", y="rask", size="asm_total", title="Posicionamiento de ingreso y costo unitario", subtitle="Cada punto es una aerolínea-trimestre; diagonal = equilibrio unitario, sin ajuste por etapa")
    metric_context(["rask", "cask", "asm_total", "load_factor_total"])

    shares = query_df(
        """
        SELECT carrier_key, period_id, market_share
        FROM v_market_share_mx
        WHERE segment='total' AND carrier_key IN ('AEROMEXICO','VOLARIS','VIVA_AEROBUS')
        ORDER BY period_id, carrier_key
        """
    )
    share_wide = shares.pivot_table(index="period_id", columns="carrier_key", values="market_share", aggfunc="first").reset_index()
    share_wide["date"] = share_wide["period_id"].map(period_date)
    time_series_chart(share_wide, x="date", series={key: key.replace("_", " ").title() for key in ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"]}, title="Participación del mercado mexicano", subtitle="Pasajeros AFAC totales; denominador incluye aerolíneas no mapeadas individualmente", y_title="Participación", percent=True)
    metric_context(["passengers_afac"])

    cluster = query_df("SELECT * FROM v_cluster_summary WHERE exercise='routes' ORDER BY assignments DESC")
    st.subheader("Qué perfiles de ruta aparecen en los datos")
    st.dataframe(cluster[["cluster_name", "assignments", "silhouette", "stability_ari"]].rename(columns={"cluster_name": "Perfil", "assignments": "Ruta-año", "silhouette": "Silueta", "stability_ari": "Estabilidad ARI"}), hide_index=True, width="stretch")
    unavailable("Clustering de aerolíneas no publicado", "Sin etapa promedio global comparable, un mapa de costos ajustados sería una falsa precisión.")
    callout("Aeroméxico compite como network carrier: una estructura de costo más alta no es automáticamente peor si el ingreso unitario y el valor de conexión/premium la compensan.")
    source_note("AFAC, comunicados trimestrales y dim_carrier. Las advertencias contables y de etapa forman parte de la comparación, no una nota opcional.")
