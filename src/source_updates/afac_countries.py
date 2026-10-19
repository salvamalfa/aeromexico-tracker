"""Exact country-bulletin YTD boxes; rounded monthly charts are deliberately excluded."""

from __future__ import annotations

from collections import defaultdict
from contextlib import closing
import io
import re

import pandas as pd
import pdfplumber

from src.source_updates.afac_airports import SPANISH, folded
from src.source_updates.afac_margins import load, routes

VERSION = "afac_country_bulletin_ytd_v1"
TABLE = "fact_afac_country_bulletin_ytd"
GRAIN = ["period_id", "metric_key", "country_as_reported"]
# Literal page headings in the retained report, not an inferred all-country universe.
PAGES = {
    3: "CANADÁ",
    4: "ESTADOS UNIDOS",
    6: "ALEMANIA",
    7: "BÉLGICA",
    8: "ESPAÑA",
    9: "FRANCIA",
    10: "ITALIA",
    11: "PAISES BAJOS",
    12: "PORTUGAL",
    13: "REINO UNIDO",
    14: "SUIZA",
    15: "TURQUÍA",
    17: "ARGENTINA",
    18: "BRASIL",
    19: "CHILE",
    20: "COLOMBIA",
    21: "PERÚ",
    22: "VENEZUELA",
    24: "BELICE",
    25: "COSTA RICA",
    26: "EL SALVADOR",
    27: "GUATEMALA",
    28: "HONDURAS",
    29: "NICARAGUA",
    30: "PANAMÁ",
    32: "CUBA",
    33: "REPÚBLICA DOMINICANA",
    35: "EMIRATOS ÁRABES UNIDOS",
    36: "JAPÓN",
}


def boxes(text, year, month):
    """Read labelled year/count rows inside a verified fixed-position YTD box."""
    lines = [v.strip() for v in text.splitlines() if v.strip()]
    if (
        lines[:3] != ["Comparativo", f"Acumulado a {SPANISH[month - 1].title()}", "Pasajeros"]
        or lines.count("Vuelos") != 1
    ):
        raise ValueError("Country YTD box labels/month changed")
    split = lines.index("Vuelos")
    output = {}
    for metric, section in [
        ("passengers", lines[3:split]),
        ("flights_as_reported_country_bulletin", lines[split + 1 :]),
    ]:
        if len(section) != 3 or not re.fullmatch(
            r"(?:Variación|ariación|riación|ación) [▲▼]\d+(?:\.\d+)?%", section[0]
        ):
            raise ValueError("Country YTD variation row/layout changed")
        observations = []
        for line in section[1:]:
            match = re.fullmatch(r"(20\d{2}) ((?:\d{1,3}(?:,\d{3})+)|\d+)", line)
            if match:
                observations.append((int(match[1]), int(match[2].replace(",", ""))))
            else:
                raise ValueError("Unreviewed numeric content in exact country YTD box")
        if [y for y, _ in observations] != [year - 1, year]:
            raise ValueError("Country YTD current/prior year rows incomplete or changed")
        for y, value in observations:
            if value > 2**53 - 1:
                raise ValueError("Country count cannot be represented exactly")
            output[(metric, y)] = value
    return output


def pdf_rows(content, original, period):
    if not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("Country report requires explicit edition month")
    year, month = int(period[:4]), int(period[-2:])
    output = []
    if len(content) > 5_000_000 or not content.startswith(b"%PDF-"):
        raise ValueError("Country bulletin PDF outside reviewed format/size")
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        if len(pdf.pages) != 37 or any((p.width, p.height) != (960, 540) for p in pdf.pages):
            raise ValueError("Country report page/layout contract changed")
        title = " ".join((pdf.pages[0].extract_text() or "").split())
        if title != f"Boletín de Estadística Operacional por País {SPANISH[month - 1].title()} {year}":
            raise ValueError("Country report title month/year changed")
        for page_number, country in PAGES.items():
            page = pdf.pages[page_number - 1]
            heading = (page.crop((0, 0, 960, 65)).extract_text() or "").strip()
            context = page.crop((0, 65, 960, 104)).extract_text() or ""
            footer = page.crop((0, 505, 960, 540)).extract_text() or ""
            coverage = re.fullmatch(
                r"Pasajeros transportados por empresas nacionales y extranjeras Vuelos realizados y pasajeros transportados entre México y (.+)\nhacia y desde (.+) en servicio regular por empresas nacionales y extranjeras en servicio regular",
                context,
            )
            expected_country = "EAU" if country == "EMIRATOS ÁRABES UNIDOS" else country
            if (
                heading != country
                or not coverage
                or {folded(value) for value in coverage.groups()} != {folded(expected_country)}
                or "Fuente: SICT, AFAC, DREE. Información proporcionada por las aerolíneas." not in footer
                or f"{SPANISH[month - 1].title()} {year}" not in footer
            ):
                raise ValueError("Country source heading/coverage/footer changed")
            values = boxes(page.crop((760, 100, 940, 260)).extract_text() or "", year, month)
            for (metric, y), value in values.items():
                output.append(
                    dict(
                        period_id=f"{y}YTD{month:02d}",
                        period_type="year_to_date",
                        period_start=f"{y}-01-01",
                        period_end_month=f"{y}-{month:02d}",
                        report_period=period,
                        country_as_reported=country,
                        metric_key=metric,
                        value=value,
                        unit="count",
                        carrier_key=None,
                        service_scope="national_and_foreign_companies_regular_country_bulletin_as_reported",
                        source_system=original["source_system"],
                        source_file=original["source_file"],
                        source_hash=original["sha256"],
                        ingested_at=pd.Timestamp(original["downloaded_at"]),
                        source_locator=f"page:{page_number}/bbox:760,100,940,260/{metric}/{y}",
                        parser_version=VERSION,
                        agent_eligible=False,
                    )
                )
    return pd.DataFrame(output)


def parse(inputs, period):
    content, original = inputs["pdf"]
    frame = pdf_rows(content, original, period)
    year, month = int(period[:4]), int(period[-2:])
    route_bytes, route_original = inputs["routes"]
    with closing(load(route_bytes)) as book:
        route_rows, _, _ = routes(book, route_original, year, month)
    country_totals = defaultdict(int)
    for row in route_rows:
        if row["market"] != "international" or row["metric_key"] != "passengers":
            continue
        country = (
            row["origin_country_as_reported"]
            if folded(row["origin_country_as_reported"]) != "MEXICO"
            else row["destination_country_as_reported"]
        )
        country_totals[folded(country)] += row["value"]
    checks = []
    for row in frame.loc[
        frame.metric_key.eq("passengers") & frame.period_id.eq(f"{year}YTD{month:02d}")
    ].itertuples(index=False):
        key = folded(row.country_as_reported)
        if key == "EMIRATOSARABESUNIDOS":
            key = "EMIRATOSARABES"  # literal OD country label differs; both originals retained.
        if key not in country_totals or country_totals[key] != row.value:
            raise ValueError("Country exact current-year YTD passengers disagree with same-edition O-D")
        checks.append(
            dict(
                country_as_reported=row.country_as_reported,
                bulletin_passengers=row.value,
                od_passengers=country_totals[key],
                difference=0,
            )
        )
    if len(checks) != len(PAGES) or frame.duplicated(GRAIN).any():
        raise ValueError("Country bulletin native domain/grain incomplete")
    return frame, dict(
        rows=len(frame),
        report_period=period,
        months_validated=[],
        ytd_periods_validated=sorted(frame.period_id.unique()),
        countries_in_report=len(PAGES),
        exact_ytd_passenger_crosschecks=checks,
        monthly_values_imported=0,
        rounded_chart_values_imported=0,
        source_publication_at=None,
        published_at=None,
        release_lag_days=None,
        scope="retained_country_bulletin_exact_current_prior_YTD_boxes_only_not_monthly_country_series",
        country_flight_definition="literal_country_bulletin_flights_not_harmonized_with_all_OD_regular_flights",
        crosscheck_scope="current_YTD_passengers_only; prior comparison and bulletin flights are literal PDF values",
        missing_countries_not_zero=True,
        zero_semantics="explicit_source_YTD_numeric_zero_only",
    )
