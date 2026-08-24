"""Leakage-safe forecasting with seasonal-naive publication gate."""

from __future__ import annotations

import json
import math
import pickle
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.statespace.sarimax import SARIMAX

from src.analytics.common import MODELS_DIR, code_version, model_run_id, reproducible_timestamp, warehouse_query, write_json


FORECAST_HORIZON = 12
SEASONAL_PERIOD = 12
MODELS = ("naive", "seasonal_naive", "drift", "ets_damped", "sarima")


def load_target() -> pd.Series:
    frame = warehouse_query(
        """
        SELECT period_id, value
        FROM v_carrier_default
        WHERE carrier_key='AEROMEXICO' AND metric_key='passengers_afac'
          AND period_type='month' AND segment='total'
        ORDER BY period_id
        """
    )
    index = pd.to_datetime(frame["period_id"].str.replace("M", "-", regex=False) + "-01")
    series = pd.Series(frame["value"].to_numpy(dtype=float), index=index, name="passengers_afac").asfreq("MS")
    if len(series) < 60 or series.isna().any():
        raise ValueError("Monthly passenger target needs at least 60 complete observations")
    return series


def _fit_predict(train: pd.Series, model_name: str, horizon: int = 1) -> tuple[np.ndarray, np.ndarray, object | None]:
    if model_name == "naive":
        prediction = np.repeat(train.iloc[-1], horizon)
        sigma = float(train.diff().dropna().std())
        return prediction, np.arange(1, horizon + 1) ** 0.5 * sigma, None
    if model_name == "seasonal_naive":
        repetitions = int(math.ceil(horizon / SEASONAL_PERIOD))
        prediction = np.tile(train.iloc[-SEASONAL_PERIOD:].to_numpy(), repetitions)[:horizon]
        sigma = float(train.diff(SEASONAL_PERIOD).dropna().std())
        return prediction, np.arange(1, horizon + 1) ** 0.5 * sigma, None
    if model_name == "drift":
        slope = (train.iloc[-1] - train.iloc[0]) / max(len(train) - 1, 1)
        prediction = train.iloc[-1] + slope * np.arange(1, horizon + 1)
        sigma = float((train.diff() - slope).dropna().std())
        return np.asarray(prediction), np.arange(1, horizon + 1) ** 0.5 * sigma, None
    if model_name == "ets_damped":
        fitted = ExponentialSmoothing(
            train,
            trend="add",
            damped_trend=True,
            seasonal="add",
            seasonal_periods=SEASONAL_PERIOD,
            initialization_method="estimated",
        ).fit(optimized=True, use_brute=False)
        prediction = np.asarray(fitted.forecast(horizon), dtype=float)
        sigma = float(np.std(fitted.resid, ddof=1))
        return prediction, np.arange(1, horizon + 1) ** 0.5 * sigma, fitted
    if model_name == "sarima":
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fitted = SARIMAX(
                train,
                order=(1, 1, 1),
                seasonal_order=(0, 1, 1, SEASONAL_PERIOD),
                trend="t",
                enforce_stationarity=False,
                enforce_invertibility=False,
            ).fit(disp=False, maxiter=150)
        forecast = fitted.get_forecast(horizon)
        return np.asarray(forecast.predicted_mean), np.asarray(forecast.se_mean), fitted
    raise KeyError(model_name)


def _walk_forward(series: pd.Series, start: int, end: int, model_name: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for origin in range(start, end):
        train = series.iloc[:origin]
        prediction, standard_error, _ = _fit_predict(train, model_name, 1)
        rows.append(
            {
                "date": series.index[origin],
                "actual": float(series.iloc[origin]),
                "forecast": float(prediction[0]),
                "standard_error": float(standard_error[0]),
                "trained_through": series.index[origin - 1],
            }
        )
    return pd.DataFrame(rows)


def _metrics(actual: np.ndarray, forecast: np.ndarray, training: pd.Series) -> dict[str, float]:
    error = actual - forecast
    nonzero = actual != 0
    scale = float(np.mean(np.abs(training.diff(SEASONAL_PERIOD).dropna())))
    return {
        "mape": float(np.mean(np.abs(error[nonzero] / actual[nonzero]))) if nonzero.any() else np.nan,
        "smape": float(np.mean(2 * np.abs(error) / np.maximum(np.abs(actual) + np.abs(forecast), 1e-12))),
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "mase": float(np.mean(np.abs(error)) / scale) if scale else np.nan,
    }


def run_forecast() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    series = load_target()
    validation_start = len(series) - 24
    test_start = len(series) - 12
    validation_runs: dict[str, pd.DataFrame] = {}
    test_runs: dict[str, pd.DataFrame] = {}
    for name in MODELS:
        validation_runs[name] = _walk_forward(series, validation_start, test_start, name)
    candidate = min(
        (name for name in MODELS if name not in {"naive", "seasonal_naive", "drift"}),
        key=lambda name: _metrics(
            validation_runs[name]["actual"].to_numpy(),
            validation_runs[name]["forecast"].to_numpy(),
            series.iloc[:validation_start],
        )["smape"],
    )
    for name in MODELS:
        test_runs[name] = _walk_forward(series, test_start, len(series), name)

    config = {
        "target": "AEROMEXICO/passengers_afac/total/month",
        "validation_periods": 12,
        "test_periods": 12,
        "horizon": FORECAST_HORIZON,
        "candidate_selected_on_validation": candidate,
        "seed": 1561861,
    }
    run_id = model_run_id(config)
    baseline_test = _metrics(
        test_runs["seasonal_naive"]["actual"].to_numpy(),
        test_runs["seasonal_naive"]["forecast"].to_numpy(),
        series.iloc[:test_start],
    )
    performance_rows: list[dict[str, object]] = []
    for name in MODELS:
        validation_metrics = _metrics(
            validation_runs[name]["actual"].to_numpy(),
            validation_runs[name]["forecast"].to_numpy(),
            series.iloc[:validation_start],
        )
        test_metrics = _metrics(
            test_runs[name]["actual"].to_numpy(),
            test_runs[name]["forecast"].to_numpy(),
            series.iloc[:test_start],
        )
        performance_rows.append(
            {
                "model_run_id": run_id,
                "model_name": name,
                "carrier_key": "AEROMEXICO",
                "metric_key": "passengers_afac",
                "evaluation_split": "test",
                "validation_smape": validation_metrics["smape"],
                **test_metrics,
                "observations": len(test_runs[name]),
                "is_baseline": name in {"naive", "seasonal_naive", "drift"},
                "beats_seasonal_naive": test_metrics["smape"] < baseline_test["smape"],
                "is_published": False,
                "trained_through_period": series.index[test_start - 1].strftime("%YM%m"),
            }
        )
    performance = pd.DataFrame(performance_rows)
    publish = bool(
        performance.loc[performance["model_name"].eq(candidate), "beats_seasonal_naive"].iloc[0]
    )
    performance.loc[performance["model_name"].eq(candidate), "is_published"] = publish

    forecast_columns = [
        "model_run_id", "model_name", "carrier_key", "metric_key", "period_id",
        "forecast_value", "lower_80", "upper_80", "lower_95", "upper_95",
        "is_backtest", "actual_value", "error", "abs_pct_error",
        "trained_through_period", "features_used", "trained_at",
    ]
    forecast_rows: list[dict[str, object]] = []
    model_directory = MODELS_DIR / run_id
    model_directory.mkdir(parents=True, exist_ok=True)
    trained_at = reproducible_timestamp()
    final_model: object | None = None
    if publish:
        selected_backtest = test_runs[candidate]
        for row in selected_backtest.itertuples(index=False):
            error = row.actual - row.forecast
            forecast_rows.append(
                {
                    "model_run_id": run_id,
                    "model_name": candidate,
                    "carrier_key": "AEROMEXICO",
                    "metric_key": "passengers_afac",
                    "period_id": row.date.strftime("%YM%m"),
                    "forecast_value": row.forecast,
                    "lower_80": max(0.0, row.forecast - 1.281552 * row.standard_error),
                    "upper_80": row.forecast + 1.281552 * row.standard_error,
                    "lower_95": max(0.0, row.forecast - 1.959964 * row.standard_error),
                    "upper_95": row.forecast + 1.959964 * row.standard_error,
                    "is_backtest": True,
                    "actual_value": row.actual,
                    "error": error,
                    "abs_pct_error": abs(error / row.actual) if row.actual else np.nan,
                    "trained_through_period": row.trained_through.strftime("%YM%m"),
                    "features_used": "target lags, trend, month seasonality; COVID retained in history",
                    "trained_at": trained_at,
                }
            )
        future_values, future_se, final_model = _fit_predict(series, candidate, FORECAST_HORIZON)
        future_dates = pd.date_range(series.index[-1] + pd.offsets.MonthBegin(1), periods=FORECAST_HORIZON, freq="MS")
        for date, value, se in zip(future_dates, future_values, future_se, strict=True):
            forecast_rows.append(
                {
                    "model_run_id": run_id,
                    "model_name": candidate,
                    "carrier_key": "AEROMEXICO",
                    "metric_key": "passengers_afac",
                    "period_id": date.strftime("%YM%m"),
                    "forecast_value": max(0.0, float(value)),
                    "lower_80": max(0.0, float(value - 1.281552 * se)),
                    "upper_80": float(value + 1.281552 * se),
                    "lower_95": max(0.0, float(value - 1.959964 * se)),
                    "upper_95": float(value + 1.959964 * se),
                    "is_backtest": False,
                    "actual_value": np.nan,
                    "error": np.nan,
                    "abs_pct_error": np.nan,
                    "trained_through_period": series.index[-1].strftime("%YM%m"),
                    "features_used": "target lags, trend, month seasonality; COVID retained in history",
                    "trained_at": trained_at,
                }
            )
    forecasts = pd.DataFrame(forecast_rows, columns=forecast_columns)

    metadata = {
        "model_run_id": run_id,
        "code_version": code_version(),
        "config": config,
        "published": publish,
        "publication_rule": "candidate selected on validation and published only if test sMAPE beats seasonal naive",
        "selected_model": candidate,
        "test_window": [series.index[test_start].strftime("%YM%m"), series.index[-1].strftime("%YM%m")],
        "performance_split": "test",
        "baseline_test_smape": baseline_test["smape"],
        "selected_test_smape": float(performance.loc[performance.model_name.eq(candidate), "smape"].iloc[0]),
        "interval_method": "model standard error with normal 80% and 95% bands",
        "trained_at": trained_at,
    }
    write_json(model_directory / "metadata.json", metadata)
    if final_model is not None:
        (model_directory / "model.pkl").write_bytes(pickle.dumps(final_model))
    (model_directory / "performance.json").write_text(
        json.dumps(performance.to_dict("records"), indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return forecasts, performance, metadata


if __name__ == "__main__":
    forecast, performance, metadata = run_forecast()
    print(metadata)
    print(performance.to_string(index=False))
    print(f"forecast rows={len(forecast)}")
