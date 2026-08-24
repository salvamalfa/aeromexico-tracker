"""Time-series chart with consistent carrier colors and event annotations."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.theme import CHART_LAYOUT, CARRIER_COLORS, GRID, MUTED


def time_series_chart(
    frame: pd.DataFrame,
    *,
    x: str,
    series: dict[str, str],
    title: str,
    subtitle: str,
    y_title: str,
    events: pd.DataFrame | None = None,
    height: int = 430,
    percent: bool = False,
) -> None:
    figure = go.Figure()
    for column, label in series.items():
        color = CARRIER_COLORS.get(column, CARRIER_COLORS.get(label.upper(), "#0B3A66"))
        figure.add_trace(go.Scatter(
            x=frame[x], y=frame[column], name=label, mode="lines+markers",
            line={"color": color, "width": 2.5}, marker={"size": 5}, connectgaps=False,
        ))
    if events is not None and len(events):
        for event in events.itertuples(index=False):
            date = pd.Timestamp(event.event_date)
            figure.add_vline(x=date, line_width=1, line_dash="dot", line_color=MUTED, opacity=0.55)
            figure.add_annotation(x=date, y=1, yref="paper", text=str(event.title), showarrow=False, textangle=-90, font={"size": 9, "color": MUTED}, yanchor="top")
    figure.update_layout(**CHART_LAYOUT, title={"text": f"{title}<br><sup>{subtitle}</sup>", "x": 0.01}, height=height, legend={"orientation": "h", "y": 1.08})
    figure.update_xaxes(showgrid=False, title=None)
    figure.update_yaxes(gridcolor=GRID, title=y_title, tickformat=".1%" if percent else None, rangemode="normal" if percent else "tozero")
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
