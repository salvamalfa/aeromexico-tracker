"""Strict retained-series readers; no source requests or caller-selected subsets."""

from __future__ import annotations

import csv
import io
import json
import re
import unicodedata
from datetime import datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlsplit

import pandas as pd
from bs4 import BeautifulSoup

from src.ingest.macro.banxico import BANXICO_SERIES, SIE_EXPORT_URL
from src.ingest.macro.fuel import EIA_SERIES_ID, EIA_XLS_URL
from src.ingest.market.prices import IPO_DATE, TICKERS
from src.source_updates.calendar import local_time
from src.source_updates.checks import period_end
from src.source_updates.market import chart_frame

PRODUCTS = frozenset({"banxico", "fuel", "equities"})
UNITS = {
    "usd_mxn_fix": "mxn_per_usd",
    "inpc": "index",
    "policy_rate": "percent",
    "jet_fuel_usd_per_gallon": "usd_per_gallon",
}
EXCHANGES = {"AERO": "NYQ", "VLRS": "NYQ", "RYAAY": "NMS", "DAL": "NYQ", "ICAGY": "PNK"}


def definitions() -> dict:
    return {
        "banxico": {
            "roles": {s: ("banxico_sie",) for s in BANXICO_SERIES},
            "primary": "SF43718",
            "certifier": "series",
        },
        "fuel": {"roles": {"workbook": ("eia",)}, "primary": "workbook", "certifier": "series"},
        "equities": {
            "roles": {**{t: ("yahoo_finance",) for t in TICKERS}, "identity": ("sec",)},
            "primary": "AERO",
            "certifier": "series",
        },
    }


def normalized(value) -> str:
    return " ".join(
        "".join(c for c in unicodedata.normalize("NFKD", str(value)) if not unicodedata.combining(c)).split()
    ).casefold()


def window(period: str):
    if not isinstance(period, str) or not re.fullmatch(r"20\d{2}(?:M(?:0[1-9]|1[0-2])|Q[1-4])", period):
        raise ValueError("Closed source window must be YYYYMmm or YYYYQn")
    end = period_end(period)
    first_month = end.month if "M" in period else end.month - 2
    start = end.replace(month=first_month, day=1)
    return start, end, [f"{end.year}M{m:02d}" for m in range(first_month, end.month + 1)]


def number(token) -> float:
    value = str(token).strip()
    if not re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        raise ValueError("Invalid or missing numeric token preserved in original; never discard or fill zero")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid native decimal") from exc
    if not result.is_finite() or not float("-inf") < float(result) < float("inf"):
        raise ValueError("Nonfinite native value")
    return float(result)


def banxico_file(content: bytes, series: str) -> pd.DataFrame:
    if series not in BANXICO_SERIES:
        raise ValueError("Unknown canonical Banxico series")
    reader = csv.reader(io.StringIO(content.decode("latin1")))
    rows = [(reader.line_num, row) for row in reader]
    headers = [i for i, (_, row) in enumerate(rows) if row and row[0] == "Fecha"]
    if len(headers) != 1 or rows[headers[0]][1] != ["Fecha", series]:
        raise ValueError("Banxico requires exactly its own Fecha/series header")
    index = headers[0]
    metadata = {}
    for _, row in rows[:index]:
        if len(row) == 2:
            if row[0] in metadata:
                raise ValueError("Duplicate native metadata")
            metadata[row[0]] = row[1]
    expected = {
        "SF43718": {"Periodicidad": "Diaria", "Unidad": "Pesos por Dólar", "Cifra": "Tipo de Cambio"},
        "SP1": {"Periodicidad": "Mensual", "Unidad": "Sin Unidad", "Cifra": "Indices", "Base": "2Q Jul 2018"},
        "SF61745": {"Periodicidad": "Diaria", "Unidad": "Sin Unidad", "Cifra": "Porcentajes"},
    }[series]
    if any(normalized(metadata.get(k, "")) != normalized(v) for k, v in expected.items()):
        raise ValueError("Banxico frequency, units, scale or index base changed")
    title = normalized(metadata.get("Título", ""))
    if (
        (series == "SF43718" and "(fix)" not in title)
        or (series == "SP1" and "indicegeneral" not in title.replace(" ", ""))
        or (series == "SF61745" and title != "tasa objetivo")
    ):
        raise ValueError("Banxico source title does not identify the canonical indicator")
    output = []
    for line, row in rows[index + 1 :]:
        if not row:
            continue
        if len(row) != 2 or not re.fullmatch(r"\d{2}/\d{2}/\d{4}", row[0]):
            raise ValueError("Unverified Banxico date/row layout")
        day = datetime.strptime(row[0], "%d/%m/%Y")
        value = number(row[1])
        if series in {"SF43718", "SP1"} and value <= 0:
            raise ValueError("FIX/INPC must be positive in native units")
        if series == "SP1" and day.day != 1:
            raise ValueError("Monthly INPC observation is not its native month anchor")
        output.append(
            {"date": day, "value": value, "source_value": row[1], "source_locator": f"csv/line/{line}"}
        )
    frame = pd.DataFrame(output)
    if frame.empty or frame.date.duplicated().any():
        raise ValueError("Empty or duplicate Banxico dates, including identical duplicates")
    return frame.sort_values("date").reset_index(drop=True)


def fuel_file(content: bytes) -> pd.DataFrame:
    raw = pd.read_excel(io.BytesIO(content), sheet_name="Data 1", header=None)
    label = "U.S. Gulf Coast Kerosene-Type Jet Fuel Spot Price FOB (Dollars per Gallon)"
    if (
        raw.shape[1] != 2
        or raw.iloc[1].tolist() != ["Sourcekey", EIA_SERIES_ID]
        or raw.iloc[2].tolist() != ["Date", label]
    ):
        raise ValueError("EIA workbook does not identify the exact jet-fuel series and dollars/gallon unit")
    output = []
    for i in range(3, len(raw)):
        row = raw.iloc[i]
        if pd.isna(row.iloc[0]) or pd.isna(row.iloc[1]):
            raise ValueError("EIA missing observation preserved in original; no silent row drop")
        stamp = pd.Timestamp(row.iloc[0])
        if stamp.tzinfo is not None or stamp != stamp.normalize():
            raise ValueError("EIA date must be a native daily date")
        value = number(row.iloc[1])
        if value < 0:
            raise ValueError("Negative EIA jet-fuel spot quote")
        output.append(
            {
                "date": stamp,
                "value": value,
                "source_value": str(row.iloc[1]),
                "source_locator": f"Data 1!A{i + 1}:B{i + 1}",
            }
        )
    frame = pd.DataFrame(output)
    if frame.empty or frame.date.duplicated().any():
        raise ValueError("Empty or duplicate EIA dates")
    return frame.sort_values("date").reset_index(drop=True)


def identity(content: bytes, source: dict) -> None:
    url = urlsplit(source["source_url"])
    if (
        source["source_system"] != "sec"
        or url.hostname != "www.sec.gov"
        or not re.fullmatch(r"/Archives/edgar/data/1561861/\d{18}/[^/]+\.htm[l]?", url.path)
    ):
        raise ValueError("AERO identity must be an actual Aeromexico SEC original")
    text = normalized(BeautifulSoup(content, "html.parser").get_text(" ", strip=True))
    if not re.search(
        r"november 6, 2025, aeromexico began trading.{0,150}new york stock exchange", text
    ) or not re.search(
        r"(?:(?:ticker|symbol).{0,60}\baero(?![\w]|[.-]\w)|nyse\s*&\s*bmv:\s*aero(?![\w]|[.-]\w))", text
    ):
        raise ValueError(
            "Physical SEC document does not establish AERO identity/IPO; Silver text is insufficient"
        )


def provenance(record: dict) -> dict:
    return {
        "source_system": record["source_system"],
        "source_file": record["source_file"],
        "source_hash": record["sha256"],
        "ingested_at": pd.Timestamp(record["downloaded_at"]).as_unit("ns"),
        "parser_version": "retained_series_v1",
    }


def binding(record: dict, source: str, entity: str, start, end) -> None:
    parts = record["logical_key"].split("|")
    if len(parts) != 4 or parts[:2] != [source, entity]:
        raise ValueError("Native source/series/ticker logical identity mismatch")
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})", parts[2])
    if not match or pd.Timestamp(match[1]).date() > start or pd.Timestamp(match[2]).date() < end:
        raise ValueError("Retained request window does not cover the selected source window")


def coverage(frame: pd.DataFrame, months: list[str], key: str) -> dict:
    observed = frame.date.dt.strftime("%YM%m")
    counts = {month: int(observed.eq(month).sum()) for month in months}
    if any(count == 0 for count in counts.values()):
        raise ValueError(f"Missing source month for {key}: {counts}")
    return {
        "months": counts,
        "first_observation": frame.date.min().date().isoformat(),
        "last_observation": frame.date.max().date().isoformat(),
        "observations": len(frame),
        "calendar_completeness_certified": False,
    }


def read(product: str, inputs: dict, period: str) -> tuple[dict, dict]:
    if product not in PRODUCTS or set(inputs) != set(definitions()[product]["roles"]):
        raise ValueError("Select all canonical product input roles; subsets are forbidden")
    start, end, months = window(period)
    frames, details = [], {}
    if product == "equities":
        identity(*inputs["identity"])
        for ticker, carrier in TICKERS.items():
            body, record = inputs[ticker]
            binding(record, "yahoo_finance", ticker + "_chart", start, end)
            url = urlsplit(record["source_url"])
            query = parse_qs(url.query)
            if (
                url.hostname != "query1.finance.yahoo.com"
                or url.path != "/v8/finance/chart/" + ticker
                or query.get("interval") != ["1d"]
                or query.get("events") != ["div,splits"]
            ):
                raise ValueError("Market original is not the canonical daily adjusted chart request")
            request_start = pd.Timestamp(int(query["period1"][0]), unit="s", tz="UTC")
            request_end = pd.Timestamp(int(query["period2"][0]), unit="s", tz="UTC")
            if request_start != pd.Timestamp("2015-01-01", tz="UTC") or request_end.date() <= end:
                raise ValueError("Market request timestamps do not cover the full source window")
            meta = json.loads(body)["chart"]["result"][0]["meta"]
            if (
                meta.get("exchangeTimezoneName") != "America/New_York"
                or meta.get("exchangeName") != EXCHANGES[ticker]
                or meta.get("dataGranularity") != "1d"
            ):
                raise ValueError("Market exchange/timezone/daily granularity changed")
            frame = chart_frame(
                body, ticker, str(pd.Timestamp(record["logical_key"].split("|")[2].rsplit("_", 1)[1]).date())
            )
            if (
                ticker == "AERO"
                and pd.Timestamp(meta["firstTradeDate"], unit="s", tz="UTC")
                .tz_convert("America/New_York")
                .date()
                != IPO_DATE.date()
            ):
                raise ValueError("AERO quote metadata does not preserve the SEC IPO boundary")
            if frame.date.max().date() > local_time(record["downloaded_at"]).date():
                raise ValueError("Original contains future observations relative to its capture")
            expected_first = IPO_DATE if ticker == "AERO" else pd.Timestamp("2015-01-02")
            if frame.date.min() != expected_first:
                raise ValueError("Retained market history lost its verified initial observation")
            history_months = set(pd.period_range(expected_first, pd.Timestamp(end), freq="M"))
            if not history_months <= set(frame.date.dt.to_period("M")):
                raise ValueError(
                    "Market history has missing months; YTD and rolling metrics cannot be certified"
                )
            frame = frame.loc[frame.date.le(pd.Timestamp(end))].assign(
                ticker=ticker, carrier_key=carrier, currency="USD", **provenance(record)
            )
            selected = frame.loc[frame.date.ge(pd.Timestamp(start))]
            details[ticker] = coverage(selected, months, ticker)
            frames.append(frame)
        return {
            "market_prices": pd.concat(frames, ignore_index=True)
            .sort_values(["ticker", "date"])
            .reset_index(drop=True)
        }, {"coverage": details, "identity_source_file": inputs["identity"][1]["source_file"]}
    for role, (body, record) in inputs.items():
        if product == "banxico":
            binding(record, "banxico_sie", role, start, end)
            if record["source_url"] != SIE_EXPORT_URL:
                raise ValueError("Unexpected Banxico export URL")
            history = banxico_file(body, role)
            indicator, series = BANXICO_SERIES[role], role
        else:
            binding(record, "eia", EIA_SERIES_ID, start, end)
            if record["source_url"] != EIA_XLS_URL:
                raise ValueError("Unexpected official EIA series URL")
            history = fuel_file(body)
            indicator, series = "jet_fuel_usd_per_gallon", EIA_SERIES_ID
        selected = history.loc[history.date.between(pd.Timestamp(start), pd.Timestamp(end))].copy()
        if not selected.empty and selected.date.max().date() > local_time(record["downloaded_at"]).date():
            raise ValueError("Selected original contains future observations relative to its capture")
        details[series] = coverage(selected, months, series)
        selected = selected.assign(
            series_id=series, indicator_key=indicator, unit=UNITS[indicator], **provenance(record)
        )
        frames.append(selected)
    frame = pd.concat(frames, ignore_index=True).sort_values(["series_id", "date"]).reset_index(drop=True)
    if product == "fuel":
        return {"fuel_prices": frame.rename(columns={"value": "price_usd_per_gallon"})}, {"coverage": details}
    fx = (
        frame.loc[frame.series_id.eq("SF43718")]
        .rename(columns={"value": "rate_close"})
        .assign(currency_pair="USD/MXN")
    )
    return {"macro_indicators": frame, "fx_rates": fx.reset_index(drop=True)}, {"coverage": details}
