"""Immutable market-price snapshots with an explicit AERO identity gate."""

from __future__ import annotations

import json

import pandas as pd
import yfinance as yf

from src.common.storage import save_bronze
from src.config import PATHS
from src.ingest.stage4_common import latest_bronze, lineage, write_parquet_atomic


START_DATE = "2015-01-01"
IPO_DATE = pd.Timestamp("2025-11-06")
TICKERS = {
    "AERO": "AEROMEXICO",
    "VLRS": "VOLARIS",
    "RYAAY": "RYANAIR",
    "DAL": "DELTA",
    "ICAGY": "IAG",
}
AERO_IDENTITY_URL = "https://ir.aeromexico.com/ir-resources/investor-faqs"


def _normalize_history(frame: pd.DataFrame) -> pd.DataFrame:
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    frame = frame.reset_index()
    date_column = "Date" if "Date" in frame else frame.columns[0]
    frame[date_column] = pd.to_datetime(frame[date_column], utc=True).dt.tz_convert(None).dt.normalize()
    return frame.rename(
        columns={
            date_column: "date", "Open": "open", "High": "high", "Low": "low",
            "Close": "close", "Adj Close": "adj_close", "Volume": "volume",
        }
    )


def _identity_evidence() -> dict[str, object]:
    reports = pd.read_parquet(PATHS.silver / "sec_report_text.parquet")
    identity_reports = reports.loc[
        reports["text"].str.contains("began trading", case=False, na=False)
        & reports["text"].str.contains("AERO", case=True, na=False)
    ]
    if identity_reports.empty:
        raise RuntimeError("No preserved SEC report confirms AERO ticker identity")
    identity_report = identity_reports.iloc[-1]
    return {
        "source_file": identity_report["source_file"],
        "source_hash": identity_report["source_hash"],
    }


def build_from_bronze(end_date: str | None = None) -> dict[str, object]:
    """Rebuild market silver data from the latest immutable ticker snapshots."""

    identity_lineage = _identity_evidence()
    frames: list[pd.DataFrame] = []
    identities: list[dict[str, object]] = []
    for ticker, carrier_key in TICKERS.items():
        bronze = latest_bronze("yahoo_finance", ticker)
        if bronze is None:
            raise FileNotFoundError(f"Missing market bronze artifact for {ticker}")
        frame = pd.read_csv(bronze)
        frame["date"] = pd.to_datetime(frame["date"], utc=True).dt.tz_convert(None).dt.normalize()
        if end_date is not None:
            frame = frame.loc[frame["date"] <= pd.Timestamp(end_date)]
        if frame.empty:
            raise RuntimeError(f"No market history remains for {ticker}")
        if ticker == "AERO" and frame["date"].min() != IPO_DATE:
            raise ValueError(
                f"AERO first price date {frame['date'].min().date()} does not match IPO date"
            )
        currency = "USD"
        exchange = "NYSE" if ticker in {"AERO", "VLRS", "DAL"} else "NASDAQ/OTC"
        frame["ticker"] = ticker
        frame["carrier_key"] = carrier_key
        frame["currency"] = currency
        frame["source"] = "yahoo_finance"
        frame["source_system"] = "yahoo_finance"
        for key, value in lineage(bronze).items():
            frame[key] = value
        if "adj_close" not in frame:
            frame["adj_close"] = frame["close"]
        frames.append(frame)
        identities.append(
            {
                "ticker": ticker,
                "carrier_key": carrier_key,
                "exchange": exchange,
                "currency": currency,
                "first_price_date": frame["date"].min().date().isoformat(),
                "last_price_date": frame["date"].max().date().isoformat(),
                "identity_verified": ticker != "AERO" or frame["date"].min() == IPO_DATE,
                "identity_source_url": AERO_IDENTITY_URL if ticker == "AERO" else None,
                "identity_source_file": identity_lineage["source_file"] if ticker == "AERO" else None,
                "identity_source_hash": identity_lineage["source_hash"] if ticker == "AERO" else None,
            }
        )
    output = pd.concat(frames, ignore_index=True)
    output["volume"] = output["volume"].astype("int64")
    columns = [
        "date", "ticker", "carrier_key", "open", "high", "low", "close",
        "adj_close", "volume", "currency", "source", "source_system", "source_file", "source_hash",
        "ingested_at", "parser_version",
    ]
    output = output[columns].sort_values(["ticker", "date"]).reset_index(drop=True)
    write_parquet_atomic(output, PATHS.silver / "market_prices.parquet")
    identity_path = PATHS.quality / "market_identity_verification.json"
    identity_path.parent.mkdir(parents=True, exist_ok=True)
    identity_path.write_text(json.dumps(identities, indent=2) + "\n", encoding="utf-8")
    return {"rows": len(output), "tickers": identities}


def run(end_date: str | None = None) -> dict[str, object]:
    end = pd.Timestamp(end_date).date().isoformat() if end_date else None
    _identity_evidence()
    for ticker in TICKERS:
        history = yf.Ticker(ticker).history(
            start=START_DATE,
            end=(pd.Timestamp(end) + pd.Timedelta(days=1)).date().isoformat() if end else None,
            auto_adjust=False,
            repair=True,
        )
        if history.empty:
            raise RuntimeError(f"No market history returned for {ticker}")
        frame = _normalize_history(history)
        raw = frame.to_csv(index=False).encode("utf-8")
        save_bronze(
            raw,
            "yahoo_finance",
            ticker,
            f"{frame['date'].min().date()}_{frame['date'].max().date()}",
            "csv",
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
            "httpx",
            "Downloaded through yfinance; raw normalized response snapshot preserved as CSV.",
            content_type="text/csv",
            relative_dir="market",
        )
    return build_from_bronze(end)


def main() -> int:
    print(json.dumps(run(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
