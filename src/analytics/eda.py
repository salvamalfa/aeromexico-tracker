"""Exploratory analysis required before Stage 7 modeling."""

from __future__ import annotations

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

from src.analytics.common import ANALYTICS_DIR, warehouse_query
from src.ingest.stage4_common import write_parquet_atomic


def _monthly_date(period_id: pd.Series) -> pd.Series:
    return pd.to_datetime(period_id.str.replace("M", "-", regex=False) + "-01")


def build_coverage() -> pd.DataFrame:
    return warehouse_query(
        """
        SELECT carrier_key, metric_key, period_type, segment,
               COUNT(*) AS observations, MIN(period_id) AS first_period,
               MAX(period_id) AS last_period,
               COUNT(DISTINCT period_id) AS distinct_periods,
               SUM(CASE WHEN value IS NULL THEN 1 ELSE 0 END) AS null_values
        FROM v_carrier_default
        GROUP BY ALL
        ORDER BY carrier_key, metric_key, period_type, segment
        """
    )


def build_descriptives() -> pd.DataFrame:
    return warehouse_query(
        """
        SELECT carrier_key, metric_key, period_type, segment,
               COUNT(value) AS observations, AVG(value) AS mean,
               MEDIAN(value) AS median, STDDEV_SAMP(value) AS std_dev,
               MIN(value) AS minimum, MAX(value) AS maximum
        FROM v_carrier_default
        GROUP BY ALL
        ORDER BY carrier_key, metric_key, period_type, segment
        """
    )


def build_seasonality() -> tuple[pd.DataFrame, dict[str, float]]:
    series = warehouse_query(
        """
        SELECT period_id, value
        FROM v_carrier_default
        WHERE carrier_key='AEROMEXICO' AND metric_key='passengers_afac'
          AND period_type='month' AND segment='total'
        ORDER BY period_id
        """
    )
    series["date"] = _monthly_date(series["period_id"])
    values = series.set_index("date")["value"].astype(float).asfreq("MS")
    if values.isna().any() or len(values) < 36:
        raise ValueError("AEROMEXICO monthly passengers must be complete for STL")
    result = STL(values, period=12, robust=True).fit()
    output = pd.DataFrame(
        {
            "period_id": series["period_id"],
            "observed": values.to_numpy(),
            "trend": result.trend.to_numpy(),
            "seasonal": result.seasonal.to_numpy(),
            "residual": result.resid.to_numpy(),
        }
    )
    amplitude = float(result.seasonal.max() - result.seasonal.min())
    trend_median = float(np.nanmedian(result.trend))
    stats = {
        "observations": len(output),
        "seasonal_amplitude_passengers": amplitude,
        "seasonal_amplitude_pct_of_median_trend": amplitude / trend_median,
        "strongest_month": int(values.index[np.argmax(result.seasonal)].month),
        "weakest_month": int(values.index[np.argmin(result.seasonal)].month),
    }
    return output, stats


def build_lag_correlations() -> pd.DataFrame:
    passengers = warehouse_query(
        """
        SELECT period_id, value AS passengers
        FROM v_carrier_default
        WHERE carrier_key='AEROMEXICO' AND metric_key='passengers_afac'
          AND period_type='month' AND segment='total'
        ORDER BY period_id
        """
    )
    macro = warehouse_query(
        """
        SELECT period_id, indicator_key, value
        FROM fact_macro
        WHERE period_type='month' AND aggregation='average'
        ORDER BY period_id, indicator_key
        """
    )
    wide = macro.pivot_table(index="period_id", columns="indicator_key", values="value", aggfunc="first")
    joined = passengers.set_index("period_id").join(wide, how="inner")
    rows: list[dict[str, object]] = []
    for indicator in wide.columns:
        for lag in range(7):
            pair = joined[["passengers", indicator]].copy()
            pair[indicator] = pair[indicator].shift(lag)
            pair = pair.dropna()
            rows.append(
                {
                    "indicator_key": indicator,
                    "lag_months": lag,
                    "correlation": pair["passengers"].corr(pair[indicator]),
                    "observations": len(pair),
                }
            )
    return pd.DataFrame(rows).sort_values(["indicator_key", "lag_months"])


def build_structural_breaks(seasonality: pd.DataFrame) -> pd.DataFrame:
    values = seasonality["residual"].to_numpy(dtype=float)
    periods = seasonality["period_id"].tolist()
    rows: list[dict[str, object]] = []
    for index in range(24, len(values) - 24):
        left = values[max(0, index - 24):index]
        right = values[index:min(len(values), index + 24)]
        pooled = np.sqrt((np.var(left, ddof=1) + np.var(right, ddof=1)) / 2)
        score = 0.0 if pooled == 0 else abs(np.mean(right) - np.mean(left)) / pooled
        rows.append({"break_period": periods[index], "standardized_mean_shift": score})
    frame = pd.DataFrame(rows).sort_values("standardized_mean_shift", ascending=False)
    frame["rank"] = np.arange(1, len(frame) + 1)
    frame["is_known_regime"] = frame["break_period"].between("2020M03", "2023M09")
    return frame.head(12).sort_values("rank")


def run_eda() -> dict[str, object]:
    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    coverage = build_coverage()
    descriptives = build_descriptives()
    seasonality, seasonal_stats = build_seasonality()
    correlations = build_lag_correlations()
    breaks = build_structural_breaks(seasonality)
    outputs = {
        "coverage": coverage,
        "descriptives": descriptives,
        "seasonality": seasonality,
        "correlations": correlations,
        "structural_breaks": breaks,
        "seasonal_stats": seasonal_stats,
        "covid_policy": "retain_with_explicit_dummy",
    }
    for name, frame in outputs.items():
        if isinstance(frame, pd.DataFrame):
            write_parquet_atomic(frame, ANALYTICS_DIR / f"eda_{name}.parquet")
    return outputs


if __name__ == "__main__":
    result = run_eda()
    print({key: len(value) if isinstance(value, pd.DataFrame) else value for key, value in result.items()})
