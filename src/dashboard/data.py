"""Cached, offline-only dashboard data access."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Any

import duckdb
import pandas as pd
import streamlit as st

from src.config import PATHS
from src.transform.stage6_contracts import table_definitions


_QUERY_LOCK = threading.RLock()
_DASHBOARD_MAX_STAGE = 9
_MONTH_ABBR_ES = (
    "",
    "ene",
    "feb",
    "mar",
    "abr",
    "may",
    "jun",
    "jul",
    "ago",
    "sep",
    "oct",
    "nov",
    "dic",
)


@st.cache_data(ttl=3600, show_spinner=False)
def load_gold_table(name: str) -> pd.DataFrame:
    if name not in table_definitions(max_stage=_DASHBOARD_MAX_STAGE):
        raise KeyError(f"Undeclared gold table: {name}")
    path = PATHS.gold / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"Dashboard gold table is missing: {path}")
    return pd.read_parquet(path)


@st.cache_resource(show_spinner="Preparando datos locales…")
def connection() -> duckdb.DuckDBPyConnection:
    database = duckdb.connect(":memory:")
    available: set[str] = set()
    for name in table_definitions(max_stage=_DASHBOARD_MAX_STAGE):
        path = (PATHS.gold / f"{name}.parquet").resolve()
        if not path.exists():
            continue
        safe_path = path.as_posix().replace("'", "''")
        database.execute(f'CREATE OR REPLACE VIEW "{name}" AS SELECT * FROM read_parquet(\'{safe_path}\')')
        available.add(name)
    for sql_path in sorted((PATHS.root / "sql" / "gold").glob("*.sql")):
        sql = sql_path.read_text(encoding="utf-8")
        if sql_path.name.startswith("07_") and "fact_forecasts" not in available:
            continue
        if sql_path.name.startswith("08_") and "fact_route_traffic_summary" not in available:
            continue
        database.execute(sql)
    return database


@st.cache_data(ttl=3600, show_spinner=False)
def query_df(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    with _QUERY_LOCK:
        return connection().execute(sql, list(params)).df()


@st.cache_data(ttl=3600, show_spinner=False)
def metric_catalog() -> pd.DataFrame:
    return load_gold_table("dim_metric").sort_values("display_order").reset_index(drop=True)


def metric_definition(metric_key: str) -> dict[str, Any]:
    frame = metric_catalog()
    row = frame[frame["metric_key"].eq(metric_key)]
    if row.empty:
        raise KeyError(f"Metric is missing from dim_metric: {metric_key}")
    return row.iloc[0].to_dict()


def latest_quarter() -> str:
    frame = query_df("SELECT MAX(period_id) AS period_id FROM v_aeromexico_quarterly")
    return str(frame.iloc[0, 0])


def events() -> pd.DataFrame:
    return query_df("SELECT * FROM dim_events ORDER BY event_date")


def data_as_of() -> str:
    # A quarter or month can be represented by its period-end date while it is
    # still in progress.  Using that boundary made the footer claim a future
    # data date (for example, 30 Sep on 1 Sep).  The latest preserved public
    # artifact is the honest, reproducible cutoff for the tracker itself.
    frame = query_df(
        "SELECT MAX(CAST(downloaded_at AS DATE)) AS date FROM dim_source_artifact"
    )
    value = pd.to_datetime(frame.iloc[0, 0])
    if pd.isna(value):
        return "sin fecha"
    return f"{value.day:02d} {_MONTH_ABBR_ES[value.month]} {value.year}"


def table_path(name: str) -> Path:
    return PATHS.gold / f"{name}.parquet"
