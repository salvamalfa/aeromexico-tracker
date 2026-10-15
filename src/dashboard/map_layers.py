"""Dated official movement records, kept separate from estimated frequencies."""

from __future__ import annotations


def dated_movements(frame, metric: str) -> list[dict]:
    return [{"period_id": str(period), "origin_iata": str(origin), "destination_iata": str(destination),
             "departures": float(group[metric].sum()), "passengers": None, "seats": None,
             "load_factor": None, "capacity_estimated": False}
            for (period, origin, destination), group in frame.groupby(["period_id", "origin_iata", "dest_iata"])]
