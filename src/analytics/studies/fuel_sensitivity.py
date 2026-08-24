"""Estimate a deliberately low-confidence fuel sensitivity."""

from __future__ import annotations

import numpy as np
import statsmodels.api as sm

from src.analytics.common import warehouse_query


def run() -> tuple[dict[str, object], dict[str, object]]:
    frame = warehouse_query(
        """
        WITH cask AS (
          SELECT period_id, value AS cask
          FROM v_carrier_default
          WHERE carrier_key='AEROMEXICO' AND period_type='quarter' AND segment='total' AND metric_key='cask'
        ), fuel AS (
          SELECT period_id, value AS fuel
          FROM fact_macro WHERE period_type='quarter' AND aggregation='average' AND indicator_key='jet_fuel_usd_per_gallon'
        )
        SELECT c.period_id, c.cask, f.fuel FROM cask c JOIN fuel f USING (period_id) ORDER BY period_id
        """
    )
    frame["log_cask"] = np.log(frame["cask"])
    frame["log_fuel_lag1"] = np.log(frame["fuel"].shift(1))
    sample = frame.dropna()
    fitted = sm.OLS(sample["log_cask"], sm.add_constant(sample[["log_fuel_lag1"]])).fit()
    elasticity = float(fitted.params["log_fuel_lag1"])
    finding = f"La elasticidad descriptiva de CASK ante combustible rezagado es {elasticity:+.2f}, pero se basa en solo {len(sample)} trimestres y no es concluyente."
    return {
        "study_key": "fuel_sensitivity", "title_es": "Sensibilidad al combustible",
        "finding_es": finding, "estimate": elasticity, "unit": "elasticity",
        "period_id": str(frame["period_id"].max()), "comparison": "one-quarter lagged jet fuel",
        "confidence": "baja", "caveat": f"Solo hay {len(sample)} trimestres utilizables; no se modelan variables omitidas ni coberturas de combustible.",
        "source_tables": "v_carrier_default|fact_macro",
    }, {"observations": len(sample), "r_squared": float(fitted.rsquared), "p_value": float(fitted.pvalues["log_fuel_lag1"])}
