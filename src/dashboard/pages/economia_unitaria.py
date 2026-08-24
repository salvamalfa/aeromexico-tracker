"""Unit economics page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.dashboard.components.kpi_card import kpi_card, metric_context
from src.dashboard.components.metric_chart import time_series_chart
from src.dashboard.components.narrative import callout
from src.dashboard.components.ui import page_header, source_note, unavailable
from src.dashboard.components.waterfall import spread_waterfall
from src.dashboard.data import load_gold_table
from src.dashboard.pages.common import aeromexico_quarters, study


def render() -> None:
    page_header("Economía unitaria", "¿Aeroméxico gana o pierde más por cada asiento ofrecido, y por qué?", eyebrow="02 · La ecuación más importante")
    callout("RASK dice cuánto ingresa cada unidad de capacidad; CASK dice cuánto cuesta. La diferencia entre ambos es el margen unitario: leer uno sin el otro cuenta media historia.")
    quarters = aeromexico_quarters()
    use_adjusted = st.toggle("Ajustar por etapa promedio", value=False)
    if use_adjusted and quarters[["sla_rask", "sla_cask"]].notna().any().any():
        columns = {"sla_rask": "RASK ajustado", "sla_cask": "CASK ajustado"}
    else:
        if use_adjusted:
            unavailable("Ajuste por etapa no disponible", "La etapa promedio global comparable no existe en las fuentes estructuradas; no se sustituyó con la subred T-100.")
        columns = {"rask": "RASK", "cask": "CASK"}
    plotted = quarters.dropna(subset=list(columns)).copy()
    time_series_chart(plotted, x="date", series=columns, title="Ingreso y costo por unidad de capacidad", subtitle="Misma unidad; vista reportada por defecto", y_title="¢ por ASK-km")
    metric_context(list(columns) + ["unit_margin"])

    st.subheader("Qué movió el spread en el último trimestre")
    decomposition = load_gold_table("fact_spread_decomposition")
    spread = quarters.dropna(subset=["rask", "cask"]).copy()
    spread["spread"] = spread["rask"] - spread["cask"]
    start = float(spread.loc[spread["period_id"].eq(decomposition["comparison_period_id"].iloc[0]), "spread"].iloc[0])
    end = float(spread.loc[spread["period_id"].eq(decomposition["period_id"].iloc[0]), "spread"].iloc[0])
    spread_waterfall(decomposition, start_value=start, end_value=end)
    st.warning("FX no se identifica por separado con las divulgaciones disponibles; permanece dentro del residual estructural.")

    latest = quarters.iloc[-1]
    cards = st.columns(2)
    with cards[0]:
        kpi_card("load_factor_total", latest.get("load_factor_total"), period_id=latest["period_id"], source="Comunicado de resultados")
    with cards[1]:
        kpi_card("break_even_load_factor", latest.get("break_even_load_factor"), period_id=latest["period_id"], source="Derivación gold con RASK/CASK")
    fuel = study("fuel_sensitivity")
    callout(fuel["finding_es"], label="Sensibilidad al combustible")
    source_note("v_carrier_default, fact_spread_decomposition y fact_study_results. La sensibilidad tiene confianza baja por siete trimestres utilizables.")
