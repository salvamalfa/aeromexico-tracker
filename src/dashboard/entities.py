"""Dashboard entities: the three Mexican carriers and their aggregate, "Industria".

The v2 dashboard shows one universe on screen: *Industria* = Aeroméxico +
Volaris + Viva, the Mexican carriers that publish comparable quarterly unit
economics (together ~99 % of the passengers AFAC counts for Mexican carriers;
see docs/etapas/dashboard-v2-fase0-datos-20260928.md).

Aggregation rules (never a simple average of ratios):

- additive metrics (passengers, ASK) are summed;
- ratios (RASK, CASK, CASK ex-fuel, load factor) are ASK-weighted, i.e. the
  ratio of the sums: RASK_industry = Σ(RASK_i · ASK_i) / Σ ASK_i, which equals
  Σ revenue / Σ ASK because each carrier's RASK is its revenue per ASK;
- the industry exists only in quarters where all three carriers have a
  complete record (a constant panel), so the series never jumps because a
  carrier enters or leaves;
- a metric one carrier does not publish (Aeroméxico's CASK ex-fuel before
  3T24) leaves the industry value as ``None``; nothing is imputed.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

import duckdb
import pandas as pd


@dataclass(frozen=True, slots=True)
class Entity:
    key: str
    label: str
    # Grammatical subject for generated sentences ("Aeroméxico ofreció…",
    # "La industria ofreció…").
    subject: str
    carriers: tuple[str, ...]
    note: str

    @property
    def is_aggregate(self) -> bool:
        return len(self.carriers) > 1


CARRIER_ENTITIES: tuple[Entity, ...] = (
    Entity(
        key="AEROMEXICO",
        label="Aeroméxico",
        subject="Aeroméxico",
        carriers=("AEROMEXICO",),
        note="Grupo Aeroméxico (Aerovías de México + Aeroméxico Connect), reporte trimestral consolidado.",
    ),
    Entity(
        key="VOLARIS",
        label="Volaris",
        subject="Volaris",
        carriers=("VOLARIS",),
        note="Controladora Vuela (Volaris), release trimestral 6-K; consolida sus operaciones de Costa Rica y El Salvador.",
    ),
    Entity(
        key="VIVA_AEROBUS",
        label="Viva",
        subject="Viva",
        carriers=("VIVA_AEROBUS",),
        note="Viva Aerobus, reporte trimestral oficial; pasajeros reservados (booked).",
    ),
)

INDUSTRY = Entity(
    key="INDUSTRY",
    label="Industria",
    subject="La industria",
    carriers=tuple(entity.key for entity in CARRIER_ENTITIES),
    note=(
        "Industria = Aeroméxico, Volaris y Viva. Pasajeros y ASK se suman; "
        "RASK, CASK y ocupación se ponderan por ASK (cociente de sumas). "
        "Solo trimestres en que reportan las tres."
    ),
)

ENTITIES: tuple[Entity, ...] = (INDUSTRY, *CARRIER_ENTITIES)
ENTITY_BY_KEY: dict[str, Entity] = {entity.key: entity for entity in ENTITIES}

QUARTERLY_QUERY = """
SELECT
    carrier_key,
    period_id,
    MAX(value) FILTER (WHERE metric_key = 'passengers') AS passengers,
    MAX(value_metric) FILTER (WHERE metric_key = 'asm_total') AS ask_km,
    MAX(value) FILTER (WHERE metric_key = 'load_factor_total') AS load_factor_reported,
    MAX(value) FILTER (WHERE metric_key = 'load_factor_derived') AS load_factor_derived,
    MAX(value) FILTER (WHERE metric_key = 'rask') AS rask_cents_per_km,
    MAX(value) FILTER (WHERE metric_key = 'cask') AS cask_cents_per_km,
    MAX(value) FILTER (WHERE metric_key = 'cask_ex_fuel') AS cask_ex_fuel_cents_per_km,
    MAX(value_metric) FILTER (WHERE metric_key = 'rpm_total') AS rpk_km,
    MAX(value) FILTER (WHERE metric_key = 'unit_margin') AS unit_margin_cents_per_km
FROM v_carrier_default
WHERE carrier_key IN ({carriers})
  AND period_type = 'quarter'
  AND segment = 'total'
GROUP BY carrier_key, period_id
ORDER BY carrier_key, period_id
"""

CORE_COLUMNS = (
    "passengers",
    "ask_km",
    "load_factor",
    "rask_cents_per_km",
    "cask_cents_per_km",
    "unit_margin_cents_per_km",
)


def _finite_or_none(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Carrier metric is not finite: {value!r}")
    return number


def load_carrier_quarters(connection: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """One row per carrier and complete quarter, from the canonical default view.

    The load factor is the reported one when the carrier publishes it with a
    stable definition, otherwise RPM/ASM (``load_factor_basis`` records which).
    A quarter missing any core metric is dropped for that carrier, never filled.
    """

    carriers = ", ".join(f"'{entity.key}'" for entity in CARRIER_ENTITIES)
    frame = connection.execute(QUARTERLY_QUERY.format(carriers=carriers)).df()
    frame["load_factor"] = frame["load_factor_reported"].where(
        frame["load_factor_reported"].notna(), frame["load_factor_derived"]
    )
    frame["load_factor_basis"] = frame["load_factor_reported"].notna().map(
        {True: "reported", False: "calculated"}
    )
    complete = frame.dropna(subset=list(CORE_COLUMNS)).copy()
    if complete.empty:
        raise ValueError("No complete carrier quarter in v_carrier_default")
    if not complete["period_id"].astype(str).str.fullmatch(r"\d{4}Q[1-4]").all():
        raise ValueError("Carrier quarters contain an invalid quarter identifier")
    if (complete[["passengers", "ask_km", "rask_cents_per_km", "cask_cents_per_km"]] <= 0).any().any():
        raise ValueError("Carrier quarters contain a non-positive business metric")
    if not complete["load_factor"].between(0, 1).all():
        raise ValueError("Carrier load factor must be stored as a fraction")
    margin = complete["rask_cents_per_km"] - complete["cask_cents_per_km"]
    if not (margin - complete["unit_margin_cents_per_km"]).abs().le(1e-9).all():
        raise ValueError("Carrier unit margin does not reconcile to RASK - CASK")
    columns = [
        "carrier_key", "period_id", *CORE_COLUMNS, "load_factor_basis", "cask_ex_fuel_cents_per_km", "rpk_km",
    ]
    return complete[columns].sort_values(["carrier_key", "period_id"]).reset_index(drop=True)


def aggregate_industry(carrier_quarters: pd.DataFrame) -> pd.DataFrame:
    """ASK-weighted industry quarters over the constant three-carrier panel."""

    members = set(INDUSTRY.carriers)
    frame = carrier_quarters[carrier_quarters["carrier_key"].isin(members)]
    counts = frame.groupby("period_id")["carrier_key"].nunique()
    panel = counts[counts == len(members)].index
    rows: list[dict[str, Any]] = []
    for period_id, group in frame[frame["period_id"].isin(panel)].groupby("period_id"):
        ask = group["ask_km"]
        total_ask = float(ask.sum())
        rask = float((group["rask_cents_per_km"] * ask).sum() / total_ask)
        cask = float((group["cask_cents_per_km"] * ask).sum() / total_ask)
        ex_fuel = group["cask_ex_fuel_cents_per_km"]
        rpk = group["rpk_km"]
        rows.append(
            {
                "carrier_key": INDUSTRY.key,
                "period_id": str(period_id),
                "passengers": float(group["passengers"].sum()),
                "ask_km": total_ask,
                "load_factor": float((group["load_factor"] * ask).sum() / total_ask),
                "rask_cents_per_km": rask,
                "cask_cents_per_km": cask,
                "unit_margin_cents_per_km": rask - cask,
                "load_factor_basis": (
                    "reported" if (group["load_factor_basis"] == "reported").all() else "calculated"
                ),
                "rpk_km": float(rpk.sum()) if rpk.notna().all() else None,
                "cask_ex_fuel_cents_per_km": (
                    float((ex_fuel * ask).sum() / total_ask) if ex_fuel.notna().all() else None
                ),
            }
        )
    return pd.DataFrame(rows, columns=carrier_quarters.columns)


def load_entity_quarters(connection: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]:
    """Complete quarters for every entity, keyed by entity key."""

    carriers = load_carrier_quarters(connection)
    result = {INDUSTRY.key: aggregate_industry(carriers)}
    for entity in CARRIER_ENTITIES:
        result[entity.key] = (
            carriers[carriers["carrier_key"] == entity.key].reset_index(drop=True)
        )
    return result


def entity_metadata() -> list[dict[str, Any]]:
    return [
        {
            "key": entity.key,
            "label": entity.label,
            "is_aggregate": entity.is_aggregate,
            "carriers": list(entity.carriers),
            "note": entity.note,
        }
        for entity in ENTITIES
    ]
