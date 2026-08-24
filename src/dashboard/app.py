"""Aeromexico Tracker Streamlit entrypoint and ten-page navigation."""

from __future__ import annotations

from pathlib import Path
import sys

# Streamlit executes this file from its own directory locally and in Community
# Cloud. Keep the repository root importable without relying on shell state.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from src.dashboard.components.ui import load_css, render_footer
from src.dashboard.pages import (
    capacidad_demanda,
    competencia,
    economia_unitaria,
    finanzas,
    forecast,
    glosario,
    lenguaje_reportes,
    red_rutas,
    resumen,
    salud_datos,
)


def main() -> None:
    st.set_page_config(
        page_title="Aeroméxico Tracker",
        page_icon="✈",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    load_css()

    st.sidebar.markdown("<div class='brand-kicker'>AERO · NYSE / BMV</div>", unsafe_allow_html=True)
    st.sidebar.markdown("# Aeroméxico Tracker")
    st.sidebar.caption("Datos públicos · análisis trimestral · actualización reproducible")

    navigation = st.navigation(
        [
            st.Page(resumen.render, title="Resumen ejecutivo", icon="🏠", url_path="resumen", default=True),
            st.Page(economia_unitaria.render, title="Economía unitaria", icon="↔️", url_path="economia-unitaria"),
            st.Page(capacidad_demanda.render, title="Capacidad y demanda", icon="📈", url_path="capacidad-demanda"),
            st.Page(competencia.render, title="Competencia", icon="🧭", url_path="competencia"),
            st.Page(red_rutas.render, title="Red y rutas", icon="🗺️", url_path="red-rutas"),
            st.Page(finanzas.render, title="Finanzas", icon="💼", url_path="finanzas"),
            st.Page(forecast.render, title="Forecast", icon="🔭", url_path="forecast"),
            st.Page(lenguaje_reportes.render, title="Lenguaje de reportes", icon="💬", url_path="lenguaje"),
            st.Page(salud_datos.render, title="Salud de datos", icon="🩺", url_path="salud-datos"),
            st.Page(glosario.render, title="Glosario", icon="📚", url_path="glosario"),
        ],
        position="sidebar",
    )
    navigation.run()
    render_footer()


if __name__ == "__main__":
    main()
