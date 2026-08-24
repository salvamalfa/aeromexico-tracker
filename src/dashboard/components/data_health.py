"""Real data-health status, never a decorative score."""

from __future__ import annotations

import pandas as pd
import streamlit as st


def source_health_table(frame: pd.DataFrame) -> None:
    display = frame.copy()
    display["first_date"] = pd.to_datetime(display["first_date"]).dt.strftime("%Y-%m-%d")
    display["last_date"] = pd.to_datetime(display["last_date"]).dt.strftime("%Y-%m-%d")
    display["last_ingested_at"] = pd.to_datetime(display["last_ingested_at"], utc=True).dt.strftime("%Y-%m-%d %H:%M UTC")
    display = display.rename(columns={
        "source_system": "Fuente", "rows": "Filas", "carriers": "Aerolíneas",
        "first_date": "Desde", "last_date": "Hasta", "last_ingested_at": "Última ingesta",
        "issue_count": "Issues", "age_days": "Antigüedad (días)",
    })
    st.dataframe(display, hide_index=True, width="stretch")
