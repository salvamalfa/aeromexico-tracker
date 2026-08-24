from __future__ import annotations

import numpy as np
import pandas as pd

from src.analytics.clustering import _unique_names
from src.analytics.forecast import _metrics
from src.analytics.nlp_reports import _metrics as text_metrics, _syllables
from src.transform.stage6_contracts import table_definitions


def test_forecast_metrics_use_seasonal_scale() -> None:
    training = pd.Series(np.arange(36, dtype=float) + 100)
    metrics = _metrics(np.array([140.0, 142.0]), np.array([139.0, 140.0]), training)
    assert metrics["mae"] == 1.5
    assert metrics["rmse"] > metrics["mae"]
    assert metrics["mase"] > 0


def test_cluster_business_names_are_unique() -> None:
    names = _unique_names({0: "Alta frecuencia", 1: "Alta frecuencia", 2: "Ocio estacional"})
    assert len(set(names.values())) == 3
    assert names[1] == "Alta frecuencia 2"


def test_text_metrics_are_bounded() -> None:
    lexicon = {
        "positive": {"improve"}, "negative": {"loss"}, "uncertainty": {"may"},
        "litigious": {"claim"}, "constraining": {"limit"},
    }
    metrics = text_metrics("Results may improve. A loss was reported, and claims limit options.", lexicon)
    assert metrics["word_count"] > 0
    assert 0 <= metrics["lm_positive_ratio"] <= 1
    assert 0 <= metrics["lm_negative_ratio"] <= 1


def test_syllable_heuristic_never_returns_zero() -> None:
    assert _syllables("rhythm") >= 1
    assert _syllables("performance") >= 1


def test_stage_contract_filter_keeps_stage6_isolated() -> None:
    stage6 = table_definitions(max_stage=6)
    stage7 = table_definitions(max_stage=7)
    assert "fact_forecasts" not in stage6
    assert "fact_forecasts" in stage7
    assert set(stage6) < set(stage7)
