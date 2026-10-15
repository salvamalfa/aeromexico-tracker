"""Public airport demand; separate universe and grain from AFAC carriers.

Reject detail whose sum is the group's international subtotal rather than
its total. Preserve original Gold: quarantine affects this derived view only.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.config import PATHS


def build_market_demand(gold: Path | None = None) -> dict[str, Any]:
    gold = PATHS.gold if gold is None else gold
    airports = pd.read_parquet(gold / "fact_airport_traffic.parquet")
    groups = pd.read_parquet(gold / "fact_airport_group_traffic.parquet")
    airports = airports[airports.country.eq("Mexico")].copy()
    groups = groups[groups.country.eq("Mexico")].copy()
    for frame, key in [(airports, "airport_iata"), (groups, "airport_group_key")]:
        if frame.duplicated([key, "period_id"]).any():
            raise ValueError(f"Duplicate airport demand grain: {key}, period_id")
        if (frame.passengers_total.dropna() < 0).any():
            raise ValueError("Negative airport passengers")
    artifact_path = gold / "dim_source_artifact.parquet"
    source_urls = {}
    if artifact_path.is_file():
        artifacts = pd.read_parquet(artifact_path)
        source_urls = dict(zip(artifacts.artifact_sha256, artifacts.source_url))
    quarantined = []
    for row in groups.itertuples():
        mask = airports.operator_group.eq(row.airport_group_key) & airports.period_id.eq(row.period_id)
        detail = airports.loc[mask, "passengers_total"]
        if len(detail) and detail.notna().all() and pd.notna(row.passengers_international):
            if (
                abs(float(detail.sum()) - float(row.passengers_international)) <= 1
                and abs(float(detail.sum()) - float(row.passengers_total)) > 1
            ):
                quarantined.append(f"{row.airport_group_key}:{row.period_id}")
                airports.loc[mask, "passengers_total"] = pd.NA
    # A source-level mismatch in every reconciled month makes the unpaired
    # history unsafe too. Omit that group's detail until the parser is fixed.
    affected = {entry.split(":")[0] for entry in quarantined}
    airports = airports[~airports.operator_group.isin(affected)]

    def records(frame: pd.DataFrame, key: str) -> list[dict[str, Any]]:
        indexed = {(str(r[key]), str(r["period_id"])): r for r in frame.to_dict("records")}
        rows = []
        for row in frame.sort_values(["period_id", key]).to_dict("records"):
            period = str(row["period_id"])
            previous_period = f"{int(period[:4]) - 1}{period[4:]}"
            previous = indexed.get((str(row[key]), previous_period), {})
            current, prior = row["passengers_total"], previous.get("passengers_total")
            current = None if pd.isna(current) else int(current)
            prior = None if prior is None or pd.isna(prior) else int(prior)
            rows.append(
                {
                    "key": str(row[key]),
                    "group": str(row.get("operator_group", row[key])),
                    "period_id": period,
                    "passengers": current,
                    "previous_period": previous_period,
                    "previous_passengers": prior,
                    "yoy_pct": None
                    if current is None or prior is None or prior <= 0
                    else (current / prior - 1) * 100,
                    "source_system": str(row["source_system"]),
                    "source_hash": str(row["source_hash"]),
                    "source_url": source_urls.get(str(row["source_hash"])),
                    "captured_at": str(row["ingested_at"]),
                }
            )
        return rows

    return {
        "schema_version": "market_demand_v1",
        "universe": "Aeropuertos y grupos mexicanos disponibles en Gold; todas las compañías; movimientos de pasajeros, no viajeros únicos.",
        "months": sorted(set(airports.period_id) | set(groups.period_id)),
        "airports": records(airports, "airport_iata"),
        "groups": records(groups, "airport_group_key"),
        "quality_notes": [
            "Se excluyen aeropuertos extranjeros (GAP Jamaica) y no se suman grupos con sus aeropuertos.",
            "Detalle OMA retenido para revisión: los totales de aeropuertos coinciden con el subtotal internacional del grupo. Se conserva Gold sin modificar."
            if affected
            else "Sin discrepancia subtotal/total detectada en grupos reconciliables.",
            "Los totales aeroportuarios no son comparables con la participación AFAC por aerolínea mexicana. Los grupos se reportan únicamente para México.",
        ],
        "quarantined_group_months": quarantined,
    }
