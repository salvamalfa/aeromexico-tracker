"""Transparent unit-spread decomposition."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.theme import CHART_LAYOUT, GOLD, MAGENTA, MUTED


def spread_waterfall(frame: pd.DataFrame, *, start_value: float, end_value: float) -> None:
    identified = frame[frame["is_identified"]].sort_values("display_order")
    x = [f"Spread {frame['comparison_period_id'].iloc[0]}", *identified["component_name_es"], f"Spread {frame['period_id'].iloc[0]}"]
    y = [start_value, *identified["contribution"], end_value]
    measure = ["absolute", *(["relative"] * len(identified)), "total"]
    figure = go.Figure(go.Waterfall(
        x=x, y=y, measure=measure,
        increasing={"marker": {"color": GOLD}}, decreasing={"marker": {"color": MAGENTA}},
        totals={"marker": {"color": MUTED}}, connector={"line": {"color": "#9AA6B2"}},
        text=[f"{value:+.2f}" for value in y], textposition="outside",
    ))
    figure.update_layout(**CHART_LAYOUT, title={"text": "Cambio del spread unitario<br><sup>Centavos por ASK-km; FX no se identifica por separado</sup>", "x": 0.01}, height=430, showlegend=False)
    figure.update_yaxes(title="¢ por ASK-km", zeroline=True, zerolinecolor="#17212B")
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
