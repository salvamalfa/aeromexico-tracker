"""Metric card whose business interpretation is sourced from dim_metric."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
import streamlit as st

from src.dashboard.data import metric_definition


def format_value(value: float | None, definition: dict[str, Any]) -> str:
    if value is None or pd.isna(value):
        return "N/D"
    unit = str(definition["unit_normalized"])
    number = float(value)
    if unit == "fraction":
        return f"{number:.1%}"
    if unit == "usd":
        return f"US${number / 1_000_000:,.1f} M"
    if "cents" in unit:
        return f"{number:.2f} ¢"
    if unit in {"count", "miles", "kilometers", "miles_per_aircraft"}:
        if abs(number) >= 1_000_000:
            return f"{number / 1_000_000:,.1f} M"
        return f"{number:,.0f}"
    return f"{number:,.3f}" if abs(number) < 10 else f"{number:,.1f}"


def _delta(value: float | None) -> str | None:
    if value is None or pd.isna(value) or not math.isfinite(float(value)):
        return None
    return f"{float(value):+.1%} interanual"


def kpi_card(
    metric_key: str,
    value: float | None,
    *,
    period_id: str,
    yoy_change: float | None = None,
    source: str,
) -> None:
    definition = metric_definition(metric_key)
    required = ["business_interpretation_up", "business_interpretation_down", "why_it_matters"]
    missing = [field for field in required if pd.isna(definition[field]) or not str(definition[field]).strip()]
    if missing:
        raise ValueError(f"{metric_key} cannot be displayed; missing dim_metric fields: {missing}")
    higher = definition["higher_is_better"]
    delta_color = "off" if pd.isna(higher) else ("normal" if bool(higher) else "inverse")
    with st.container(border=True):
        st.caption(period_id)
        st.metric(
            str(definition["metric_name_es"]),
            format_value(value, definition),
            _delta(yoy_change),
            delta_color=delta_color,
        )
        st.markdown(f"<p class='kpi-why'>{definition['why_it_matters']}</p>", unsafe_allow_html=True)
        with st.expander("Cómo leer esta métrica"):
            st.markdown(f"**Si sube:** {definition['business_interpretation_up']}")
            st.markdown(f"**Si baja:** {definition['business_interpretation_down']}")
            st.markdown(f"**Cuidado:** {definition['caveats']}")
            formula = definition.get("formula")
            if pd.notna(formula):
                st.markdown(f"**Fórmula:** `{formula}`")
            st.caption(f"Fuente: {source}")


def metric_context(metric_keys: list[str], *, label: str = "Qué significan estas métricas") -> None:
    definitions = [metric_definition(key) for key in metric_keys]
    for definition in definitions:
        required = ["business_interpretation_up", "business_interpretation_down", "why_it_matters"]
        if any(pd.isna(definition[field]) or not str(definition[field]).strip() for field in required):
            raise ValueError(f"Incomplete dim_metric interpretation: {definition['metric_key']}")
    with st.expander(label):
        for definition in definitions:
            st.markdown(f"**{definition['metric_name_es']}** — {definition['why_it_matters']}")
            st.caption(f"Si sube: {definition['business_interpretation_up']} · Si baja: {definition['business_interpretation_down']} · Cuidado: {definition['caveats']}")
