"""Dated official movement records, kept separate from estimated frequencies."""

from __future__ import annotations


def dated_movements(frame, metric: str) -> list[dict]:
    return [{"period_id": str(period), "origin_iata": str(origin), "destination_iata": str(destination),
             "departures": float(group[metric].sum()), "passengers": None, "seats": None,
             "load_factor": None, "capacity_estimated": False}
            for (period, origin, destination), group in frame.groupby(["period_id", "origin_iata", "dest_iata"])]


def supported_estimate_items(items: list[dict], months: set[str], directions: list[dict]) -> list[dict]:
    """Enrich only the months and directions the route's own source covers."""
    pairs = {(item["origin_iata"], item["destination_iata"]) for item in directions}
    return [item for item in items if item["period_id"] in months and (
        not pairs or (item["origin_iata"], item["destination_iata"]) in pairs)]
