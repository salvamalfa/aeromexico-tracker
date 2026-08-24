"""Seven high-value Stage 7 business studies."""

from __future__ import annotations

import pandas as pd

from src.analytics.studies.event_study import run as event_study
from src.analytics.studies.faa_category2 import run as faa_category2
from src.analytics.studies.fuel_sensitivity import run as fuel_sensitivity
from src.analytics.studies.network_concentration import run as network_concentration
from src.analytics.studies.peer_comparison import run as peer_comparison
from src.analytics.studies.route_seasonality import run as route_seasonality
from src.analytics.studies.spread import run as spread


def run_all(model_run_id: str) -> tuple[pd.DataFrame, dict[str, object]]:
    functions = [spread, faa_category2, peer_comparison, fuel_sensitivity, event_study, route_seasonality, network_concentration]
    rows: list[dict[str, object]] = []
    details: dict[str, object] = {}
    for function in functions:
        row, detail = function()
        row["model_run_id"] = model_run_id
        rows.append(row)
        details[row["study_key"]] = detail
    return pd.DataFrame(rows), details

