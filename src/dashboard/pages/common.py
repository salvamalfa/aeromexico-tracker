"""Shared page-level data shaping."""

from __future__ import annotations

import pandas as pd

from src.dashboard.data import query_df


def period_date(period_id: str) -> pd.Timestamp:
    value = str(period_id)
    if "M" in value:
        return pd.Timestamp(f"{value[:4]}-{value[-2:]}-01")
    if "Q" in value:
        return pd.Timestamp(int(value[:4]), int(value[-1]) * 3, 1) + pd.offsets.MonthEnd(0)
    return pd.Timestamp(f"{value[:4]}-12-31")


def aeromexico_quarters() -> pd.DataFrame:
    long = query_df(
        """
        SELECT period_id, metric_key, value, source_system
        FROM v_carrier_default
        WHERE carrier_key='AEROMEXICO' AND period_type='quarter' AND segment='total'
        ORDER BY period_id, metric_key
        """
    )
    wide = long.pivot_table(index="period_id", columns="metric_key", values="value", aggfunc="first").reset_index()
    wide["date"] = wide["period_id"].map(period_date)
    return wide.sort_values("period_id").reset_index(drop=True)


def study(study_key: str) -> pd.Series:
    frame = query_df("SELECT * FROM fact_study_results WHERE study_key=?", (study_key,))
    if frame.empty:
        raise KeyError(study_key)
    return frame.iloc[0]
