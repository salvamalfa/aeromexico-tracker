"""Deterministic Spanish narratives generated from metric conditions."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def executive_narrative(current: pd.Series, prior_year: pd.Series | None) -> str:
    revenue_growth = None if prior_year is None else current.get("total_revenue", float("nan")) / prior_year.get("total_revenue", float("nan")) - 1
    capacity_growth = current.get("yoy_growth_asm_total", float("nan"))
    margin = current.get("operating_margin", float("nan"))
    if pd.notna(revenue_growth) and pd.notna(capacity_growth) and revenue_growth > 0.10 and abs(capacity_growth) < 0.02:
        lead = "Los ingresos crecieron con capacidad casi plana: la mejora vino más de monetización y mezcla que de poner muchos más asientos en el mercado."
    elif pd.notna(revenue_growth) and revenue_growth > 0:
        lead = "Los ingresos avanzaron, aunque el balance entre precio, capacidad y ocupación determina si ese crecimiento creó valor."
    else:
        lead = "El trimestre exige mirar más allá del ingreso: capacidad, ocupación y costo unitario explican la calidad del resultado."
    margin_text = f" El margen operativo fue {margin:.1%}." if pd.notna(margin) else ""
    return lead + margin_text


def callout(text: str, *, label: str = "Lectura de negocio") -> None:
    st.markdown(f"<div class='narrative-callout'><span>{label}</span><p>{text}</p></div>", unsafe_allow_html=True)
