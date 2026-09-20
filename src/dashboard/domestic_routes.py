"""Build the separately labelled domestic AICM slot view for Vuelos."""

from __future__ import annotations

import pandas as pd


SOURCE_LABEL = "México · AICM, vuelos AM programados"
EXCLUSIVE_LABEL = "AFAC · mercado con Aeroméxico como único operador identificado"
SHARED_LABEL = "AIFA · ruta de Aeroméxico identificada; volumen propio sin desglose"
ESTIMATED_LABEL = "AFAC + AeroDataBox · pasajeros estimados"
ESTIMATED_CARRIERS = {
    "AEROMEXICO": "Aerovías de México",
    "AEROMEXICO_CONNECT": "Aeroméxico Connect",
}
MONTH_NAMES = (
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def load_domestic_monthly_networks(connection) -> dict[str, dict]:
    """Expose every retained estimate month independently from financial quarters."""

    exists = connection.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_name = 'fact_route_carrier_domestic_estimate'"
    ).fetchone()[0]
    if not exists:
        return {}
    periods = [
        str(row[0])
        for row in connection.execute(
            "SELECT DISTINCT period_id FROM fact_route_carrier_domestic_estimate "
            "ORDER BY period_id"
        ).fetchall()
    ]
    records = [
        {
            "period_id": period,
            "period_label": f"{MONTH_NAMES[int(period[5:])]} {period[:4]}",
            "expected_months": [period],
        }
        for period in periods
    ]
    return load_domestic_networks(connection, records)


def load_domestic_networks(connection, quarters: list[dict]) -> dict[str, dict]:
    estimate_exists = connection.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_name = 'fact_route_carrier_domestic_estimate'"
    ).fetchone()[0]
    estimates = connection.execute(
        "SELECT * FROM fact_route_carrier_domestic_estimate "
        "WHERE carrier_key IN ('AEROMEXICO', 'AEROMEXICO_CONNECT')"
    ).df() if estimate_exists else pd.DataFrame()
    exists = connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'fact_domestic_scheduled_route_movements'"
    ).fetchone()[0]
    observations = connection.execute(
        "SELECT * FROM fact_domestic_scheduled_route_movements WHERE observation_status = 'assigned_slot_not_flown'"
    ).df() if exists else pd.DataFrame()
    exclusive_exists = connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'fact_domestic_exclusive_market_inferences'"
    ).fetchone()[0]
    exclusive = connection.execute(
        "SELECT * FROM fact_domestic_exclusive_market_inferences WHERE attribution_status = 'inferred_exclusive_carrier_market'"
    ).df() if exclusive_exists else pd.DataFrame()
    shared_exists = connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'fact_aifa_shared_route_presence'"
    ).fetchone()[0]
    shared = connection.execute(
        "SELECT * FROM fact_aifa_shared_route_presence WHERE attribution_status = 'carrier_route_present_volume_unresolved'"
    ).df() if shared_exists else pd.DataFrame()
    if estimates.empty and observations.empty and exclusive.empty and shared.empty:
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

    def estimated_network(quarter: dict, frame: pd.DataFrame, months: list[str]) -> dict:
        frame = frame.copy()
        frame["carrier_label"] = frame["carrier_key"].map(ESTIMATED_CARRIERS)
        if frame["carrier_label"].isna().any():
            raise ValueError("Domestic estimate contains an unsupported Aeromexico carrier key")
        routes = []
        airport_codes: set[str] = set()
        observed_months = sorted(frame["period_id"].astype(str).unique().tolist())
        coverage_note = "Meses: " + ", ".join(month[5:] for month in observed_months)
        for market_key, group in frame.groupby("market_key"):
            endpoints = str(market_key).split("<>")
            if len(endpoints) != 2:
                raise ValueError(f"Invalid domestic estimated market key: {market_key}")
            airport_codes.update(endpoints)
            directions = []
            for (origin, destination), part in group.groupby(
                ["origin_iata", "destination_iata"]
            ):
                directions.append(
                    {
                        "origin_iata": str(origin),
                        "destination_iata": str(destination),
                        "passengers": float(part["passengers_estimated"].sum()),
                        "passengers_low": float(part["passengers_estimated_low"].sum()),
                        "passengers_high": float(part["passengers_estimated_high"].sum()),
                        "seats": None,
                        "departures": None,
                    }
                )
            monthly = []
            for row in group.sort_values(
                ["period_id", "carrier_key", "origin_iata", "destination_iata"]
            ).itertuples(index=False):
                monthly.append(
                    {
                        "period_id": str(row.period_id),
                        "carrier_key": str(row.carrier_key),
                        "carrier_label": str(row.carrier_label),
                        "origin_iata": str(row.origin_iata),
                        "destination_iata": str(row.destination_iata),
                        "passengers": float(row.passengers_estimated),
                        "passengers_low": float(row.passengers_estimated_low),
                        "passengers_high": float(row.passengers_estimated_high),
                        "support_observed_in_period": bool(row.support_observed_in_period),
                        "support_source_periods": str(row.support_source_periods),
                        "support_month_gap": int(row.support_month_gap),
                    }
                )
            routes.append(
                {
                    "market_key": str(market_key),
                    "origin": endpoint(endpoints[0]),
                    "destination": endpoint(endpoints[1]),
                    "passengers": float(group["passengers_estimated"].sum()),
                    "passengers_low": float(group["passengers_estimated_low"].sum()),
                    "passengers_high": float(group["passengers_estimated_high"].sum()),
                    "passengers_estimated": True,
                    "seats": None,
                    "departures": None,
                    "load_factor": None,
                    "previous": {"passengers": None, "seats": None, "departures": None},
                    "directions": directions,
                    "monthly": monthly,
                    "source_label": ESTIMATED_LABEL,
                    "coverage_note": coverage_note + " · estimación por operador",
                    "operation_status": "estimated_from_afac_margins_and_temporal_support",
                    "carrier_role": "operating_carrier_estimated",
                    "agent_eligible": False,
                    "support_repair_applied": bool(group["support_repair_applied"].any()),
                }
            )
        routes.sort(key=lambda route: (-route["passengers"], route["market_key"]))
        return {
            "period_id": quarter["period_id"],
            "period_label": quarter["period_label"],
            "mode": "estimated_domestic",
            "expected_months": months,
            "observed_months": observed_months,
            "availability": "complete" if set(observed_months) == set(months) else "partial",
            "routes": routes,
            "airports": [endpoint(code) for code in sorted(airport_codes)],
            "coverage_by_source": {ESTIMATED_LABEL: observed_months},
            "source_url": "https://www.gob.mx/afac/acciones-y-programas/estadisticas-280404",
            "route_count": len(routes),
            "represented_passengers": float(sum(route["passengers"] for route in routes)),
            "represented_movements": None,
            "represented_seed_weight": float(frame["seed_weight"].sum()),
            "agent_eligible": False,
            "eligibility_reason": (
                "Estimación retrospectiva generada después del corte histórico del 13 jul 2026."
            ),
        }

    result = {}
    for quarter in quarters:
        months = quarter["expected_months"] if "expected_months" in quarter else [
            f"{quarter['period_id'][:4]}M{month:02d}"
            for month in range((int(quarter["period_id"][-1]) - 1) * 3 + 1,
                               (int(quarter["period_id"][-1]) - 1) * 3 + 4)
        ]
        estimated = estimates[estimates.period_id.isin(months)].copy() if not estimates.empty else pd.DataFrame()
        if not estimated.empty:
            result[quarter["period_id"]] = estimated_network(quarter, estimated, months)
            continue
        current = observations[observations.period_id.isin(months)].copy()
        inferred = exclusive[exclusive.period_id.isin(months)].copy() if not exclusive.empty else pd.DataFrame()
        present = shared[shared.period_id.eq(quarter["period_id"])].copy() if not shared.empty else pd.DataFrame()
        if current.empty and inferred.empty and present.empty:
            continue
        if not current.empty and current.duplicated(["period_id", "origin_iata", "dest_iata"]).any():
            raise ValueError("Duplicate AICM route/month/direction in Gold")
        if not inferred.empty and inferred.duplicated(["period_id", "origin_iata", "dest_iata"]).any():
            raise ValueError("Duplicate AFAC inferred route/month/direction in Gold")
        observed_months = sorted(set(current.period_id.unique().tolist()) | set(inferred.period_id.unique().tolist())
                                 | ({"2026M06"} if not present.empty else set()))
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
                "coverage_note": "Abr–jun 2026 · slots AICM · programado",
                "operation_status": "assigned_slot_not_flown",
                "carrier_role": "AM_flight_number_slot_holder",
                "agent_eligible": False,
                "source_hashes": sorted(group.source_hash.unique().tolist()),
                "record_ids": sorted(group.record_id.unique().tolist()),
            })
        if not inferred.empty:
            inferred["market_key"] = inferred.apply(
                lambda row: "<>".join(sorted((row.origin_iata, row.dest_iata))), axis=1
            )
            for market_key, group in inferred.groupby("market_key"):
                if any(route["market_key"] == market_key for route in routes):
                    raise ValueError(f"AFAC inferred market overlaps AICM slot route: {market_key}")
                endpoints = market_key.split("<>")
                if len(endpoints) != 2 or "NLU" not in endpoints and "CLQ" not in endpoints:
                    raise ValueError(f"Unexpected inferred domestic market: {market_key}")
                directions = [
                    {"origin_iata": origin, "destination_iata": destination,
                     "passengers": None, "seats": None,
                     "departures": int(part.market_movements.sum())}
                    for (origin, destination), part in group.groupby(["origin_iata", "dest_iata"])
                ]
                if len(directions) != 2:
                    raise ValueError(f"Missing direction in inferred market: {market_key}")
                airport_codes.update(endpoints)
                routes.append({
                    "market_key": market_key,
                    "origin": endpoint(endpoints[0]), "destination": endpoint(endpoints[1]),
                    "passengers": None, "seats": None,
                    "departures": int(group.market_movements.sum()), "load_factor": None,
                    "previous": {"passengers": None, "seats": None, "departures": None},
                    "directions": directions,
                    "source_label": EXCLUSIVE_LABEL,
                    "coverage_note": "Abr–jun 2026 · AFAC: vuelos del mercado; atribución inferida por operador único",
                    "operation_status": "carrier_inferred_market_observed",
                    "carrier_role": "inferred_Aeromexico_or_Connect",
                    "agent_eligible": False,
                    "source_hashes": sorted(set(group.afac_source_hash) | set(group.roster_source_hash)),
                    "record_ids": sorted(group.record_id.unique().tolist()),
                })
        for row in present.itertuples(index=False):
            if any(route["market_key"] == row.market_key for route in routes):
                raise ValueError(f"AIFA presence overlaps a quantified market: {row.market_key}")
            if row.origin_iata != "NLU" or "NLU" not in row.market_key.split("<>"):
                raise ValueError(f"Unexpected AIFA presence market: {row.market_key}")
            if pd.notna(row.carrier_movements):
                raise ValueError(f"AIFA shared market has unattributed carrier movements: {row.market_key}")
            airport_codes.add(row.dest_iata)
            routes.append({
                "market_key": row.market_key,
                "origin": endpoint("NLU"), "destination": endpoint(row.dest_iata),
                "passengers": None, "seats": None, "departures": None,
                "load_factor": None,
                "previous": {"passengers": None, "seats": None, "departures": None},
                "directions": [],
                "source_label": SHARED_LABEL,
                "coverage_note": "Junio 2026 · Aeroméxico presente · vuelos propios sin desglose",
                "operation_status": "carrier_route_present_volume_unresolved",
                "carrier_role": "Aeromexico_or_Connect_unresolved",
                "agent_eligible": False,
                "source_hashes": [row.afac_source_hash, row.roster_source_hash],
                "record_ids": [row.record_id],
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
            "coverage_by_source": ({SOURCE_LABEL: sorted(current.period_id.unique().tolist())} if not current.empty else {})
                                  | ({EXCLUSIVE_LABEL: sorted(inferred.period_id.unique().tolist())} if not inferred.empty else {})
                                  | ({SHARED_LABEL: ["2026M06"]} if not present.empty else {}),
            "source_url": (str(current.source_url.iloc[0]) if not current.empty else
                           str(inferred.source_url.iloc[0]) if not inferred.empty else str(present.roster_source_url.iloc[0])),
            "route_count": len(routes),
            "represented_movements": sum(route["departures"] or 0 for route in routes),
            "scheduled_movements": sum(route["departures"] for route in routes if route["operation_status"] == "assigned_slot_not_flown"),
            "attributed_market_movements": sum(route["departures"] for route in routes if route["operation_status"] == "carrier_inferred_market_observed"),
            "presence_only_route_count": sum(route["operation_status"] == "carrier_route_present_volume_unresolved" for route in routes),
            "agent_eligible": False,
        }
    return result
