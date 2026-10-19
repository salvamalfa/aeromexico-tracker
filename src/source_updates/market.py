"""Bounded public Yahoo chart capture recipes and direct raw-JSON-to-Silver parsing."""

from __future__ import annotations

import json
import unicodedata
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import numpy as np
import pandas as pd

from src.config import PATHS
from src.ingest.market.prices import IPO_DATE, START_DATE, TICKERS, _identity_evidence
from src.ingest.stage4_common import bronze_period, latest_bronze, lineage, write_parquet_atomic
from src.source_updates.calendar import local_time
from src.source_updates.checks import period_end, verify_bronze


def chart_frame(content: bytes, ticker: str, end_date: str) -> pd.DataFrame:
    if ticker not in TICKERS:
        raise ValueError("Unknown tracked ticker")
    chart = json.loads(content)["chart"]
    if chart.get("error") or len(chart.get("result") or []) != 1:
        raise ValueError("Yahoo returned an error or ambiguous chart result")
    result = chart["result"][0]
    meta = result["meta"]
    if (
        meta.get("symbol") != ticker
        or meta.get("currency") != "USD"
        or meta.get("instrumentType") != "EQUITY"
    ):
        raise ValueError("Chart ticker, currency or instrument identity mismatch")
    if ticker == "AERO":
        name = unicodedata.normalize("NFKD", str(meta.get("longName") or meta.get("shortName") or ""))
        if "aeromexico" not in "".join(c for c in name if c.isalpha()).casefold():
            raise ValueError("Yahoo AERO company name does not identify Aeromexico")
    times = result.get("timestamp") or []
    if not times or len(times) > 100_000:
        raise ValueError("Missing or unexpectedly large daily history")
    indicators = result["indicators"]
    if len(indicators.get("quote", [])) != 1 or len(indicators.get("adjclose", [])) != 1:
        raise ValueError("Exactly one quote and adjusted-close series are required")
    quote = indicators["quote"][0]
    values = {column: quote[column] for column in ("open", "high", "low", "close", "volume")}
    values["adj_close"] = indicators["adjclose"][0]["adjclose"]
    if any(len(value) != len(times) for value in values.values()):
        raise ValueError("Quote arrays do not match source timestamps")
    frame = pd.DataFrame(values).apply(pd.to_numeric, errors="raise")
    if not np.isfinite(frame.to_numpy(dtype=float)).all():
        raise ValueError("Missing/nonfinite market observations; never replace with zero")
    if not frame[["open", "high", "low", "close", "adj_close"]].gt(0).all().all():
        raise ValueError("Market prices must be positive")
    if frame.volume.lt(0).any() or frame.volume.mod(1).ne(0).any():
        raise ValueError("Invalid reported volume")
    if (
        frame.high.lt(frame[["open", "close", "low"]].max(axis=1)).any()
        or frame.low.gt(frame[["open", "close", "high"]].min(axis=1)).any()
    ):
        raise ValueError("Incoherent reported OHLC prices")
    frame["volume"] = frame.volume.astype("int64")
    frame["date"] = (
        pd.to_datetime(times, unit="s", utc=True)
        .tz_convert(meta["exchangeTimezoneName"])
        .tz_localize(None)
        .normalize()
    )
    if (
        frame.date.duplicated().any()
        or frame.date.min() < pd.Timestamp(START_DATE)
        or frame.date.max() > pd.Timestamp(end_date)
    ):
        raise ValueError("Duplicate days or observations outside requested window")
    frame = frame.sort_values("date").reset_index(drop=True)
    if ticker == "AERO" and frame.date.min() != IPO_DATE:
        raise ValueError(
            "AERO first observation must equal the preserved IPO date; no historical ticker splice"
        )
    return frame


def build_from_charts() -> dict:
    identity = _identity_evidence()
    artifacts = verify_bronze(PATHS.root)
    reference = artifacts.get(str(identity["source_file"]))
    if (
        reference is None
        or reference["sha256"] != identity["source_hash"]
        or reference["source_system"] != "sec"
    ):
        raise ValueError("AERO identity evidence must resolve to verified SEC Bronze")
    frames, receipts = [], []
    for ticker, carrier in TICKERS.items():
        path = latest_bronze("yahoo_finance", ticker + "_chart")
        if path is None:
            raise FileNotFoundError(f"Missing preserved raw chart for {ticker}")
        original = artifacts.get(path.relative_to(PATHS.bronze).as_posix())
        if original is None or original["source_system"] != "yahoo_finance":
            raise ValueError(f"Raw chart for {ticker} is absent from verified Bronze")
        end = bronze_period(path).rsplit("_", 1)[-1]
        frame = chart_frame(path.read_bytes(), ticker, end)
        frame = frame.assign(
            ticker=ticker,
            carrier_key=carrier,
            currency="USD",
            source="yahoo_finance",
            source_system="yahoo_finance",
            **lineage(path),
        )
        frame["parser_version"] = "yahoo_chart_offline_v1"
        frames.append(frame)
        receipts.append(
            {
                "ticker": ticker,
                "carrier_key": carrier,
                "first_price_date": str(frame.date.min().date()),
                "last_price_date": str(frame.date.max().date()),
                "observations": len(frame),
                "identity_verified": True,
                "identity_source_file": identity["source_file"],
                "identity_source_hash": identity["source_hash"],
                "source_file": lineage(path)["source_file"],
                "source_hash": lineage(path)["source_hash"],
                "raw_json_preserved": True,
            }
        )
    output = pd.concat(frames, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)
    columns = [
        "date",
        "ticker",
        "carrier_key",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
        "currency",
        "source",
        "source_system",
        "source_file",
        "source_hash",
        "ingested_at",
        "parser_version",
    ]
    write_parquet_atomic(output[columns], PATHS.silver / "market_prices.parquet")
    PATHS.quality.mkdir(parents=True, exist_ok=True)
    (PATHS.quality / "market_identity_verification.json").write_text(json.dumps(receipts, indent=2) + "\n")
    return {
        "rows": len(output),
        "tickers": receipts,
        "network_requests": 0,
        "coverage": "observed_daily_quotes_not_calendar_completeness",
    }


def round_recipe(period: str, as_of: str) -> dict:
    end = period_end(period)
    if end >= local_time(as_of).date():
        raise ValueError("Market recipe requires a closed observation period")
    params = {
        "period1": int(datetime(2015, 1, 1, tzinfo=UTC).timestamp()),
        "period2": int(datetime.combine(end + timedelta(days=1), datetime.min.time(), UTC).timestamp()),
        "interval": "1d",
        "events": "div,splits",
    }
    return {
        "version": 1,
        "product": "equities",
        "selection": {
            "version": 1,
            "items": [
                {
                    "id": "yahoo-" + ticker,
                    "product": "equities",
                    "source_system": "yahoo_finance",
                    "entity": ticker + "_chart",
                    "period": f"{START_DATE}_{end}",
                    "purpose": "data",
                    "url": "https://query1.finance.yahoo.com/v8/finance/chart/"
                    + ticker
                    + "?"
                    + urlencode(params),
                    "extension": "json",
                    "mode": "get",
                }
                for ticker in TICKERS
            ],
        },
        "steps": ["parse.market_chart"],
        "checks": {
            "as_of": as_of,
            "checks": [
                {
                    "product": "equities",
                    "layer": "silver",
                    "table": "market_prices",
                    "expected_period": month,
                    "period_column": "date",
                    "filters": {"ticker": ticker, "carrier_key": carrier},
                    "value_columns": ["close", "adj_close", "volume"],
                }
                for ticker, carrier in TICKERS.items()
                for month in (
                    [period]
                    if "M" in period
                    else [
                        f"{period[:4]}M{n:02d}"
                        for n in range(int(period[-1]) * 3 - 2, int(period[-1]) * 3 + 1)
                    ]
                )
            ],
        },
        "prerequisite": "Verified candidate-local SEC identity report and its raw Bronze artifact",
        "coverage": "selected_quotes_only_not_complete_family",
        "activation": "none",
        "publication": "not_authorized",
    }
