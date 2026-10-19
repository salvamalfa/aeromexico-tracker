"""Strict H.10 readers; preserve decimal quotes and source ND before aggregation."""

from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
import io
import re

from bs4 import BeautifulSoup

from src.ingest.macro.banxico import FED_H10_SERIES_ID
from src.source_updates.h10_capture import month_bounds


def quote(value: str) -> Decimal | None:
    if value == "ND":
        return None
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        raise ValueError("H.10 value is neither an explicit ND nor an unscaled decimal quote")
    result = Decimal(value)
    if not result.is_finite() or result <= 0:
        raise ValueError("H.10 quotes must be finite and positive")
    return result


def csv_rates(content: bytes) -> dict[date, str]:
    rows = list(csv.reader(io.StringIO(content.decode("utf-8-sig"))))
    labels = [row[0].strip() if row else "" for row in rows]
    if labels.count("Time Period") != 1:
        raise ValueError("H.10 requires exactly one Time Period header")
    header = labels.index("Time Period")
    columns = rows[header]
    if columns.count("RXI_N.B.MX") != 1:
        raise ValueError("H.10 requires exactly one daily Mexican-peso series")
    column = columns.index("RXI_N.B.MX")
    expected = {
        "Series Description": "Mexican Peso",
        "Unit:": "Currency",
        "Multiplier:": "1",
        "Currency:": "MXN",
        "Unique Identifier:": FED_H10_SERIES_ID,
    }
    if set(labels[:header]) != set(expected) or header != len(expected):
        raise ValueError("Unverified H.10 metadata layout")
    for name, value in expected.items():
        row = rows[labels.index(name)]
        if len(row) != len(columns) or row[column].strip() != value:
            raise ValueError(f"H.10 metadata mismatch: {name}")
    result = {}
    for row in rows[header + 1 :]:
        if len(row) != len(columns) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row[0]):
            raise ValueError("Unverified H.10 date or row layout")
        day = date.fromisoformat(row[0])
        if day in result:
            raise ValueError("Duplicate H.10 CSV date, even if the quotes agree")
        quote(row[column])
        result[day] = row[column]
    return result


def html_rates(content: bytes) -> tuple[dict[date, str], date]:
    soup = BeautifulSoup(content, "html.parser")
    text = soup.get_text(" ", strip=True)
    if "Historical Rates for the Mexican Peso" not in text or not re.search(
        r"Rates in Mexican pesos per U\.S\. dollar", text
    ):
        raise ValueError("Official HTML does not establish Mexican pesos per one U.S. dollar")
    release = re.search(r"Release Date:\s*(?:[A-Za-z]+,\s*)?([A-Za-z]+ \d{1,2}, \d{4})", text)
    if not release:
        raise ValueError("Official H.10 history release date missing")
    vintage = datetime.strptime(release[1], "%B %d, %Y").date()
    tables = soup.find_all("table")
    if len(tables) != 1:
        raise ValueError("Ambiguous H.10 historical table")
    result = {}
    # The official preserved page has bare <th> elements inside <thead>,
    # whereas other verified exports wrap those same headings in a <tr>.
    header = tables[0].find("thead") or tables[0].find("tr")
    if header is None or [c.get_text(" ", strip=True) for c in header.find_all(["th", "td"])] != [
        "Date",
        "Rate",
    ]:
        raise ValueError("H.10 historical Date/Rate header missing")
    for number, row in enumerate(tables[0].find_all("tr")):
        cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
        if number == 0 and cells == ["Date", "Rate"]:
            continue
        if len(cells) != 2 or not re.fullmatch(r"\d{1,2}-[A-Z]{3}-\d{2}", cells[0]):
            raise ValueError("Unverified H.10 historical row layout")
        # This official page explicitly covers 2000 onward; no locale/pivot guessing.
        parsed = datetime.strptime(cells[0], "%d-%b-%y").date()
        day = parsed.replace(year=2000 + int(cells[0][-2:]))
        if day in result:
            raise ValueError("Duplicate H.10 HTML date, even if the quotes agree")
        if day > vintage:
            raise ValueError("H.10 observation is later than its history release date")
        quote(cells[1])
        result[day] = cells[1]
    return result, vintage


def holiday_evidence(content: bytes, year: int) -> dict[date, str]:
    soup = BeautifulSoup(content, "html.parser")
    text = soup.get_text(" ", strip=True)
    if not all(
        phrase in text
        for phrase in (
            "Board of Governors will be closed",
            "Federal Reserve Banks",
            "For holidays falling on Saturday",
            "preceding Friday",
            "For holidays falling on Sunday",
            "following Monday",
        )
    ):
        raise ValueError("K.8 observance definitions missing")
    tables = soup.find_all("table")
    if len(tables) != 1:
        raise ValueError("Ambiguous K.8 holiday table")
    rows = [[c.get_text(" ", strip=True) for c in r.find_all(["th", "td"])] for r in tables[0].find_all("tr")]
    years = [int(cell) for cell in rows[0][1:]]
    if year not in years or len(years) != len(set(years)) or len(rows) != 12:
        raise ValueError("Requested holiday year is not verified by the preserved K.8 table")
    result = {}
    for row in rows[1:]:
        if len(row) != len(years) + 1:
            raise ValueError("K.8 holiday table schema changed")
        for y, cell in zip(years, row[1:], strict=True):
            day = datetime.strptime(f"{cell.rstrip('*')} {y}", "%B %d %Y").date()
            # This labels documented Board observance, not a universal FX calendar.
            observed = (
                day - timedelta(days=1)
                if day.weekday() == 5
                else day + timedelta(days=1)
                if day.weekday() == 6
                else day
            )
            result[observed] = row[0]
    return result


def reconcile(csv_data: dict, html_data: dict, period: str, holidays: dict) -> list[dict]:
    start, end = month_bounds(period)
    expected = {
        start + timedelta(days=i)
        for i in range((end - start).days + 1)
        if (start + timedelta(days=i)).weekday() < 5
    }
    left = {day: value for day, value in csv_data.items() if start <= day <= end}
    right = {day: value for day, value in html_data.items() if start <= day <= end}
    if set(left) != expected or set(right) != expected:
        raise ValueError(
            "Incomplete H.10 month or unexpected weekend: every weekday, including ND, is required"
        )
    result = []
    for day in sorted(expected):
        value, other = quote(left[day]), quote(right[day])
        if value != other:
            raise ValueError("Official H.10 sources disagree; retain both vintages and review revisions")
        if value is None and day not in holidays:
            raise ValueError("ND on a date without verified K.8 evidence requires separate source review")
        result.append(
            {
                "date": day,
                "source_value": left[day],
                "rate_close": float(value) if value is not None else None,
                "observation_status": "ND" if value is None else "observed",
                "holiday_evidence": holidays.get(day),
            }
        )
    if not any(row["observation_status"] == "observed" for row in result):
        raise ValueError("H.10 month has no observed quotes")
    return result
