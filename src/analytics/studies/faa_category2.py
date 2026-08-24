"""Descriptive difference-in-differences around FAA Category 2."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.analytics.common import warehouse_query


def run() -> tuple[dict[str, object], dict[str, object]]:
    frame = warehouse_query(
        """
        SELECT f.carrier_key, f.period_id, SUM(f.asm_miles) AS asm_miles
        FROM fact_route_traffic f JOIN dim_route r USING (route_key)
        WHERE r.is_transborder_us AND f.carrier_key IN ('AEROMEXICO','DELTA')
        GROUP BY ALL ORDER BY period_id, carrier_key
        """
    )
    wide = frame.pivot(index="period_id", columns="carrier_key", values="asm_miles").fillna(0).reset_index()
    wide["regime"] = np.select(
        [wide["period_id"].lt("2021M05"), wide["period_id"].le("2023M09")],
        ["pre", "category_2"], default="post",
    )
    wide["log_ratio"] = np.log1p(wide["AEROMEXICO"]) - np.log1p(wide["DELTA"])
    means = wide.groupby("regime")["log_ratio"].mean()
    during = float(np.expm1(means["category_2"] - means["pre"]))
    post = float(np.expm1(means["post"] - means["category_2"]))
    finding = (
        f"Frente a Delta en las rutas México-EE.UU., la razón de ASM de Aeroméxico cambió {during:+.1%} durante Categoría 2 "
        f"respecto al periodo previo y {post:+.1%} después de la recuperación de Categoría 1."
    )
    return {
        "study_key": "faa_category2", "title_es": "Impacto de Categoría 2 de la FAA",
        "finding_es": finding, "estimate": during, "unit": "log_ratio_change_pct",
        "period_id": "2021M05-2023M09", "comparison": "pre-2021M05 versus Delta",
        "confidence": "media", "caveat": "Experimento natural descriptivo con Delta como control; choques simultáneos impiden una afirmación causal estricta.",
        "source_tables": "fact_route_traffic|dim_route",
    }, {"regime_log_ratios": means.to_dict(), "during_effect": during, "post_effect": post, "months": len(wide)}
