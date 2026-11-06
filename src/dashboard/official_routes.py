"""Reported regular city-pair AFAC and observed F/G MX-US tracker-operator networks."""

from __future__ import annotations

from itertools import combinations

import pandas as pd

from src.dashboard.official_routes_contract import CARRIERS, VERSION, dataset_version, validate
from src.dashboard.official_routes_geo import city_key, iso, region

OPERATOR_GROUPS = {operator: carrier["key"] for carrier in CARRIERS for operator in carrier["operator_ids"]}


def months(period: str) -> list[str]:
    year, quarter = int(period[:4]), int(period[-1])
    if period != f"{year}Q{quarter}" or quarter not in range(1, 5):
        raise ValueError("Official routes need a calendar quarter")
    return [f"{year}M{m:02d}" for m in range(quarter * 3 - 2, quarter * 3 + 1)]


def afac_cells(frame: pd.DataFrame, points: dict) -> list[dict]:
    frame = frame[(frame.margin_scope == "directed_city_pair_all_carriers")
                  & (frame.metric_key == "flights_as_reported")]
    cells = []
    for row in frame.to_dict("records"):
        origin_country, dest_country = iso(row["origin_country_as_reported"]), iso(row["destination_country_as_reported"])
        foreign = dest_country if origin_country == "MX" else origin_country
        scope = "national" if origin_country == dest_country == "MX" else "international"
        if scope == "international" and foreign == "US":
            continue  # AFAC US is deliberately outside this surface, never substituted for BTS.
        a = city_key(row["origin_city_as_reported"], origin_country)
        b = city_key(row["destination_city_as_reported"], dest_country)
        if a not in points or b not in points:
            raise ValueError("AFAC label absent from explicit city dimension")
        cells.append(dict(period_id=row["period_id"], scope=scope, origin=a, destination=b,
                          departures=int(row["value"]), carrier_group=None, operator=None, label=None,
                          airline_id=None, region=None if scope == "national" else region(foreign)))
    return cells


def bts_cells(frame: pd.DataFrame, points: dict) -> list[dict]:
    selected = frame[frame["class"].isin(["F", "G"]) & frame.airline_id.astype(str).isin(OPERATOR_GROUPS)]
    cells = []
    for row in selected.to_dict("records"):
        a, b = row["origin"], row["dest"]
        if a not in points or b not in points:
            raise ValueError("BTS endpoint absent from pinned airport geography")
        if {points[a]["country_iso2"], points[b]["country_iso2"]} != {"MX", "US"}:
            continue  # PR/VI geographic territories belong to the AFAC Caribbean view.
        operator_id = str(row["airline_id"])
        cells.append(dict(period_id=row["period_id"], scope="us", origin="AIRPORT_" + a,
                          destination="AIRPORT_" + b, departures=int(row["departures_performed"]),
                          carrier_group=OPERATOR_GROUPS[operator_id], operator=row["carrier_key"],
                          label=row["unique_carrier_name"], airline_id=operator_id, region=None))
    return cells


def comparison(current: list[dict], previous: list[dict], observed: list[str]) -> dict:
    """Require every operator/direction/month cell on both sides; absence is not zero."""
    shifted = [str(int(m[:4]) - 1) + m[4:] for m in observed]
    result = dict(previous_departures=None, yoy_pct=None, comparison_months=observed, reason=None)
    key = lambda c: (c["period_id"][4:], c["origin"], c["destination"], c["operator"])
    current_keys, previous_keys = {key(c) for c in current}, {key(c) for c in previous}
    if not current or not previous or current_keys != previous_keys:
        result["reason"] = "N/D: faltan celdas comparables de ruta, operador, sentido o mes."
        return result
    if {c["period_id"] for c in current} != set(observed) or {c["period_id"] for c in previous} != set(shifted):
        result["reason"] = "N/D: faltan meses comparables de la ruta."
        return result
    total = sum(c["departures"] for c in previous)
    result["previous_departures"] = total
    if total == 0:
        result["reason"] = "N/D: la base del año previo es cero."
    else:
        result["yoy_pct"] = (sum(c["departures"] for c in current) / total - 1) * 100
    return result


def aggregate_routes(current: list[dict], previous: list[dict], points: dict, observed: list[str]) -> list[dict]:
    grouped, old = {}, {}
    for cells, target in [(current, grouped), (previous, old)]:
        for cell in cells:
            key = tuple(sorted([cell["origin"], cell["destination"]]))
            target.setdefault(key, []).append(cell)
    routes = []
    for pair, cells in sorted(grouped.items()):
        monthly, directions, operators = {}, {}, {}
        for cell in cells:
            m = cell["period_id"]
            monthly[m] = monthly.get(m, 0) + cell["departures"]
            d = (cell["origin"], cell["destination"])
            directions[d] = directions.get(d, 0) + cell["departures"]
            if cell["operator"]:
                o = (cell["operator"], cell["carrier_group"], cell["label"], cell["airline_id"])
                operators[o] = operators.get(o, 0) + cell["departures"]
        routes.append(dict(
            route_key="--".join(pair), origin=points[pair[0]], destination=points[pair[1]],
            region=cells[0]["region"], departures=sum(monthly.values()),
            monthly=[dict(period_id=m, departures=n) for m, n in sorted(monthly.items())],
            directions=[dict(origin_id=a, destination_id=b, departures=n) for (a, b), n in sorted(directions.items())],
            operators=[dict(carrier_key=k, carrier_group=g, label=label, airline_id=i, departures=n)
                       for (k, g, label, i), n in sorted(operators.items())],
            comparison=comparison(cells, old.get(pair, []), observed),
        ))
    return sorted(routes, key=lambda r: (-r["departures"], r["route_key"]))


def build_payload(afac: pd.DataFrame, bts: pd.DataFrame, cities: dict, airports: dict,
                  sources: list[dict], *, source_as_of: str) -> dict:
    """Pure generator. Source certification and physical replay happen before this call."""
    cells = afac_cells(afac, cities) + bts_cells(bts, airports)
    all_points = {**cities, **{p["id"]: p for p in airports.values()}}
    source_periods = {"national": sorted(afac.period_id.unique()), "international": sorted(afac.period_id.unique()),
                      "us": sorted(bts.period_id.unique())}
    periods = sorted({m[:4] + "Q" + str((int(m[-2:]) - 1) // 3 + 1) for values in source_periods.values() for m in values})
    keys = [c["key"] for c in CARRIERS]
    subsets = [list(s) for n in range(1, 4) for s in combinations(keys, n)]
    networks = []
    for period in periods:
        expected = months(period)
        for scope in ["national", "us", "international"]:
            observed = sorted(set(expected) & set(source_periods[scope]))
            prev_months = {str(int(m[:4]) - 1) + m[4:] for m in observed}
            for subset in subsets if scope == "us" else [[]]:
                selected = [c for c in cells if c["scope"] == scope and
                            (not subset or c["carrier_group"] in subset)]
                current = [c for c in selected if c["period_id"] in observed]
                previous = [c for c in selected if c["period_id"] in prev_months]
                networks.append(dict(
                    period_id=period, scope=scope, carrier_keys=subset,
                    entity="ALL" if not subset else "THREE" if len(subset) == 3 else "+".join(subset),
                    grain="airport_pair" if scope == "us" else "city_pair", expected_months=expected,
                    observed_months=observed, availability="complete" if observed == expected else
                    "partial" if observed else "unavailable",
                    source_ids=[s["id"] for s in sources if s["id"].startswith("bts-" if scope == "us" else "afac-")
                                and s["source_period"][:4] in {period[:4], str(int(period[:4]) - 1)}],
                    notes=["Servicio regular; pasajeros y carga exclusiva. Ambos sentidos se suman una sola vez.",
                           "Meses disponibles no acreditan cobertura total de operadores o rutas BTS." if scope == "us"
                           else "Todas las aerolíneas; par de ciudades AFAC, sin atribución por empresa."],
                    routes=aggregate_routes(current, previous, all_points, observed),
                ))
    payload = dict(schema_version=VERSION, metadata=dict(
        title="Vuelos regulares", universe="scheduled_passenger_and_all_cargo", source_as_of=source_as_of,
        notes=["Faltantes conservados como N/D; no se estiman vuelos ni pasajeros.",
               "EE.UU.: tres grupos del tracker, BTS F/G; no es el total del mercado estadounidense."],
        geography_attribution="Ciudades: GeoNames CC BY 4.0. Aeropuertos: OurAirports, dominio público."),
        periods=periods, carriers=CARRIERS, sources=sources, networks=networks)
    payload["dataset_version"] = dataset_version(payload)
    validate(payload)
    return payload
