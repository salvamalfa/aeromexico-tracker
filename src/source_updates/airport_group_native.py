"""Reviewed SEC airport traffic: country, precision, monthly and YTD stay explicit."""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlsplit

import pandas as pd
from bs4 import BeautifulSoup

from src.source_updates.calendar import local_time
from src.source_updates.government_traffic import month

PRODUCTS = {"gap_traffic", "asur_traffic"}
VERSION = "airport_group_native_v1"
GRAIN = ["operator_group", "entity_key", "period_id", "period_type", "market"]
GAP = dict(
    zip(
        [
            "Guadalajara",
            "Tijuana*",
            "Los Cabos",
            "Puerto Vallarta",
            "Montego Bay",
            "Guanajuato",
            "Hermosillo",
            "Kingston",
            "Morelia",
            "La Paz",
            "Mexicali",
            "Aguascalientes",
            "Los Mochis",
            "Manzanillo",
        ],
        ["GDL", "TIJ", "SJD", "PVR", "MBJ", "BJX", "HMO", "KIN", "MLM", "LAP", "MXL", "AGU", "LMM", "ZLO"],
        strict=True,
    )
)
ASUR = dict(
    zip(
        ["CUN", "CZM", "HUX", "MID", "MTT", "OAX", "TAP", "VER", "VSA"],
        [
            "Cancun",
            "Cozumel",
            "Huatulco",
            "Merida",
            "Minatitlan",
            "Oaxaca",
            "Tapachula",
            "Veracruz",
            "Villahermosa",
        ],
        strict=True,
    )
)
CBX = "Passengers in Tijuana who use CBX in both directions are classified as international."
ASUR_SCOPE = "Transit and general aviation passengers are excluded only for Mexico and Colombia."


def cells(table):
    return [
        [" ".join(c.get_text(" ", strip=True).split()) for c in tr.find_all(["td", "th"], recursive=False)]
        for tr in table.find_all("tr")
    ]


def number(token, decimals):
    pattern = r"(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)" + (r"\.\d" if decimals else "")
    if not re.fullmatch(pattern, token):
        raise ValueError("Airport native count missing, negative or grouping/precision changed")
    value = Decimal(token.replace(",", ""))
    if value > 10**12:
        raise ValueError("Airport native magnitude outside reviewed bound")
    return value


def reconcile(actual, parts, quantum):
    if abs(actual - sum(parts)) > Decimal(quantum) * (len(parts) + 1) / 2:
        raise ValueError("Airport native reconciliation exceeds source rounding bound")


def append(
    rows,
    original,
    group,
    entity,
    name,
    country,
    market,
    values,
    period,
    locator,
    *,
    scope,
    decimals=0,
    derived=False,
):
    year, end = month(period)
    if len(values) != 4:
        raise ValueError("Native comparison requires four monthly/YTD values")
    tolerance = Decimal("0.1") * (12 if derived else 1) if decimals else Decimal(0)
    for year_column in (0, 1):
        if values[year_column] > values[year_column + 2] + tolerance:
            raise ValueError("Native YTD is smaller than the contained report month")
        if end == 1 and values[year_column] != values[year_column + 2]:
            raise ValueError("January and YTD must describe the same observation period")
    for col, value in enumerate(values):
        current = year if col % 2 else year - 1
        kind = "year_to_date" if col >= 2 else "month"
        rows.append(
            dict(
                operator_group=group,
                entity_key=entity,
                airport_name=name,
                country=country,
                airport_iata=entity if len(entity) == 3 and entity not in {"ALL"} else None,
                period_id=f"{current}YTD{end:02d}" if col >= 2 else f"{current}M{end:02d}",
                report_period=period,
                period_type=kind,
                market=market,
                metric_key="terminal_passengers",
                value=float(value),
                source_value=str(value),
                unit="thousand_passengers" if decimals else "passengers",
                source_decimals=decimals,
                precision_passengers=100 if decimals else 1,
                value_status="calculated_sum_of_rounded_airports" if derived else "reported",
                is_preliminary=group == "GAP",
                source_definition=scope,
                source_system=original["source_system"],
                source_file=original["source_file"],
                source_hash=original["sha256"],
                ingested_at=pd.Timestamp(original["downloaded_at"]).as_unit("ns"),
                parser_version=VERSION,
                source_locator=f"{locator}/count-column:{col + 1}",
                agent_eligible=False,
            )
        )


def parse_gap(soup, text, original, period):
    year, end = month(period)
    abbr, full = calendar.month_abbr[end], calendar.month_name[end]
    if (
        f"announces preliminary terminal passenger traffic figures for {full} {year}" not in text
        or "GRUPO AEROPORTUARIO DEL PACÍFICO" not in text
        or "12 Mexican airports operated by GAP" not in text
        or "GAP’s airports in Jamaica" not in text
        or CBX not in text
    ):
        raise ValueError("GAP issuer, report month, preliminary or CBX scope changed")
    datelines = re.findall(r"GUADALAJARA, Mexico, ([A-Z][a-z]+\.? \d{2}, 20\d{2})", text)
    if len(datelines) != 1:
        raise ValueError("GAP report dateline missing or ambiguous")
    reported = datetime.strptime(datelines[0].replace(".", ""), "%b %d, %Y").date()
    header = [
        "Airport",
        f"{abbr}-{str(year - 1)[2:]}",
        f"{abbr}-{str(year)[2:]}",
        "% Change",
        f"Jan - {abbr} {str(year - 1)[2:]}",
        f"Jan - {abbr} {str(year)[2:]}",
        "% Change",
    ]
    rows, data, checks = [], {}, 0
    for market in ["domestic", "international", "total"]:
        title = f"{market.title()} Terminal Passengers (in thousands):"
        # Bind each table to its physical heading; never assume the first three tables are markets.
        matches = [
            t
            for t in soup.find_all("table")
            if " ".join(t.find_previous(["p", "div"]).get_text(" ", strip=True).split()) == title
        ]
        if len(matches) != 1:
            raise ValueError("GAP market table heading/unit absent or duplicated")
        table = cells(matches[0])
        if table[0] != header:
            raise ValueError("GAP monthly/YTD comparative headers changed")
        parsed = {}
        for index, row in enumerate(table[1:], 1):
            if not any(row):
                continue
            if len(row) != 9 or row[0] not in GAP.keys() | {"Total"} or row[0] in parsed:
                raise ValueError("GAP airport domain, row width or duplicates changed")
            if any(not re.fullmatch(r"\(?-?\d+\.\d", row[i]) for i in [3, 7]) or any(
                row[i] not in {"%", "%)"} for i in [4, 8]
            ):
                raise ValueError("GAP percentage columns shifted")
            values = [number(row[i], 1) for i in [1, 2, 5, 6]]
            parsed[row[0]] = values
            entity = GAP.get(row[0], "ALL")
            country = "JM" if entity in {"MBJ", "KIN"} else "MULTI" if entity == "ALL" else "MX"
            append(
                rows,
                original,
                "GAP",
                entity,
                row[0],
                country,
                market,
                values,
                period,
                f"market:{market}/row:{index}",
                scope="Preliminary terminal passengers. " + CBX,
                decimals=1,
            )
        if set(parsed) != GAP.keys() | {"Total"}:
            raise ValueError("GAP requires all fourteen airports and the reported worldwide total")
        for col in range(4):
            reconcile(parsed["Total"][col], [parsed[a][col] for a in GAP], "0.1")
            checks += 1
        mexico = [a for a in GAP if GAP[a] not in {"MBJ", "KIN"}]
        append(
            rows,
            original,
            "GAP",
            "MX",
            "GAP Mexico (calculated)",
            "MX",
            market,
            [sum(parsed[a][col] for a in mexico) for col in range(4)],
            period,
            f"market:{market}/sum:12-MX-airports",
            decimals=1,
            derived=True,
            scope="Sum of twelve rounded Mexican airport values, not reported worldwide GAP total. " + CBX,
        )
        data[market] = parsed
    for entity in GAP.keys() | {"Total"}:
        for col in range(4):
            reconcile(
                data["total"][entity][col],
                [data[m][entity][col] for m in ["domestic", "international"]],
                "0.1",
            )
            checks += 1
    return rows, checks, reported


def asur_header(table, title, period):
    year, end = month(period)
    expected = [
        [],
        ["", calendar.month_name[end], "% Chg", "", "Year to date", "% Chg"],
        [str(year - 1), str(year), "", str(year - 1), str(year)],
    ]
    if not table or not table[0] or table[0][0] != title or table[1:3] != expected[1:]:
        raise ValueError("ASUR table title/month/YTD comparative header changed")


def asur_values(row, *, airport=False):
    if len(row) != (9 if airport else 8):
        raise ValueError("ASUR count row width changed")
    offset = 1 if airport else 0
    return [number(row[i + offset], 0) for i in [1, 2, 5, 6]]


def parse_asur(soup, text, original, period):
    year, end = month(period)
    full = calendar.month_name[end]
    if (
        f"ASUR Announces Total Passenger Traffic for {full} {year}" not in text
        or ASUR_SCOPE not in text
        or "Grupo Aeroportuario del Sureste, S.A.B. de C.V." not in text
    ):
        raise ValueError("ASUR issuer, report month or native scope changed")
    days = calendar.monthrange(year, end)[1]
    if (
        f"from {full} 1 to {full} {days}, {year}, and from {full} 1 to {full} "
        f"{calendar.monthrange(year - 1, end)[1]}, {year - 1}" not in text
    ):
        raise ValueError("ASUR complete monthly comparison dates absent")
    datelines = re.findall(r"Mexico City, ([A-Z][a-z]+ \d{1,2}, 20\d{2}) -", text)
    if len(datelines) != 1:
        raise ValueError("ASUR report dateline absent or ambiguous")
    reported = datetime.strptime(datelines[0], "%B %d, %Y").date()
    tables = [cells(t) for t in soup.find_all("table")]

    def choose(title):
        found = [t for t in tables if t and t[0] and t[0][0] == title]
        if len(found) != 1:
            raise ValueError("ASUR native table missing or duplicated")
        asur_header(found[0], title, period)
        return found[0]

    summary = choose("Passenger Traffic Summary")
    detail = choose("Mexico Passenger Traffic")
    if len(summary) != 15 or len(detail) != 33:
        raise ValueError("ASUR country/airport domain size changed")
    rows, checks, countries = [], 0, {}
    for block, (label, entity, country) in enumerate(
        [
            ("Mexico", "MX", "MX"),
            ("San Juan, Puerto Rico", "PR", "PR"),
            ("Colombia", "CO", "CO"),
            ("Total Traffic", "ALL", "MULTI"),
        ]
    ):
        values = {}
        for off, (native_label, market) in enumerate(
            [(label, "total"), ("Domestic Traffic", "domestic"), ("International Traffic", "international")]
        ):
            row = summary[3 + 3 * block + off]
            if row[0] != native_label:
                raise ValueError("ASUR summary country/market order changed")
            values[market] = asur_values(row)
            append(
                rows,
                original,
                "ASUR",
                entity,
                label,
                country,
                market,
                values[market],
                period,
                f"summary/row:{3 + 3 * block + off}",
                scope=ASUR_SCOPE,
            )
        for col in range(4):
            reconcile(values["total"][col], [values[m][col] for m in ["domestic", "international"]], "0")
            checks += 1
        countries[entity] = values
    for market in ["domestic", "international", "total"]:
        for col in range(4):
            reconcile(
                countries["ALL"][market][col], [countries[c][market][col] for c in ["MX", "PR", "CO"]], "0"
            )
            checks += 1
    airports = {}
    for block, (label, market) in enumerate(
        [
            ("Domestic Traffic", "domestic"),
            ("International Traffic", "international"),
            ("Traffic Total Mexico", "total"),
        ]
    ):
        row = detail[3 + 10 * block]
        if row[0] != label or asur_values(row) != countries["MX"][market]:
            raise ValueError("ASUR Mexico detail total differs from country summary")
        checks += 4
        domain = {}
        for i in range(9):
            row = detail[4 + 10 * block + i]
            if len(row) < 2 or row[0] not in ASUR or row[1] != ASUR[row[0]] or row[0] in domain:
                raise ValueError("ASUR Mexico airport identity/domain changed")
            domain[row[0]] = asur_values(row, airport=True)
            append(
                rows,
                original,
                "ASUR",
                row[0],
                row[1],
                "MX",
                market,
                domain[row[0]],
                period,
                f"Mexico/row:{4 + 10 * block + i}",
                scope=ASUR_SCOPE,
            )
        if set(domain) != ASUR.keys():
            raise ValueError("ASUR nine Mexican airports required")
        for col in range(4):
            reconcile(countries["MX"][market][col], [domain[a][col] for a in ASUR], "0")
            checks += 1
        airports[market] = domain
    for airport in ASUR:
        for col in range(4):
            reconcile(
                airports["total"][airport][col],
                [airports[m][airport][col] for m in ["domestic", "international"]],
                "0",
            )
            checks += 1
    return rows, checks, reported


def read(product, inputs, period):
    if product not in PRODUCTS:
        raise ValueError("Unsupported airport group product")
    year, end = month(period)
    content, original = inputs["html"]
    cik = "1347557" if product == "gap_traffic" else "1123452"
    if (
        len(content) > 3_000_000
        or original["source_system"] not in {"sec", "sec_edgar", "sec_filing"}
        or not urlsplit(original["source_url"]).path.startswith(f"/Archives/edgar/data/{cik}/")
    ):
        raise ValueError("SEC artifact must belong to the exact airport group CIK")
    soup = BeautifulSoup(content, "html.parser")
    if soup.find("html") is None or soup.find("script") is not None:
        raise ValueError("Expected reviewed static SEC HTML")
    text = " ".join(soup.get_text(" ", strip=True).split())
    rows, checks, reported = (parse_gap if product == "gap_traffic" else parse_asur)(
        soup, text, original, period
    )
    if (
        not date(year, end, calendar.monthrange(year, end)[1])
        <= reported
        <= local_time(original["downloaded_at"]).date()
    ):
        raise ValueError("Airport report dateline inconsistent with closed month/capture")
    frame = pd.DataFrame(rows)
    if frame.duplicated(GRAIN).any() or frame.empty:
        raise ValueError("Duplicate or empty airport native observation grain")
    return frame, dict(
        reconciliations=checks,
        report_period=period,
        source_report_date_as_reported=reported.isoformat(),
        first_publication_date=None,
        release_lag_days=None,
        mexico_airports=12 if product == "gap_traffic" else 9,
        native_monthly_and_YTD_kept_separate=True,
        ytd_contains_month_validated=True,
        complete_month_certified=True,
        counts_are_rounded=product == "gap_traffic",
        mexico_group_is_calculated=product == "gap_traffic",
        CBX_international_as_reported=product == "gap_traffic",
        latest_source_availability_verified=False,
    )
