"""Small, offline ECharts components for high-density interactive views."""

from __future__ import annotations

import pandas as pd
from streamlit_echarts import st_echarts

from src.dashboard.theme import AERO_BLUE, GRID, INK, MUTED


def ranked_bar(
    frame: pd.DataFrame,
    *,
    category: str,
    value: str,
    title: str,
    subtitle: str,
    height: int = 430,
) -> None:
    """Render a labelled horizontal ranking with no network dependencies."""

    clean = frame[[category, value]].dropna().sort_values(value).copy()
    options = {
        "animationDuration": 450,
        "title": {
            "text": title,
            "subtext": subtitle,
            "left": 4,
            "textStyle": {"color": INK, "fontSize": 17, "fontWeight": 650},
            "subtextStyle": {"color": MUTED, "fontSize": 11},
        },
        "tooltip": {"trigger": "axis", "axisPointer": {"type": "shadow"}},
        "grid": {"left": 8, "right": 34, "top": 78, "bottom": 20, "containLabel": True},
        "xAxis": {
            "type": "value",
            "axisLine": {"show": False},
            "splitLine": {"lineStyle": {"color": GRID}},
            "axisLabel": {"color": MUTED},
        },
        "yAxis": {
            "type": "category",
            "data": clean[category].astype(str).tolist(),
            "axisLine": {"show": False},
            "axisTick": {"show": False},
            "axisLabel": {"color": INK},
        },
        "series": [{
            "type": "bar",
            "data": clean[value].astype(float).round(2).tolist(),
            "itemStyle": {"color": AERO_BLUE, "borderRadius": [0, 5, 5, 0]},
            "label": {"show": True, "position": "right", "color": INK},
        }],
    }
    st_echarts(options=options, height=f"{height}px", key=f"echarts-{category}-{value}-{title}")
