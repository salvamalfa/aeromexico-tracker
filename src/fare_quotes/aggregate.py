"""Public route/fare averages from verified observations; no book or flight identifiers."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.fare_quotes.normalize import digest

VERSION = "fare_averages_v1"
METRICS = ("cash_final_mxn", "points", "redemption_cash_mxn", "redemption_taxes_mxn")
GROUP_FIELDS = (
    "period_id",
    "provider",
    "origin",
    "destination",
    "fare",
    "conditions",
    "horizon_months",
    "stay_days",
    "trip_type",
)


def _notes(row):
    try:
        return json.loads(row.get("notes") or "{}")
    except (TypeError, ValueError):
        return {}


def comparable_group(row):
    fare = row.get("fare")
    if not isinstance(fare, str) or not fare.strip():
        return None
    query = date.fromisoformat(row["query_date"])
    departure = date.fromisoformat(row["departure_date"])
    returning = date.fromisoformat(row["return_date"]) if row["return_date"] else None
    conditions = " ".join((row.get("conditions") or "").split())
    if not conditions and row["provider"] == "AMR":
        # Only the assigned, validated cabin contract gives an AMR basis for comparison.
        notes = _notes(row)
        if notes.get("validation") in {
            "installed_worker_schema_pair_and_fenced_sheet_readback",
            "installed_worker_schema_and_fenced_sheet_readback",
        }:
            conditions = "Contrato AMR validado; misma cabina; vuelo redondo; adulto"
    if not conditions:
        # Missing fare conditions cannot be made comparable by grouping all unknowns together.
        return None
    values = dict(
        period_id=row["period_id"],
        provider=row["provider"],
        origin=row["origin"],
        destination=row["destination"],
        fare=fare.strip(),
        conditions=conditions,
        horizon_months=(departure.year - query.year) * 12 + departure.month - query.month,
        stay_days=(returning - departure).days if returning else None,
        trip_type="round_trip" if returning else "one_way",
    )
    return tuple(values[k] for k in GROUP_FIELDS)


def metric(values):
    observed = [Decimal(str(v)) for v in values if v is not None]
    return dict(mean=float(sum(observed) / len(observed)) if observed else None, n=len(observed))


def build_averages(private: dict) -> dict:
    if private.get("schema_version") != "local_fare_quotes_v1" or private.get("private") is not True:
        raise ValueError("Expected the private normalized quote dataset")
    from src.config import PATHS
    from src.dashboard.official_routes_geo import city_key, iso

    airport_cities = defaultdict(set)
    for filename, country in (
        ("afac_city_iata_crosswalk.csv", "MX"),
        ("afac_international_city_iata_crosswalk.csv", None),
    ):
        path = Path(PATHS.data) / "reference" / filename
        with path.open(encoding="utf-8-sig", newline="") as stream:
            for row in csv.DictReader(stream):
                airport_cities[row["airport_iata"]].add(
                    city_key(row["afac_city"], country or iso(row["afac_country"]))
                )
    grouped, excluded = defaultdict(list), 0
    for row in private["rows"]:
        if row["status"] not in {"ok", "partial_redemption"}:
            excluded += 1
            continue
        key = comparable_group(row)
        if key is None:
            excluded += 1
            continue
        grouped[key].append(row)
    groups = []
    for key, observations in sorted(grouped.items(), key=lambda pair: repr(pair[0])):
        group = dict(zip(GROUP_FIELDS, key))
        for name in ("origin", "destination"):
            keys = airport_cities[group[name]]
            group[name + "_map_id"] = next(iter(keys)) if len(keys) == 1 else None
        group.update(
            metrics={field: metric(row.get(field) for row in observations) for field in METRICS},
            observations=len(observations),
            paired_cash_points=sum(
                row["cash_final_mxn"] is not None and row["points"] is not None for row in observations
            ),
            query_date_start=min(row["query_date"] for row in observations),
            query_date_end=max(row["query_date"] for row in observations),
            points_applicability="not_applicable" if group["provider"] == "VOLARIS" else "applicable",
        )
        if group["provider"] == "VOLARIS" and group["metrics"]["points"] != {"mean": None, "n": 0}:
            raise ValueError("Volaris cannot have points, even zero")
        group["group_id"] = digest(group)
        groups.append(group)
    payload = dict(
        schema_version=VERSION,
        period_basis="consultation_quarter_America_Mexico_City",
        aggregation="arithmetic_mean_of_verified_observations_not_all_flights",
        periods=sorted({g["period_id"] for g in groups}),
        groups=groups,
        excluded_unverified_observations=excluded,
        notes=[
            "Cada media usa sólo observaciones verificadas y no valores faltantes.",
            "Aeropuerto, proveedor, tarifa, condiciones, horizonte y estancia se conservan separados.",
            "Dinero es precio regular final en MXN; pago adicional del canje e impuestos son independientes.",
        ],
    )
    payload["dataset_version"] = digest(payload)
    return payload
