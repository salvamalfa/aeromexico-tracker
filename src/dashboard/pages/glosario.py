"""Searchable metric glossary page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard.components.ui import page_header, source_note
from src.dashboard.data import metric_catalog


def render() -> None:
    page_header("Glosario", "¿Qué significa cada KPI, cómo se calcula y qué puede hacer que se interprete mal?", eyebrow="11 · Leer antes de comparar")
    catalog = metric_catalog()
    query = st.text_input("Buscar métrica", placeholder="Ej. CASK, ocupación, ingreso…").strip().lower()
    dashboard_only = st.toggle("Solo métricas usadas en el dashboard", value=True)
    if dashboard_only:
        catalog = catalog[catalog["is_dashboard_metric"] | catalog["metric_key"].isin(["total_revenue", "ebitdar_margin", "operating_income", "net_income", "cash_and_cash_equivalents", "total_assets", "total_liabilities", "total_equity"])]
    if query:
        mask = catalog.apply(lambda row: query in " ".join(str(value).lower() for value in row.values), axis=1)
        catalog = catalog[mask]
    st.caption(f"{len(catalog)} definiciones")
    for row in catalog.itertuples(index=False):
        with st.expander(f"{row.metric_name_es} · {row.metric_key}"):
            st.markdown(f"**Por qué importa:** {row.why_it_matters}")
            st.markdown(f"**Si sube:** {row.business_interpretation_up}")
            st.markdown(f"**Si baja:** {row.business_interpretation_down}")
            st.markdown(f"**Fórmula:** `{row.formula}`" if pd.notna(row.formula) else "**Fórmula:** valor reportado por la fuente")
            st.markdown(f"**Unidad:** `{row.unit_normalized}`")
            st.markdown(f"**Cuidado:** {row.caveats}")
            if pd.notna(row.typical_range_network) or pd.notna(row.typical_range_ulcc):
                network_range = row.typical_range_network if pd.notna(row.typical_range_network) else "N/D"
                ulcc_range = row.typical_range_ulcc if pd.notna(row.typical_range_ulcc) else "N/D"
                st.caption(f"Referencia network: {network_range} · ULCC: {ulcc_range}")
    source_note("dim_metric, generado desde el glosario del plan y los contratos versionados. Ninguna explicación se hardcodea en una tarjeta KPI.")
