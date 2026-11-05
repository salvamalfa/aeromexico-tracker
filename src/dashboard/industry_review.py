"""Explicit local preview of Industry from the three published issuer records.

Not called by the publication gate or the ordinary dashboard exporter. An exact
data projection still needs its own review before a production publication.
"""

import copy
import math

import pandas as pd

from src.dashboard.entities import INDUSTRY, aggregate_industry
from src.dashboard.executive_summary import _entity_kpi_definitions, _entity_record, _period_view

HEADLINE = "Industria calculada · vista previa para revisión"


def build_industry_review(payload: dict, period: str) -> dict:
    return build_industry_period(payload, period, review=True)


def build_industry_period(payload: dict, period: str, *, review: bool) -> dict:
    """Shared aggregation; publication callers separately verify source/authority."""
    inputs = []
    keys = (
        "passengers",
        "ask_km",
        "rpk_km",
        "load_factor",
        "load_factor_basis",
        "rask_cents_per_km",
        "cask_cents_per_km",
        "cask_ex_fuel_cents_per_km",
        "unit_margin_cents_per_km",
    )
    for entity in INDUSTRY.carriers:
        block = payload["entities"][entity]
        rows = [row for row in block["records"] if row["period_id"] == period]
        if len(rows) != 1 or period not in block["views"]:
            raise ValueError(f"Missing or ambiguous published issuer record: {entity} {period}")
        values = {key: rows[0][key] for key in keys}
        if any(
            type(values[key]) not in (int, float) or not math.isfinite(values[key])
            for key in keys
            if key != "load_factor_basis"
        ):
            raise ValueError("Industry preview requires finite source values from all three issuers")
        if values["ask_km"] <= 0 or not 0 <= values["load_factor"] <= 1:
            raise ValueError("Invalid issuer capacity or occupancy")
        inputs.append({"carrier_key": entity, "period_id": period, **values})
    result = copy.deepcopy(payload)
    industry = result["entities"]["INDUSTRY"]
    if any(row["period_id"] == period for row in industry["records"]):
        raise ValueError("Do not replace an existing industry period with a review projection")
    record = _entity_record(aggregate_industry(pd.DataFrame(inputs)).iloc[0])
    by_period = {row["period_id"]: row for row in industry["records"]}
    by_period[period] = record
    view = _period_view(
        record,
        by_period,
        definitions=_entity_kpi_definitions(INDUSTRY, record["load_factor_basis"]),
        load_key="load_factor",
        subject=INDUSTRY.subject,
        load_verb="registró",
    )
    # Source/method notes only, never a new editorial analysis or thesis.
    view["conclusions"] = []
    view["narrative"] = {
        "headline": HEADLINE if review else "Bases de los indicadores de Industria",
        "paragraphs": [
            (
                "Industria calculada con los tres reportes financieros de Aeroméxico, Viva y Volaris. "
                + ("Pendiente de revisión para su publicación." if review else
                   "Agregado calculado; conserva las definiciones de pasajeros y costos de cada emisor.")
            ),
            (
                "Pasajeros, ASK y RPK se suman. RASK, CASK y ocupación reportada se ponderan por ASK; "
                "el margen unitario es RASK menos CASK. No es un promedio simple ni un dato AFAC."
            ),
            (
                "Los comparativos se calculan contra el histórico conservado. Los pasajeros y costos "
                "mantienen las definiciones y el redondeo de cada emisor; "
                "no se sustituyen por un total del estado de resultados."
            ),
        ],
    }
    industry["records"].append(record)
    industry["records"].sort(key=lambda row: row["period_id"])
    industry["views"][period] = view
    industry["last_period"] = industry["records"][-1]["period_id"]
    industry["quarter_count"] = len(industry["records"])
    return result
