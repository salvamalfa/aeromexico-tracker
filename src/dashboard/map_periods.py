"""Map periods supported by retained inputs, independent of financial quarters.

Capacity-only captures never activate an estimate month. No source is fetched,
model fitted, or approval written here.
"""

from __future__ import annotations

MONTHS = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
          "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def period_months(period: str) -> list[str]:
    if len(period) == 7 and period[4] == "M" and 1 <= int(period[5:]) <= 12:
        return [period]
    if len(period) == 6 and period[4] == "Q" and period[5] in "1234":
        first = (int(period[5]) - 1) * 3 + 1
        return [f"{period[:4]}M{month:02d}" for month in range(first, first + 3)]
    raise ValueError(f"Invalid map period: {period}")


def period_label(period: str) -> str:
    period_months(period)
    return (f"{MONTHS[int(period[5:]) - 1]} {period[:4]}" if "M" in period
            else f"{period[-1]}T{period[2:4]}")


def retained_map_periods(connection) -> list[dict]:
    """Only dated observations/schedules and already fitted historical outputs."""
    tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    months = set()
    for table in (
        "fact_route_traffic_summary", "fact_international_route_observations",
        "fact_aicm_international_scheduled_route_movements",
        "fact_route_carrier_international_estimate",
    ):
        if table in tables:
            months.update(str(row[0]) for row in connection.execute(
                f"SELECT DISTINCT period_id FROM {table}"
            ).fetchall())
    months = {month for month in months if len(month) == 7 and month[4] == "M"}
    quarters = {f"{month[:4]}Q{(int(month[5:]) - 1) // 3 + 1}" for month in months}
    return [{"period_id": period, "period_label": period_label(period),
             "expected_months": period_months(period)} for period in sorted(months | quarters)]


def mappable_routes(frame):
    """Keep an absent geography explicit; never invent an airport location."""
    missing = frame[["origin_lat", "origin_lon", "dest_lat", "dest_lon"]].isna().any(axis=1)
    markets = frame.loc[missing, "market_key"].tolist()
    movements = float(frame.loc[missing, "departures"].sum())
    note = (f"Mapa parcial: {movements:g} vuelos sin coordenadas en {', '.join(markets)}. " if markets else "")
    return frame.loc[~missing].copy(), note


def refresh_network_availability(network: dict) -> None:
    """Report temporal availability independently of geographic/source scope.

    Complete means all expected observed months are retained, not that the
    worldwide network or every route is complete. Source limits stay in
    coverage/coverage_by_source and historical eligibility remains unchanged.
    """
    quantified = any(route.get("departures") is not None for route in network.get("routes", []))
    expected = set(network.get("expected_months") or [])
    observed = set(network.get("observed_months") or [])
    network["availability"] = (
        "complete" if quantified and expected and observed == expected
        else "partial" if quantified else "unavailable"
    )
    if quantified and str(network.get("eligibility_reason", "")).startswith("T-100 no contiene"):
        network["eligibility_reason"] = (
            "Hay cifras retenidas de otras fuentes; cobertura parcial por fuente y mes, "
            "sin acreditar red completa ni elegibilidad histórica."
        )
