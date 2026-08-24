"""Data health and epistemic honesty page."""

from __future__ import annotations

import plotly.express as px
import streamlit as st

from src.dashboard.components.data_health import source_health_table
from src.dashboard.components.narrative import callout
from src.dashboard.components.ui import page_header, source_note
from src.dashboard.data import load_gold_table, query_df
from src.dashboard.theme import AERO_BLUE, MAGENTA


def render() -> None:
    page_header("Salud de los datos", "¿Qué tan confiable, completo y reciente es lo que aparece en las otras páginas?", eyebrow="09 · Evidencia antes que decoración")
    callout("Esta página no produce una calificación cosmética. Muestra antigüedad, cobertura, discrepancias y faltantes para que cada conclusión se lea con el peso correcto.")
    freshness = query_df("SELECT * FROM v_dashboard_source_freshness ORDER BY source_system")
    source_health_table(freshness)

    st.subheader("Cobertura de métricas prioritarias")
    coverage = load_gold_table("fact_dashboard_coverage")
    carriers = ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS", "DELTA", "RYANAIR"]
    selected_carriers = st.multiselect("Aerolíneas", carriers, default=["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"])
    filtered = coverage[coverage["carrier_key"].isin(selected_carriers) & coverage["segment"].eq("total") & coverage["metric_key"].isin(["passengers_afac", "total_revenue", "asm_total", "load_factor_total", "rask", "cask", "casm_ex_fuel"])].copy()
    matrix = filtered.pivot_table(index="metric_key", columns="carrier_key", values="coverage_pct", aggfunc="max")
    if len(matrix):
        figure = px.imshow(matrix, text_auto=".0%", aspect="auto", zmin=0, zmax=1, color_continuous_scale=[[0, "#F7E7EF"], [0.5, "#DCEAF5"], [1, AERO_BLUE]])
        figure.update_layout(title="Cobertura entre el primer y último periodo observado", height=420, coloraxis_colorbar={"tickformat": ".0%"})
        st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})

    issues = load_gold_table("fact_data_quality_issues").sort_values(["severity", "period_id"], na_position="last")
    st.subheader(f"Issues abiertos · {len(issues)}")
    st.dataframe(issues[["severity", "issue_type", "source_system", "carrier_key", "period_id", "metric_key", "difference_pct", "detail"]].rename(columns={"severity": "Severidad", "issue_type": "Tipo", "source_system": "Fuente", "carrier_key": "Aerolínea", "period_id": "Periodo", "metric_key": "Métrica", "difference_pct": "Diferencia", "detail": "Detalle"}), hide_index=True, width="stretch")

    restatements = query_df("SELECT carrier_key, period_id, metric_key, source_system, restatement_count, valid_from, valid_to, is_current FROM v_restatements ORDER BY valid_from DESC")
    st.subheader(f"Restatements registrados · {len(restatements)}")
    st.dataframe(restatements, hide_index=True, width="stretch")
    derivation = query_df("SELECT is_derived, COUNT(*) AS rows FROM v_carrier_default GROUP BY is_derived ORDER BY is_derived")
    st.caption("Composición actual de facts preferidos")
    st.dataframe(derivation.rename(columns={"is_derived": "Es derivada", "rows": "Filas"}), hide_index=True)
    st.warning("No conocido hoy: etapa promedio global comparable, textos de peers para NLP y guidance estructurado. Estos huecos permanecen como huecos; no se convierten en cero.")
    source_note("fact_data_quality_issues, fact_dashboard_coverage, v_restatements y v_data_health; estado real del pipeline local.")
