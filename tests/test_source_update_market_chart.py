import json

import pandas as pd
import pytest

from src.source_updates.market import chart_frame, round_recipe


def payload(ticker="AERO"):
    dates = ["2025-11-06", "2026-09-01", "2026-09-30"]
    timestamps = [int(pd.Timestamp(day + "T15:30:00Z").timestamp()) for day in dates]
    return {
        "chart": {
            "error": None,
            "result": [
                {
                    "meta": {
                        "symbol": ticker,
                        "currency": "USD",
                        "instrumentType": "EQUITY",
                        "exchangeTimezoneName": "America/New_York",
                        "shortName": "Grupo Aeromexico, S.A.B. de C.V.",
                    },
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": [10.0, 11.0, 12.0],
                                "high": [11.0, 12.0, 13.0],
                                "low": [9.0, 10.0, 11.0],
                                "close": [10.5, 11.5, 12.5],
                                "volume": [0, 100, 200],
                            }
                        ],
                        "adjclose": [{"adjclose": [10.0, 11.0, 12.0]}],
                    },
                }
            ],
        }
    }


def test_raw_chart_preserves_observations_adjustments_and_reported_zero_volume():
    frame = chart_frame(json.dumps(payload()).encode(), "AERO", "2026-09-30")
    assert frame.date.min() == pd.Timestamp("2025-11-06")
    assert frame.date.max() == pd.Timestamp("2026-09-30")
    assert frame.close.tolist() == [10.5, 11.5, 12.5]
    assert frame.adj_close.tolist() == [10.0, 11.0, 12.0]
    assert frame.volume.tolist() == [0, 100, 200]


@pytest.mark.parametrize(
    "case",
    [
        "symbol",
        "currency",
        "instrument",
        "issuer",
        "missing_close",
        "missing_volume",
        "fractional_volume",
        "negative_volume",
        "missing_adjustments",
        "duplicate_day",
        "outside_window",
        "pre_ipo",
        "error",
    ],
)
def test_raw_chart_blocks_ambiguous_identity_missing_data_and_historical_splices(case):
    data = payload()
    result = data["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    if case == "symbol":
        result["meta"]["symbol"] = "VLRS"
    elif case == "currency":
        result["meta"]["currency"] = "MXN"
    elif case == "instrument":
        result["meta"]["instrumentType"] = "ETF"
    elif case == "issuer":
        result["meta"]["shortName"] = "Aero unrelated company"
    elif case == "missing_close":
        quote["close"][1] = None
    elif case == "missing_volume":
        quote["volume"][1] = None
    elif case == "fractional_volume":
        quote["volume"][1] = 1.5
    elif case == "negative_volume":
        quote["volume"][1] = -1
    elif case == "missing_adjustments":
        result["indicators"].pop("adjclose")
    elif case == "duplicate_day":
        result["timestamp"][1] = result["timestamp"][0]
    elif case == "outside_window":
        result["timestamp"][-1] = int(pd.Timestamp("2026-10-01T15:30:00Z").timestamp())
    elif case == "pre_ipo":
        result["timestamp"][0] = int(pd.Timestamp("2015-01-02T15:30:00Z").timestamp())
    else:
        data["chart"]["error"] = {"code": "Unauthorized"}
    with pytest.raises(ValueError):
        chart_frame(json.dumps(data).encode(), "AERO", "2026-09-30")


def test_market_recipe_declares_five_exact_tickers_and_all_quarter_months():
    recipe = round_recipe("2026Q3", "2026-10-19T12:00:00-06:00")
    assert len(recipe["selection"]["items"]) == 5
    assert len(recipe["checks"]["checks"]) == 15
    assert {row["expected_period"] for row in recipe["checks"]["checks"]} == {"2026M07", "2026M08", "2026M09"}
    assert recipe["steps"] == ["parse.market_chart"]
    assert all(row["entity"].endswith("_chart") for row in recipe["selection"]["items"])
