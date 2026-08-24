"""Identify summer- and winter-weighted Aeromexico routes."""

from __future__ import annotations

import pandas as pd

from src.analytics.common import warehouse_query


def run() -> tuple[dict[str, object], dict[str, object]]:
    frame = warehouse_query(
        """
        SELECT r.market_key, f.period_id, SUM(f.passengers) AS passengers
        FROM fact_route_traffic f JOIN dim_route r USING (route_key)
        WHERE f.carrier_key='AEROMEXICO'
        GROUP BY ALL ORDER BY period_id, market_key
        """
    )
    latest_year = int(frame["period_id"].str[:4].max())
    complete = frame[frame["period_id"].str[:4].astype(int).between(latest_year - 3, latest_year - 1)].copy()
    complete["month"] = complete["period_id"].str[-2:].astype(int)
    route = complete.groupby("market_key").filter(lambda group: group["period_id"].nunique() >= 24)
    overall = route.groupby("market_key")["passengers"].mean()
    summer = route[route["month"].isin([6, 7, 8])].groupby("market_key")["passengers"].mean() / overall
    winter = route[route["month"].isin([12, 1, 2])].groupby("market_key")["passengers"].mean() / overall
    result = pd.concat([summer.rename("summer_index"), winter.rename("winter_index")], axis=1).dropna()
    top_summer = result.nlargest(5, "summer_index").reset_index().to_dict("records")
    top_winter = result.nlargest(5, "winter_index").reset_index().to_dict("records")
    leader = top_summer[0] if top_summer else {"market_key": "unavailable", "summer_index": float("nan")}
    finding = f"{leader['market_key']} es la ruta con mayor sesgo de verano entre las rutas con al menos 24 meses: su índice estacional es {leader['summer_index']:.2f} frente a su mes promedio."
    return {
        "study_key": "route_seasonality", "title_es": "Estacionalidad de la red",
        "finding_es": finding, "estimate": float(leader["summer_index"]), "unit": "seasonal_index",
        "period_id": f"{latest_year-3}-{latest_year-1}", "comparison": "June-August versus route monthly average",
        "confidence": "alta", "caveat": "T-100 cubre segmentos México-Estados Unidos, no la red global completa.",
        "source_tables": "fact_route_traffic|dim_route",
    }, {"top_summer": top_summer, "top_winter": top_winter, "routes": len(result)}
