"""Reusable category and scatter comparisons."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboard.theme import CHART_LAYOUT, CARRIER_COLORS, GRID


def ranked_bar(frame: pd.DataFrame, *, category: str, value: str, title: str, subtitle: str, value_format: str = ",.0f") -> None:
    data = frame.sort_values(value, ascending=True)
    figure = go.Figure(go.Bar(
        x=data[value], y=data[category], orientation="h", marker={"color": "#0B3A66"},
        text=data[value], texttemplate=f"%{{text:{value_format}}}", textposition="outside",
    ))
    figure.update_layout(**CHART_LAYOUT, title={"text": f"{title}<br><sup>{subtitle}</sup>", "x": 0.01}, height=max(340, 34 * len(data) + 120), showlegend=False)
    figure.update_xaxes(gridcolor=GRID, rangemode="tozero")
    figure.update_yaxes(title=None)
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})


def carrier_scatter(frame: pd.DataFrame, *, x: str, y: str, size: str, title: str, subtitle: str) -> None:
    figure = px.scatter(
        frame, x=x, y=y, size=size, color="carrier_key", text="carrier_key",
        color_discrete_map=CARRIER_COLORS, hover_data=["period_id", "load_factor"],
    )
    maximum = float(max(frame[x].max(), frame[y].max())) if len(frame) else 1
    figure.add_shape(type="line", x0=0, y0=0, x1=maximum, y1=maximum, line={"color": "#5E6B78", "dash": "dash"})
    figure.update_traces(textposition="top center")
    figure.update_layout(**CHART_LAYOUT, title={"text": f"{title}<br><sup>{subtitle}</sup>", "x": 0.01}, height=500)
    figure.update_xaxes(gridcolor=GRID, title="CASK reportado (¢ por ASK-km)", rangemode="tozero")
    figure.update_yaxes(gridcolor=GRID, title="RASK reportado (¢ por ASK-km)", rangemode="tozero")
    st.plotly_chart(figure, width="stretch", config={"displayModeBar": False})
