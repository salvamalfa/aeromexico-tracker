"""Shared wire definitions for the official regular-flight map (no legacy mutation)."""

from __future__ import annotations

import hashlib
import json
import math

VERSION = "official_route_network_v1"
PUBLIC_PATH = "data/v1/official-routes.json"
CARRIERS = [
    {"key": "AEROMEXICO", "label": "Grupo Aeroméxico", "operator_ids": ["19534", "20250"]},
    {"key": "VOLARIS", "label": "Volaris", "operator_ids": ["21351"]},
    {"key": "VIVA_AEROBUS", "label": "Viva", "operator_ids": ["21342"]},
]
REGIONS = ("canada", "central_america_caribbean", "south_america", "europe", "asia")


def encoded(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()


def dataset_version(value: dict) -> str:
    """Content identity excluding only its own hash, reproducible across machines."""
    return hashlib.sha256(encoded({k: v for k, v in value.items() if k != "dataset_version"})).hexdigest()


def validate(value: dict) -> None:
    from pathlib import Path

    from jsonschema import Draft202012Validator

    schema = Path(__file__).resolve().parents[2] / "contracts/web/official-routes.schema.json"
    Draft202012Validator(json.loads(schema.read_bytes())).validate(value)
    if value["dataset_version"] != dataset_version(value):
        raise ValueError("Official routes content identity changed")
    identities = [(n["period_id"], n["scope"], tuple(n["carrier_keys"])) for n in value["networks"]]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate official route network")
    _semantics(value)


def _semantics(value: dict) -> None:
    from src.dashboard.official_routes_geo import region

    if value["carriers"] != CARRIERS:
        raise ValueError("Official map admits exactly three reviewed tracker groups")
    source_ids = [s["id"] for s in value["sources"]]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("Duplicate official source identity")
    keys = [c["key"] for c in CARRIERS]
    operator_ids = {i: c["key"] for c in CARRIERS for i in c["operator_ids"]}
    operator_keys = {"19534": "AEROMEXICO", "20250": "AEROMEXICO_CONNECT",
                     "21351": "VOLARIS", "21342": "VIVA_AEROBUS"}
    for network in value["networks"]:
        period, scope, selected = network["period_id"], network["scope"], network["carrier_keys"]
        if period not in value["periods"]:
            raise ValueError("Network quarter absent from manifest")
        expected = [f"{period[:4]}M{m:02d}" for m in range(int(period[-1]) * 3 - 2, int(period[-1]) * 3 + 1)]
        observed = network["observed_months"]
        if network["expected_months"] != expected or observed != sorted(set(observed) & set(expected)):
            raise ValueError("Official network months escape their calendar quarter")
        status = "complete" if observed == expected else "partial" if observed else "unavailable"
        if network["availability"] != status or (not observed and network["routes"]):
            raise ValueError("Official temporal availability differs from observed months")
        if not set(network["source_ids"]) <= set(source_ids):
            raise ValueError("Official network references an unknown source")
        if selected != [k for k in keys if k in selected] or (scope == "us") != bool(selected):
            raise ValueError("Official scope/carrier selection changed")
        entity = "ALL" if not selected else "THREE" if len(selected) == 3 else "+".join(selected)
        if network["entity"] != entity or network["grain"] != ("airport_pair" if scope == "us" else "city_pair"):
            raise ValueError("Official network entity or route grain changed")
        routes = network["routes"]
        if len({r["route_key"] for r in routes}) != len(routes):
            raise ValueError("Duplicate bidirectional official route")
        for route in routes:
            a, b = route["origin"], route["destination"]
            if a["id"] >= b["id"] or route["route_key"] != a["id"] + "--" + b["id"]:
                raise ValueError("Official route identity must canonicalize the two endpoints once")
            countries = {a["country_iso2"], b["country_iso2"]}
            if (scope == "national" and countries != {"MX"}) or (scope == "us" and countries != {"MX", "US"}):
                raise ValueError("Official route endpoints contradict their scope")
            if scope == "international" and ("MX" not in countries or "US" in countries or len(countries) != 2):
                raise ValueError("International AFAC excludes the geographic US")
            expected_region = region(next(c for c in countries if c != "MX")) if scope == "international" else None
            if route["region"] != expected_region:
                raise ValueError("Official route region differs from reviewed country mapping")
            for point in (a, b):
                if point["point_kind"] != ("airport" if scope == "us" else "city"):
                    raise ValueError("City margins cannot be presented as airport traffic")
                if (point["lat"] is None) != (point["lon"] is None):
                    raise ValueError("Official point has incomplete coordinates")
                if scope != "us" and "iata" in point:
                    raise ValueError("AFAC city point cannot claim an airport code")
            monthly = route["monthly"]
            if len({m["period_id"] for m in monthly}) != len(monthly) or not {
                m["period_id"] for m in monthly
            } <= set(observed) or sum(m["departures"] for m in monthly) != route["departures"]:
                raise ValueError("Official monthly departures fail temporal/sum reconciliation")
            directions = route["directions"]
            if len({(d["origin_id"], d["destination_id"]) for d in directions}) != len(directions) or any(
                {d["origin_id"], d["destination_id"]} != {a["id"], b["id"]} for d in directions
            ) or sum(d["departures"] for d in directions) != route["departures"]:
                raise ValueError("Official directional departures fail reconciliation")
            operators = route["operators"]
            if scope != "us" and operators:
                raise ValueError("AFAC aggregate cannot attribute traffic to an airline")
            if scope == "us" and (sum(o["departures"] for o in operators) != route["departures"] or any(
                o["carrier_group"] not in selected or operator_ids.get(o["airline_id"]) != o["carrier_group"]
                or operator_keys.get(o["airline_id"]) != o["carrier_key"] for o in operators
            )):
                raise ValueError("Official BTS operator identities or group totals differ")
            comp = route["comparison"]
            previous, pct = comp["previous_departures"], comp["yoy_pct"]
            if not set(comp["comparison_months"]) <= set(observed):
                raise ValueError("Comparison months exceed current source support")
            if previous is None or previous == 0:
                if pct is not None or not comp["reason"]:
                    raise ValueError("Missing/zero previous base must retain an explicit N/D reason")
            elif pct is None or not math.isclose(pct, (route["departures"] / previous - 1) * 100, abs_tol=1e-9):
                raise ValueError("Official year-on-year change differs from its comparable base")
