"""Decompose the latest quarter-on-quarter change in RASK-CASK spread."""

from __future__ import annotations

import pandas as pd

from src.analytics.common import warehouse_query


def run() -> tuple[dict[str, object], dict[str, object]]:
    frame = warehouse_query(
        """
        SELECT period_id,
               MAX(value) FILTER (WHERE metric_key='rask') AS rask,
               MAX(value) FILTER (WHERE metric_key='cask') AS cask,
               MAX(value) FILTER (WHERE metric_key='jet_fuel_expense') AS fuel_expense_usd,
               MAX(value_metric) FILTER (WHERE metric_key='asm_total') AS ask_km
        FROM v_carrier_default
        WHERE carrier_key='AEROMEXICO' AND period_type='quarter' AND segment='total'
        GROUP BY period_id ORDER BY period_id
        """
    ).dropna(subset=["rask", "cask", "fuel_expense_usd", "ask_km"])
    frame["fuel_cask"] = frame["fuel_expense_usd"] / frame["ask_km"] * 100
    frame["spread"] = frame["rask"] - frame["cask"]
    previous, current = frame.iloc[-2], frame.iloc[-1]
    price = float(current["rask"] - previous["rask"])
    fuel = float(-(current["fuel_cask"] - previous["fuel_cask"]))
    structural = float(-(current["cask"] - previous["cask"]) - fuel)
    total = float(current["spread"] - previous["spread"])
    components = {"price_rask": price, "fuel_cost_proxy": fuel, "structural_cost_residual": structural, "fx_separate": None}
    finding = (
        f"El spread RASK-CASK cambió {total:+.2f} centavos por ASK entre {previous['period_id']} y {current['period_id']}. "
        f"Precio aportó {price:+.2f}, combustible {fuel:+.2f} y el costo estructural residual {structural:+.2f}; "
        "FX no puede aislarse con las divulgaciones disponibles y no se estimó."
    )
    return {
        "study_key": "spread_decomposition", "title_es": "Descomposición del spread RASK-CASK",
        "finding_es": finding, "estimate": total, "unit": "cents_per_ask_km",
        "period_id": str(current["period_id"]), "comparison": str(previous["period_id"]),
        "confidence": "media", "caveat": "Combustible es un proxy de gasto reportado por ASK; FX queda dentro del residual estructural y no se identifica por separado.",
        "source_tables": "v_carrier_default",
    }, {"components": components, "start_spread": float(previous["spread"]), "end_spread": float(current["spread"])}
