"""Precompute bounded dashboard extracts; never runs models."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd

from src.analytics.common import warehouse_query, write_gold
from src.config import PATHS
from src.analytics.studies.spread import run as run_spread
from src.analytics.eda import build_coverage
from src.transform.generate_data_dictionary import generate as generate_dictionary
from src.transform.stage6_warehouse import build_warehouse


def build_route_summary() -> pd.DataFrame:
    frame = warehouse_query(
        """
        SELECT f.carrier_key, r.market_key, f.period_id,
               MIN(r.origin_iata) AS origin_iata, MAX(r.dest_iata) AS dest_iata,
               SUM(f.seats) AS seats, SUM(f.passengers) AS passengers,
               SUM(f.asm_miles) AS asm_miles, SUM(f.rpm_miles) AS rpm_miles,
               SUM(f.departures_performed) AS departures,
               STRING_AGG(DISTINCT f.source_file, ' | ' ORDER BY f.source_file) AS source_files,
               MAX(f.ingested_at) AS ingested_at
        FROM fact_route_traffic f JOIN dim_route r USING (route_key)
        GROUP BY f.carrier_key, r.market_key, f.period_id
        ORDER BY f.carrier_key, r.market_key, f.period_id
        """
    )
    endpoints = frame["market_key"].str.split("<>", expand=True)
    frame["origin_iata"] = endpoints[0]
    frame["dest_iata"] = endpoints[1]
    frame["load_factor"] = frame["rpm_miles"] / frame["asm_miles"].replace(0, np.nan)
    frame["source_hash"] = frame.apply(
        lambda row: hashlib.sha256(
            f"{row.carrier_key}|{row.market_key}|{row.period_id}|{row.source_files}".encode()
        ).hexdigest(), axis=1,
    )
    columns = [
        "carrier_key", "market_key", "period_id", "origin_iata", "dest_iata",
        "seats", "passengers", "asm_miles", "rpm_miles", "departures",
        "load_factor", "source_files", "source_hash", "ingested_at",
    ]
    return frame[columns]


def build_spread_decomposition() -> pd.DataFrame:
    finding, details = run_spread()
    labels = {
        "price_rask": "Precio / RASK",
        "fuel_cost_proxy": "Combustible",
        "structural_cost_residual": "Costo estructural residual",
        "fx_separate": "FX no identificado",
    }
    rows = []
    for order, (component, value) in enumerate(details["components"].items(), start=1):
        rows.append(
            {
                "period_id": finding["period_id"],
                "comparison_period_id": finding["comparison"],
                "component_key": component,
                "component_name_es": labels[component],
                "contribution": value,
                "display_order": order,
                "is_identified": value is not None,
                "caveat": finding["caveat"],
                "source_tables": finding["source_tables"],
            }
        )
    return pd.DataFrame(rows)


def build_dashboard_coverage() -> pd.DataFrame:
    frame = build_coverage().copy()
    def expected(row: pd.Series) -> int:
        first, last = str(row["first_period"]), str(row["last_period"])
        if row["period_type"] == "month":
            return (int(last[:4]) - int(first[:4])) * 12 + int(last[-2:]) - int(first[-2:]) + 1
        if row["period_type"] == "quarter":
            return (int(last[:4]) - int(first[:4])) * 4 + int(last[-1]) - int(first[-1]) + 1
        if row["period_type"] == "year":
            return int(last[:4]) - int(first[:4]) + 1
        return int(row["observations"])
    frame["expected_periods"] = frame.apply(expected, axis=1).astype(int)
    frame["coverage_pct"] = frame["observations"] / frame["expected_periods"].replace(0, np.nan)
    return frame[[
        "carrier_key", "metric_key", "period_type", "segment", "observations",
        "first_period", "last_period", "expected_periods", "coverage_pct", "null_values",
    ]]


def run() -> dict[str, object]:
    summary = build_route_summary()
    spread = build_spread_decomposition()
    coverage = build_dashboard_coverage()
    write_gold("fact_route_traffic_summary", summary)
    write_gold("fact_spread_decomposition", spread)
    write_gold("fact_dashboard_coverage", coverage)
    views = build_warehouse(max_stage=8)
    generate_dictionary()
    result = {
        "parser_version": "stage8_v1.0.0",
        "fact_route_traffic_summary_rows": len(summary),
        "fact_spread_decomposition_rows": len(spread),
        "fact_dashboard_coverage_rows": len(coverage),
        "first_period": summary["period_id"].min(),
        "last_period": summary["period_id"].max(),
        "views": [view for view in views if view.startswith("v_dashboard")],
    }
    (PATHS.quality / "stage8_prepare.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
