"""Resolve flight evidence at operator × directional airport route × month.

Passenger estimates and scheduling never establish an observed flight. Components
keep their source and kind even when their market is aggregated for the map.
"""

from __future__ import annotations

from collections import defaultdict
import math

import pandas as pd

KINDS = ("observed", "estimated", "scheduled")


def resolve_cells(cells):
    """Choose one source per exact cell; explicit observed zero blocks fallback.

    Duplicate source cells are an input error, not an invitation to sum twice.
    Scheduled evidence stays separate and cannot add to observed/estimated flights.
    """
    grouped = defaultdict(list)
    seen = set()
    for cell in cells:
        value = cell.get("departures")
        if value is None or pd.isna(value):
            continue
        if not math.isfinite(float(value)) or float(value) < 0:
            raise ValueError("Invalid flight-cell departures")
        key = tuple(cell[k] for k in ("carrier_key", "origin_iata", "destination_iata", "period_id"))
        identity = (*key, cell["kind"], cell["source_label"])
        if identity in seen:
            raise ValueError("Duplicate flight source cell")
        seen.add(identity)
        grouped[key].append({**cell, "departures": float(value)})
    result = []
    for key, candidates in sorted(grouped.items()):
        rank = {"observed": 0, "estimated": 1, "scheduled": 2}
        candidates.sort(key=lambda c: (rank[c["kind"]], c.get("priority", 0), c["source_label"]))
        result.append(candidates[0])
    # Brand-level schedules cannot identify Aerovías versus Connect. Exclude an
    # overlapping cell if either actual operator has evidence; never add both.
    operative = {
        (c["origin_iata"], c["destination_iata"], c["period_id"])
        for c in result
        if c["kind"] != "scheduled" and c["carrier_key"] in {"AEROMEXICO", "AEROMEXICO_CONNECT"}
    }
    return [
        c
        for c in result
        if c["kind"] != "scheduled"
        or c["carrier_key"] != "AEROMEXICO_GROUP"
        or (c["origin_iata"], c["destination_iata"], c["period_id"]) not in operative
    ]


def _rows(connection, table, months, carriers=None):
    if not connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name=?", [table]
    ).fetchone()[0]:
        return pd.DataFrame()
    query = f"SELECT * FROM {table} WHERE period_id IN ({','.join('?' for _ in months)})"
    args = list(months)
    if carriers:
        query += f" AND carrier_key IN ({','.join('?' for _ in carriers)})"
        args += list(carriers)
    return connection.execute(query, args).df()


def admitted_estimates(estimates, endpoint, *, include_us=False, allowed_us_estimate_cells=None):
    """Apply the private, exact-cell admission policy before any route aggregation.

    None retains the explicit legacy opt-in; an empty set admits no US fallback.
    Non-US estimates retain their existing policy independently of this flag.
    """
    if estimates.empty:
        return estimates
    keep = []
    for row in estimates.itertuples(index=False):
        is_us = "US" in (endpoint(row.origin_iata)["country"], endpoint(row.destination_iata)["country"])
        key = (str(row.carrier_key), str(row.period_id), str(row.origin_iata), str(row.destination_iata))
        keep.append(
            not is_us
            or (include_us and (allowed_us_estimate_cells is None or key in allowed_us_estimate_cells))
        )
    return estimates.loc[keep].copy()


def international_cells(
    connection,
    months,
    entity,
    estimates,
    endpoint,
    *,
    include_us=False,
    authorities=None,
    scheduled=None,
    allowed_us_estimate_cells=None,
):
    """Read retained counts; no network calls, fitting, or passenger-based weights."""
    estimates = admitted_estimates(
        estimates, endpoint, include_us=include_us, allowed_us_estimate_cells=allowed_us_estimate_cells
    )
    cells = []
    raw = _rows(connection, "fact_route_traffic", months, entity.t100_carriers)
    if not raw.empty:
        if "record_id" in raw and raw.record_id.duplicated().any():
            raise ValueError("Duplicate BTS flight record")
        routes = connection.execute("SELECT route_key, origin_iata, dest_iata FROM dim_route").df()
        raw = raw.merge(routes, on="route_key", validate="many_to_one")
        for keys, group in raw.groupby(["carrier_key", "origin_iata", "dest_iata", "period_id"]):
            carrier, origin, dest, period = map(str, keys)
            cells.append(
                dict(
                    carrier_key=carrier,
                    origin_iata=origin,
                    destination_iata=dest,
                    period_id=period,
                    kind="observed",
                    source_label="Estados Unidos · BTS T-100",
                    departures=group.departures_performed.sum(min_count=1),
                    source_hashes=sorted(set(group.source_hash.dropna().astype(str)))
                    if "source_hash" in group
                    else [],
                    service_class_departures={
                        str(k): float(v)
                        for k, v in group.groupby("service_class", dropna=False)
                        .departures_performed.sum()
                        .items()
                    }
                    if "service_class" in group
                    else {},
                )
            )
    if authorities is not None and not authorities.empty:
        current = authorities[authorities.period_id.isin(months)]
        for keys, group in current.groupby(["source_system", "origin_iata", "dest_iata", "period_id"]):
            source, origin, dest, period = map(str, keys)
            labels = {
                "anac": "Brasil · ANAC",
                "aerocivil": "Colombia · Aerocivil",
                "caa": "Reino Unido · CAA",
            }
            cells.append(
                dict(
                    carrier_key="AEROMEXICO",
                    origin_iata=origin,
                    destination_iata=dest,
                    period_id=period,
                    kind="observed",
                    source_label=labels[source],
                    departures=group.departures.sum(min_count=1),
                    source_hashes=sorted(set(group.source_hash)),
                )
            )
    if not estimates.empty:
        current = estimates[estimates.period_id.isin(months)]
        if current.duplicated(["carrier_key", "origin_iata", "destination_iata", "period_id"]).any():
            raise ValueError("Duplicate retained frequency cell")
        for keys, group in current.groupby(["carrier_key", "origin_iata", "destination_iata", "period_id"]):
            carrier, origin, dest, period = map(str, keys)
            if not include_us and "US" in (endpoint(origin)["country"], endpoint(dest)["country"]):
                continue
            cells.append(
                dict(
                    carrier_key=carrier,
                    origin_iata=origin,
                    destination_iata=dest,
                    period_id=period,
                    kind="estimated",
                    source_label="AeroDataBox · frecuencias históricas estimadas",
                    departures=group.departures_estimated.sum(min_count=1),
                    source_hashes=[],
                    estimator_version="; ".join(sorted(set(group.estimator_version.astype(str))))
                    if "estimator_version" in group
                    else "unknown",
                )
            )
    if scheduled is not None and not scheduled.empty:
        for keys, group in scheduled[scheduled.period_id.isin(months)].groupby(
            ["origin_iata", "dest_iata", "period_id"]
        ):
            origin, dest, period = map(str, keys)
            cells.append(
                dict(
                    carrier_key="AEROMEXICO_GROUP",
                    origin_iata=origin,
                    destination_iata=dest,
                    period_id=period,
                    kind="scheduled",
                    source_label="AICM · vuelos AM programados",
                    departures=group.scheduled_movements.sum(min_count=1),
                    source_hashes=sorted(set(group.source_hash)),
                )
            )
    return resolve_cells(cells)


def apply_flight_cells(network, cells, endpoint):
    """Replace only flight counts; retain the historical passenger payload intact."""
    by_market = defaultdict(list)
    for cell in cells:
        by_market["<>".join(sorted((cell["origin_iata"], cell["destination_iata"])))].append(cell)
    routes = {r["market_key"]: r for r in network["routes"]}
    for market, components in sorted(by_market.items()):
        if market not in routes:
            a, b = market.split("<>")
            try:
                origin, destination = endpoint(a), endpoint(b)
            except (KeyError, ValueError):
                continue  # Geography exclusion remains explicit in the T-100 builder.
            route = dict(
                market_key=market,
                origin=origin,
                destination=destination,
                passengers=None,
                seats=None,
                load_factor=None,
                directions=[],
                previous=dict(passengers=None, seats=None, departures=None),
            )
            network["routes"].append(route)
            routes[market] = route
        route = routes[market]
        route["flight_components"] = [
            {
                **{
                    k: c[k]
                    for k in (
                        "carrier_key",
                        "origin_iata",
                        "destination_iata",
                        "period_id",
                        "kind",
                        "source_label",
                        "departures",
                        "source_hashes",
                    )
                },
                **{k: c[k] for k in ("service_class_departures", "estimator_version") if k in c},
            }
            for c in components
        ]
        totals = {kind: sum(c["departures"] for c in components if c["kind"] == kind) for kind in KINDS}
        operative = [c for c in components if c["kind"] != "scheduled"]
        selected = operative or components
        route["departures"] = sum(c["departures"] for c in selected)
        kinds = {c["kind"] for c in selected}
        if kinds == {"observed"}:
            route["operation_status"] = "operated_observed"
        elif kinds == {"estimated"}:
            route["operation_status"] = "estimated_from_retained_frequencies"
        elif kinds == {"scheduled"}:
            route["operation_status"] = "assigned_slot_not_flown"
        else:
            route["operation_status"] = "mixed_observed_estimated_cells"
            route["previous"] = {k: None for k in ("passengers", "seats", "departures")}
        route["source_label"] = " · ".join(sorted({c["source_label"] for c in selected}))
        route["observed_months"] = sorted({c["period_id"] for c in components if c["kind"] == "observed"})
        route["estimated_months"] = sorted({c["period_id"] for c in components if c["kind"] == "estimated"})
        route["scheduled_months"] = sorted({c["period_id"] for c in components if c["kind"] == "scheduled"})
        route["coverage_note"] = (
            route.get("coverage_note", "")
            + " · Vuelos por celda operador/ruta/sentido/mes: "
            + ", ".join(
                f"{totals[kind]:g} {kind}" for kind in KINDS if any(c["kind"] == kind for c in components)
            )
        )
        old_directions = {(d["origin_iata"], d["destination_iata"]): d for d in route.get("directions", [])}
        directions = defaultdict(float)
        for cell in selected:
            directions[(cell["origin_iata"], cell["destination_iata"])] += cell["departures"]
        route["directions"] = [
            {
                **old_directions.get(pair, dict(passengers=None, seats=None)),
                "origin_iata": pair[0],
                "destination_iata": pair[1],
                "departures": count,
            }
            for pair, count in sorted(directions.items())
            if count > 0
        ]
    coverage = defaultdict(set)
    for cell in cells:
        coverage[cell["source_label"]].add(cell["period_id"])
    for route in network["routes"]:
        if not route.get("flight_components"):
            coverage[route.get("source_label", "Fuente no detallada")].update(
                route.get("observed_months")
                or route.get("scheduled_months")
                or route.get("estimated_months", [])
            )
    network["coverage_by_source"] = {k: sorted(v) for k, v in sorted(coverage.items())}
