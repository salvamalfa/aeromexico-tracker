"""Public entrypoint for the approved Aeromexico Tracker HTML dashboard."""

from pathlib import Path

import streamlit as st


DASHBOARD_PATH = Path(__file__).parent / "static" / "aeromexico_tracker.html"


def main() -> None:
    st.set_page_config(
        page_title="Aeroméxico Tracker",
        page_icon="✈",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    st.markdown(
        """
        <style>
        [data-testid="stHeader"], [data-testid="stToolbar"],
        [data-testid="stDecoration"], [data-testid="stStatusWidget"],
        footer { display: none !important; }
        .stMainBlockContainer {
            max-width: none !important;
            padding: 0 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.iframe(
        DASHBOARD_PATH,
        height="content",
        tab_index=0,
    )


if __name__ == "__main__":
    main()
