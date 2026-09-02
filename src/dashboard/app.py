"""Aeromexico Tracker Streamlit entrypoint and eleven-page navigation."""

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
from src.dashboard.navigation import PAGE_SPECS, render_callable


def main() -> None:
    st.set_page_config(
        page_title="Aeroméxico Tracker",
        page_icon="✈",
        layout="wide",
        initial_sidebar_state="auto",
    )
    load_css()

    st.sidebar.markdown("<div class='brand-kicker'>AERO · NYSE / BMV</div>", unsafe_allow_html=True)
    st.sidebar.markdown("# Aeroméxico Tracker")
    st.sidebar.caption("Datos públicos · análisis trimestral · actualización reproducible")

    pages = [
        st.Page(
            render_callable(spec),
            title=spec.title,
            icon=spec.icon,
            url_path=spec.url_path,
            default=spec.default,
        )
        for spec in PAGE_SPECS
    ]
    navigation = st.navigation(pages, position="sidebar")
    navigation.run()
    render_footer()


if __name__ == "__main__":
    main()
