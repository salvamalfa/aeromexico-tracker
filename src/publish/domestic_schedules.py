"""Verify the withdrawn model's replacement schedules directly in pinned Gold."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd

MONTHS = ("", "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
          "septiembre", "octubre", "noviembre", "diciembre")
SOURCE = "México · AICM, vuelos AM programados"


def _canonical(value):
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items() if item is not None and item != []}
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    return value


def require_domestic_gold_schedules(baseline: Path, candidate: Path, gold: Path) -> None:
    """Reject invented, omitted, redistributed or mislabelled AICM schedules.

    The previous estimated network cannot be a numeric baseline. Independently
    sum the unchanged public source rows, preserving their direction, actual
    scheduling months and slot-holder grain; never call the domestic builder.
    """
    old = json.loads((baseline / "data/v1/flights/quarters.json").read_text())
    root = candidate / "data/v1/flights"
    manifest = json.loads((root / "quarters.json").read_text())
    quarter_labels = {item["period_id"]: item["period_label"] for item in old["quarters"]}
    path = gold / "fact_domestic_scheduled_route_movements.parquet"
    source = pd.read_parquet(path) if path.is_file() else pd.DataFrame()
    expected = {}
    if not source.empty:
        source = source[source.observation_status.eq("assigned_slot_not_flown")].copy()
        if not source.carrier_code.eq("AM").all() or not source.source_system.eq("aicm").all():
            raise ValueError("Domestic Gold is outside the AM slot-holder source allowlist")
        if source.duplicated(["period_id", "origin_iata", "dest_iata"]).any():
            raise ValueError("Duplicate domestic Gold direction/month")
        airports = pd.read_parquet(gold / "dim_airport.parquet").set_index("airport_iata")

        def endpoint(code):
            row = airports.loc[code]
            return {"iata": code, "name": str(row["name"]),
                    "city": "Ciudad de México" if code == "MEX" else str(row.city),
                    "lat": float(row.latitude), "lon": float(row.longitude)}

        monthly = sorted(source.period_id.unique())
        periods = {month: [month] for month in monthly}
        for quarter in quarter_labels:
            start = (int(quarter[-1]) - 1) * 3 + 1
            months = [f"{quarter[:4]}M{month:02d}" for month in range(start, start + 3)]
            if set(months) & set(monthly):
                periods[quarter] = months
        for period, months in periods.items():
            current = source[source.period_id.isin(months)]
            rows_by_market = {}
            for row in current.itertuples():
                pair = {row.origin_iata, row.dest_iata}
                if "MEX" not in pair or len(pair) != 2:
                    raise ValueError("Domestic Gold route is outside the AICM scope")
                market = "<>".join(sorted(pair))
                rows_by_market.setdefault(market, []).append(row)
            routes = []
            codes = {"MEX"}
            for market, rows in rows_by_market.items():
                sums = {}
                for row in rows:
                    direction = (row.origin_iata, row.dest_iata)
                    sums[direction] = sums.get(direction, 0) + int(row.scheduled_movements)
                if len(sums) != 2:
                    continue
                counterpart = next(code for code in market.split("<>") if code != "MEX")
                codes.add(counterpart)
                covered = sorted({row.period_id for row in rows})
                routes.append({
                    "market_key": market, "origin": endpoint("MEX"), "destination": endpoint(counterpart),
                    "departures": sum(sums.values()), "previous": {},
                    "directions": [{"origin_iata": origin, "destination_iata": dest, "departures": count}
                                   for (origin, dest), count in sorted(sums.items())],
                    "source_label": SOURCE,
                    "coverage_note": "Meses programados: " + ", ".join(month[5:] for month in covered)
                                     + " · AICM · ejecución sin verificar",
                    "operation_status": "assigned_slot_not_flown", "passengers_estimated": False,
                    "capacity_estimated": False, "support_repair_applied": False,
                })
            if not routes:
                continue
            routes.sort(key=lambda route: (-route["departures"], route["market_key"]))
            urls = current.source_url.unique()
            if len(urls) != 1:
                raise ValueError("Domestic Gold has conflicting source URLs")
            expected[period] = {
                "period_label": quarter_labels[period] if "Q" in period else f"{MONTHS[int(period[5:])]} {period[:4]}",
                "mode": "scheduled_domestic", "expected_months": months, "observed_months": [],
                "routes": routes, "airports": [endpoint(code) for code in sorted(codes)],
                "coverage_by_source": {SOURCE: sorted(current.period_id.unique())}, "source_url": str(urls[0]),
                "availability": "partial", "agent_eligible": False,
                "eligibility_reason": "Programación AICM; no confirma vuelos realizados ni cobertura nacional exhaustiva.",
                "aena_airport_activity": [],
            }
    expected_paths = {Path("domestic") / f"{period}.json" for period in expected}
    actual_paths = {p.relative_to(root) for p in root.rglob("*.json") if "domestic" in p.parts}
    if actual_paths != expected_paths:
        raise ValueError("Domestic schedule files/periods differ from pinned Gold")
    for period, network in expected.items():
        actual = json.loads((root / "domestic" / f"{period}.json").read_text())
        if _canonical(actual) != _canonical(network):
            raise ValueError(f"Domestic schedule values/directions/provenance differ from pinned Gold: {period}")
    available = copy.deepcopy(old["available_periods"])
    available["domestic"] = sorted(period for period in expected if "Q" in period)
    available["domestic_monthly"] = sorted(period for period in expected if "M" in period)
    for entity in available.get("entities", {}).values():
        entity["domestic_monthly"] = []
    if manifest["available_periods"] != available:
        raise ValueError("Flight period/entity listings differ from retained sources and pinned domestic Gold")
