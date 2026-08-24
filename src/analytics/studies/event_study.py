"""Raw-return event study around Aeromexico result publications."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.analytics.common import warehouse_query


def run() -> tuple[dict[str, object], dict[str, object]]:
    market = warehouse_query("SELECT date, return_1d FROM fact_market_data WHERE carrier_key='AEROMEXICO' ORDER BY date").dropna()
    events = warehouse_query(
        """SELECT event_date, title FROM dim_events
        WHERE event_category='earnings'
        ORDER BY event_date"""
    )
    market["date"] = pd.to_datetime(market["date"]).dt.tz_localize(None)
    event_rows = []
    for event in events.itertuples(index=False):
        event_date = pd.Timestamp(event.event_date).tz_localize(None)
        if market.empty:
            continue
        distance = (market["date"] - event_date).abs()
        nearest_position = int(distance.to_numpy().argmin())
        if distance.iloc[nearest_position].days > 7:
            continue
        window = market.iloc[max(0, nearest_position - 5):nearest_position + 6]
        if len(window) < 6:
            continue
        cumulative = float(np.prod(1 + window["return_1d"].fillna(0)) - 1)
        event_rows.append({"event_date": event_date, "title": event.title, "return_window": cumulative, "sessions": len(window)})
    if event_rows:
        average = float(np.mean([row["return_window"] for row in event_rows]))
        finding = f"En {len(event_rows)} publicaciones con historia bursátil suficiente, el retorno bruto promedio de AERO en ±5 sesiones fue {average:+.1%}."
        confidence = "baja"
    else:
        average = np.nan
        finding = "No hay suficientes publicaciones posteriores al relisting con una ventana completa de ±5 sesiones; no se reporta reacción promedio."
        confidence = "no disponible"
    return {
        "study_key": "earnings_event_study", "title_es": "Reacción bursátil a resultados",
        "finding_es": finding, "estimate": average, "unit": "cumulative_return",
        "period_id": str(market["date"].max().date()) if len(market) else "unavailable", "comparison": "raw return, -5 to +5 sessions",
        "confidence": confidence, "caveat": "La historia bursátil de AERO comienza con el relisting de 2025 y gold no contiene un índice de mercado; son retornos brutos, no retornos anormales.",
        "source_tables": "fact_market_data|dim_events",
    }, {"events": event_rows}
