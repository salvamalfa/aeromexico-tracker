"""Build the separately labelled domestic AICM slot view for Vuelos."""

from __future__ import annotations

import pandas as pd

from src.dashboard.route_entities import AEROMEXICO_ROUTES, RouteEntity


SOURCE_LABEL = "México · AICM, vuelos AM programados"
EXCLUSIVE_LABEL = "AFAC · mercado con Aeroméxico como único operador identificado"
SHARED_LABEL = "AIFA · ruta de Aeroméxico identificada; volumen propio sin desglose"
ESTIMATED_LABEL = "AFAC + AeroDataBox + flota · Grupo Aeroméxico estimado"
ESTIMATED_CARRIERS = {
    "AEROMEXICO": "Aerovías de México",
    "AEROMEXICO_CONNECT": "Aeroméxico Connect",
}
MONTH_NAMES = (
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def load_domestic_monthly_networks(connection, entity: RouteEntity = AEROMEXICO_ROUTES) -> dict[str, dict]:
    """Expose official AICM scheduling months without any paid-provider input."""
    if not entity.aeromexico_layers:
        return {}
    exists = connection.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_name = 'fact_domestic_scheduled_route_movements'"
    ).fetchone()[0]
    if not exists:
        return {}
    periods = [str(row[0]) for row in connection.execute(
        "SELECT DISTINCT period_id FROM fact_domestic_scheduled_route_movements "
        "WHERE observation_status = 'assigned_slot_not_flown' ORDER BY period_id"
    ).fetchall()]
    return load_domestic_networks(connection, [
        {"period_id": period, "period_label": f"{MONTH_NAMES[int(period[5:])]} {period[:4]}",
         "expected_months": [period]} for period in periods
    ], entity=entity)


def load_domestic_networks(
    connection, quarters: list[dict], *, entity: RouteEntity = AEROMEXICO_ROUTES
) -> dict[str, dict]:
    exists = connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'fact_domestic_scheduled_route_movements'"
    ).fetchone()[0]
    # AICM slots, AIFA single-operator markets and AIFA presence describe
    # Grupo Aeroméxico only; other entities never inherit them.
    am_layers = entity.aeromexico_layers
    observations = connection.execute(
        "SELECT * FROM fact_domestic_scheduled_route_movements WHERE observation_status = 'assigned_slot_not_flown'"
    ).df() if exists and am_layers else pd.DataFrame()
    # AFAC city-pair totals attributed through a roster are inferences, not
    # observed company flights. Preserve their Gold history, exclude them here.
    if observations.empty:
        return {}
    airports = connection.execute("SELECT * FROM dim_airport").df().set_index("airport_iata")

    def endpoint(code: str) -> dict:
        airport = airports.loc[code]
        if pd.isna(airport.latitude) or pd.isna(airport.longitude):
            raise ValueError(f"Missing coordinates for {code}")
        return {
            "iata": code, "name": str(airport["name"]),
            "city": ("Ciudad de México" if code == "MEX" else
                     "Ciudad de México (AIFA)" if code == "NLU" else str(airport.city)),
            "country": str(airport.country), "lat": float(airport.latitude),
            "lon": float(airport.longitude),
        }

    result = {}
    for quarter in quarters:
        months = quarter["expected_months"] if "expected_months" in quarter else [
            f"{quarter['period_id'][:4]}M{month:02d}"
            for month in range((int(quarter["period_id"][-1]) - 1) * 3 + 1,
                               (int(quarter["period_id"][-1]) - 1) * 3 + 4)
        ]
        current = observations[observations.period_id.isin(months)].copy()
        if current.empty:
            continue
        if not current.empty and current.duplicated(["period_id", "origin_iata", "dest_iata"]).any():
            raise ValueError("Duplicate AICM route/month/direction in Gold")
        observed_months = []  # Slots do not certify performed flights.
        scheduled_months = sorted(current.period_id.unique().tolist())
        routes = []
        airport_codes = {"MEX"}
        for counterpart, group in current.assign(
            counterpart=current.apply(
                lambda row: row.dest_iata if row.origin_iata == "MEX" else row.origin_iata, axis=1
            )
        ).groupby("counterpart"):
            if not set(group.origin_iata).issubset({"MEX", counterpart}) or not set(group.dest_iata).issubset({"MEX", counterpart}):
                raise ValueError("AICM domestic route lacks MEX endpoint")
            directions = []
            for (origin, destination), part in group.groupby(["origin_iata", "dest_iata"]):
                directions.append({
                    "origin_iata": origin, "destination_iata": destination,
                    "passengers": None, "seats": None,
                    "departures": int(part.scheduled_movements.sum()),
                })
            if len(directions) != 2:
                continue
            route_scheduled_months = sorted(group.period_id.unique().tolist())
            airport_codes.add(counterpart)
            routes.append({
                "market_key": "<>".join(sorted(("MEX", counterpart))),
                "origin": endpoint("MEX"), "destination": endpoint(counterpart),
                "passengers": None, "seats": None,
                "departures": int(group.scheduled_movements.sum()),
                "load_factor": None,
                "previous": {"passengers": None, "seats": None, "departures": None},
                "directions": directions,
                "source_label": SOURCE_LABEL,
                "coverage_note": (
                    "Meses programados: " + ", ".join(m[5:] for m in route_scheduled_months)
                    + " · AICM · ejecución sin verificar"
                ),
                "operation_status": "assigned_slot_not_flown",
                "carrier_role": "AM_flight_number_slot_holder",
                "agent_eligible": False,
                "source_hashes": sorted(group.source_hash.unique().tolist()),
                "record_ids": sorted(group.record_id.unique().tolist()),
            })
        if not routes:
            continue
        routes.sort(key=lambda route: (-(route["departures"] or 0), route["market_key"]))
        result[quarter["period_id"]] = {
            "period_id": quarter["period_id"], "period_label": quarter["period_label"],
            "mode": "scheduled_domestic",
            "expected_months": months, "observed_months": observed_months,
            "routes": routes,
            "airports": [endpoint(code) for code in sorted(airport_codes)],
            "coverage_by_source": {SOURCE_LABEL: scheduled_months},
            "source_url": str(current.source_url.iloc[0]),
            "availability": "partial",
            "route_count": len(routes),
            "represented_movements": None,
            "scheduled_movements": sum(route["departures"] for route in routes if route["operation_status"] == "assigned_slot_not_flown"),
            "attributed_market_movements": None,
            "presence_only_route_count": sum(route["operation_status"] == "carrier_route_present_volume_unresolved" for route in routes),
            "agent_eligible": False,
            "eligibility_reason": "Programación AICM; no confirma vuelos realizados ni cobertura nacional exhaustiva.",
        }
    return result
