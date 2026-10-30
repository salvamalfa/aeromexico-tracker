"""Aerocivil's provisional airport movement measure, outside flight totals."""

from __future__ import annotations

import math

import pandas as pd

LABEL = "Colombia · Aerocivil · movimientos registrados (provisional)"
DEFINITION = (
    "Movimientos registrados en el aeropuerto colombiano, códigos literales S/I; "
    "clasificación operacional provisional pendiente de confirmación oficial. "
    "No equivalen a salidas, pasajeros ni asientos; no acreditan el trimestre completo. "
    "Empresa y explotador son etiquetas derivadas de la fuente, sin confirmar comercializador o AOC."
)


def movement_payload(group):
    """Fail closed on legacy mistyped Gold; regenerate from retained originals."""
    required = {
        "metric_key",
        "operations",
        "departures",
        "passengers",
        "seats",
        "load_factor",
        "source_flight_type_code",
        "source_traffic_code",
        "commercial_designator_as_reported",
        "operator_icao",
        "origin_iata",
        "dest_iata",
        "period_id",
        "source_hash",
        "source_locator",
    }
    if not required.issubset(group.columns):
        raise ValueError("Regenerate Aerocivil Gold: missing recorded-movement semantics")
    if (
        not group.metric_key.eq("operations").all()
        or group[["departures", "passengers", "seats", "load_factor"]].notna().any().any()
        or not group.source_flight_type_code.eq("S").all()
        or not group.source_traffic_code.eq("I").all()
    ):
        raise ValueError("Aerocivil recorded movements cannot be consumed as departures or other metrics")
    grain = ["operator_icao", "commercial_designator_as_reported", "origin_iata", "dest_iata", "period_id"]
    if group.duplicated(grain).any():
        raise ValueError("Duplicate Aerocivil movement grain")
    components = []
    for row in group.sort_values(grain, na_position="last").to_dict("records"):
        count = row["operations"]
        if pd.isna(count) or not math.isfinite(float(count)) or not 0 <= count <= 2**53 - 1 or count % 1:
            raise ValueError("Explicit nonnegative integer movements required; missing is not zero")
        components.append(
            {
                "operator_icao": row["operator_icao"],
                "commercial_designator_as_reported": (
                    None
                    if pd.isna(row["commercial_designator_as_reported"])
                    else row["commercial_designator_as_reported"]
                ),
                "origin_iata": row["origin_iata"],
                "destination_iata": row["dest_iata"],
                "period_id": row["period_id"],
                "operations": float(count),
                "source_hash": row["source_hash"],
                "source_locator": row["source_locator"],
            }
        )
    return {
        "count": sum(c["operations"] for c in components),
        "source_label": LABEL,
        "observed_months": sorted(group.period_id.unique()),
        "definition": DEFINITION,
        "flight_type_code": "S",
        "traffic_code": "I",
        "provisional": True,
        "official_classification_confirmed": False,
        "agent_eligible": False,
        "components": components,
    }
