"""OMA terminal-passenger tables: airport/group, market and monthly/YTD remain distinct."""

from __future__ import annotations

import calendar
import io
import re
from datetime import datetime

import pandas as pd
from pypdf import PdfReader

from src.source_updates.afac_airports import folded
from src.source_updates.authorities import count
from src.source_updates.calendar import local_time
from src.source_updates.checks import period_end

VERSION = "retained_oma_terminal_traffic_v1"
TABLE = "fact_oma_retained_terminal_traffic"
GRAIN = ["period_id", "period_type", "market", "airport_as_reported"]
AIRPORTS = {
    folded(name)
    for name in [
        "Acapulco",
        "Ciudad Juárez",
        "Culiacán",
        "Chihuahua",
        "Durango",
        "Mazatlán",
        "Monterrey",
        "Reynosa",
        "San Luis Potosí",
        "Tampico",
        "Torreón",
        "Zacatecas",
        "Zihuatanejo",
    ]
}
NOTE = (
    "* Terminal passengers: includes passengers on the three types of aviation "
    "(commercial, charter, and general aviation), and excludes passengers in transit."
)


def source_count(token):
    if not re.fullmatch(r"(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)", token):
        raise ValueError("OMA integer grouping is not canonical")
    return count(token.replace(",", ""))


def parse(inputs, period):
    if not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("OMA requires an explicit report month")
    content, original = inputs["pdf"]
    if len(content) > 3_000_000 or not content.startswith(b"%PDF-"):
        raise ValueError("OMA traffic PDF outside reviewed bound")
    year, month = int(period[:4]), int(period[-2:])
    abbr = calendar.month_abbr[month]
    pdf = PdfReader(io.BytesIO(content))
    if not 2 <= len(pdf.pages) <= 4:
        raise ValueError("OMA report page contract changed")
    text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    if (
        NOTE not in " ".join(text.split())
        or "Grupo Aeroportuario del Centro Norte" not in text
        or f"in {calendar.month_name[month]} {year}" not in text
    ):
        raise ValueError("OMA issuer, month or terminal-passenger scope changed")
    dates = re.findall(r"Mexico City\s*, Mexico, ([A-Z][a-z]+ \d{1,2}, 20\d{2})", text)
    if len(dates) != 1:
        raise ValueError("OMA source report dateline absent or ambiguous")
    reported_date = datetime.strptime(dates[0], "%B %d, %Y").date().isoformat()
    if (
        not period_end(period)
        < datetime.fromisoformat(reported_date).date()
        <= local_time(original["downloaded_at"]).date()
    ):
        raise ValueError("OMA reported dateline must follow the completed month and precede capture")
    header = (
        rf"{abbr}-{year - 1}\s+{abbr}-{year}\s+Change %\s+Jan-{abbr}\s+{year - 1}"
        rf"\s+Jan-{abbr}\s+{year}\s+Change %"
    )
    parts = re.split(header, text)
    if len(parts) != 5:
        raise ValueError("OMA four monthly/YTD table headers missing or changed")
    tables = []
    row_pattern = re.compile(
        r"^(.+?)\s+([\d,]+)\s+([\d,]+)\s+(\(?-?[\d.]+\)?)\s+([\d,]+)\s+([\d,]+)\s+(\(?-?[\d.]+\)?)\s*$"
    )
    for index, part in enumerate(parts[1:], 1):
        parsed = []
        for line in part.splitlines():
            match = row_pattern.fullmatch(line.strip())
            if not match:
                continue
            label = match[1]
            values = [source_count(match[i]) for i in [2, 3, 5, 6]]
            if index == 1 and label not in {"Domestic", "International", "OMA Total"}:
                raise ValueError("Unknown OMA group summary row")
            if index > 1 and folded(label) not in AIRPORTS | {"OMATOTAL"}:
                raise ValueError("Unknown OMA airport row")
            parsed.append((label, values))
        labels = [folded(label) for label, _ in parsed]
        expected = {"DOMESTIC", "INTERNATIONAL", "OMATOTAL"} if index == 1 else AIRPORTS | {"OMATOTAL"}
        if set(labels) != expected or len(labels) != len(expected):
            raise ValueError("OMA monthly airport/group native domain incomplete or duplicated")
        tables.append(parsed)
    summaries = {folded(k): v for k, v in tables[0]}
    by_market = {
        market: {folded(k): v for k, v in table}
        for market, table in zip(["total", "domestic", "international"], tables[1:], strict=True)
    }
    checks = 0
    for col in range(4):
        if summaries["DOMESTIC"][col] + summaries["INTERNATIONAL"][col] != summaries["OMATOTAL"][col]:
            raise ValueError("OMA summary domestic/international sum differs")
        checks += 1
        for market in by_market:
            values = by_market[market]
            if (
                sum(values[a][col] for a in AIRPORTS) != values["OMATOTAL"][col]
                or values["OMATOTAL"][col]
                != summaries[
                    {"total": "OMATOTAL", "domestic": "DOMESTIC", "international": "INTERNATIONAL"}[market]
                ][col]
            ):
                raise ValueError("OMA airport/group or summary totals disagree")
            checks += 2
        for label in AIRPORTS:
            if (
                by_market["domestic"][label][col] + by_market["international"][label][col]
                != by_market["total"][label][col]
            ):
                raise ValueError("OMA airport domestic/international sum differs")
            checks += 1
    output = []
    for table_index, (market, table) in enumerate(
        zip(["total", "domestic", "international"], tables[1:], strict=True), 2
    ):
        for row_index, (airport, values) in enumerate(table, 1):
            for column, value in enumerate(values):
                current_year = year if column % 2 else year - 1
                ytd = column >= 2
                output.append(
                    dict(
                        period_id=f"{current_year}YTD{month:02d}" if ytd else f"{current_year}M{month:02d}",
                        period_type="year_to_date" if ytd else "month",
                        report_period=period,
                        metric_key="terminal_passengers",
                        market=market,
                        airport_as_reported=airport,
                        airport_group="OMA",
                        scope_level="group" if folded(airport) == "OMATOTAL" else "airport",
                        value=value,
                        unit="passengers",
                        carrier_key=None,
                        source_definition=NOTE,
                        source_system=original["source_system"],
                        source_file=original["source_file"],
                        source_hash=original["sha256"],
                        ingested_at=pd.Timestamp(original["downloaded_at"]),
                        source_locator=f"text-table:{table_index}/row:{row_index}/count-column:{column + 1}",
                        parser_version=VERSION,
                        agent_eligible=False,
                    )
                )
    frame = pd.DataFrame(output)
    if frame.duplicated(GRAIN).any():
        raise ValueError("OMA duplicate terminal-passenger native grain")
    return frame, dict(
        rows=len(frame),
        report_period=period,
        complete_month_certified=True,
        months_validated=[f"{year - 1}M{month:02d}", period],
        ytd_periods_validated=[f"{year - 1}YTD{month:02d}", f"{year}YTD{month:02d}"],
        airports=13,
        reconciliations=checks,
        source_report_date_as_reported=reported_date,
        published_at=None,
        release_lag_days=None,
        scope="retained_OMA_terminal_passengers_13_airports_group_and_markets_month_vs_YTD_separate_not_airline_traffic",
        commercial_charter_general_aviation_included=True,
        transit_excluded=True,
        monthly_YTD_not_combined=True,
    )
