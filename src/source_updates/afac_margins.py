"""Verify same-edition AFAC city-pair and reporting-company margins, without fitting cells."""

from __future__ import annotations

from collections import defaultdict
from contextlib import closing
import io
import re
from zipfile import ZipFile

import openpyxl
import pandas as pd

from src.source_updates.afac_airports import MONTHS, SPANISH, folded, number

VERSION = "afac_retained_margins_v1"
TABLE = "fact_afac_retained_margins"
GRAIN = [
    "period_id",
    "metric_key",
    "margin_scope",
    "market",
    "carrier_block",
    "carrier_name_as_reported",
    "origin_city_as_reported",
    "origin_country_as_reported",
    "destination_city_as_reported",
    "destination_country_as_reported",
]
SOURCE_NOTE = "FUENTE: SICT, AFAC, DREE. Información proporcionada por las aerolíneas."
MONTH_HEADERS = [v.title() for v in MONTHS]


def load(content):
    if len(content) > 12_000_000:
        raise ValueError("AFAC margin workbook exceeds reviewed bound")
    with ZipFile(io.BytesIO(content)) as archive:
        if sum(e.file_size for e in archive.infolist()) > 60_000_000 or len(archive.namelist()) != len(
            set(archive.namelist())
        ):
            raise ValueError("Oversized/duplicate AFAC workbook ZIP members")
    return openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)


def values(row, offset, last):
    observed = [int(number(v, count=True)) for v in row[offset : offset + 12]]
    if len(observed) != 12 or any(observed[last:]):
        raise ValueError("Future month template changed")
    if sum(observed) != number(row[offset + 12], count=True):
        raise ValueError("AFAC row annual/YTD sum mismatch")
    return observed


def observation(
    original,
    year,
    month,
    metric,
    value,
    locator,
    *,
    scope,
    market,
    carrier=None,
    block=None,
    origin=None,
    destination=None,
    origin_country=None,
    destination_country=None,
    notes=None,
    estimated=None,
):
    return dict(
        period_id=f"{year}M{month:02d}",
        period_type="month",
        metric_key=metric,
        value=value,
        unit="count",
        margin_scope=scope,
        market=market,
        carrier_name_as_reported=carrier,
        carrier_block=block,
        origin_city_as_reported=origin,
        destination_city_as_reported=destination,
        origin_country_as_reported=origin_country,
        destination_country_as_reported=destination_country,
        value_kind="source_reported_margin",
        source_cell_estimated=estimated,
        source_notes=notes,
        source_system=original["source_system"],
        source_file=original["source_file"],
        source_hash=original["sha256"],
        ingested_at=pd.Timestamp(original["downloaded_at"]),
        source_locator=locator,
        parser_version=VERSION,
        agent_eligible=False,
    )


def routes(book, original, year, last):
    output = []
    totals = {}
    checks = 0
    for sheet, market, keys, flights, pax in [
        ("REG NAC", "domestic", 2, 2, 15),
        ("REG INT", "international", 4, 4, 17),
    ]:
        rows = list(book[sheet].values)
        if not any(row[0] == SOURCE_NOTE for row in rows):
            raise ValueError("AFAC airline-provided source note missing")
        title = "EN SERVICIO REGULAR " + ("NACIONAL" if keys == 2 else "INTERNACIONAL") + f", {year}"
        if not any(isinstance(v, str) and v.startswith(title) for v in rows[2]):
            raise ValueError("AFAC route year/service edition changed")
        expected_keys = (
            ["ORIGEN / FROM", "DESTINO / TO"]
            if keys == 2
            else ["ORIGEN / FROM", "PAÍS ORIGEN / COUNTRY FROM", "DESTINO / TO", "PAÍS DESTINO / COUNTRY TO"]
        )
        if list(rows[5][:keys]) != expected_keys:
            raise ValueError("AFAC route city/country header changed")
        if rows[4][flights] != "VUELOS / FLIGHTS" or rows[4][pax] != "PASAJEROS / PASSENGERS":
            raise ValueError("AFAC route metric blocks changed")
        for offset in [flights, pax]:
            if list(rows[5][offset : offset + 12]) != MONTH_HEADERS or rows[5][offset + 12] != "Total":
                raise ValueError("AFAC route month/total headers changed")
        sum_rows = {"flights_as_reported": [0] * 12, "passengers": [0] * 12}
        total_rows = []
        seen = set()
        closed = False
        for index, row in enumerate(rows[6:], 7):
            if row[0] is None:
                if any(v is not None for v in row[:keys]):
                    raise ValueError("Partial AFAC city-pair identifiers")
                continue
            if str(row[0]).startswith("FUENTE:"):
                continue
            if folded(row[0]) == "TOTAL":
                total_rows.append(row)
                closed = True
                continue
            if closed:
                raise ValueError("AFAC route rows after grand total")
            labels = tuple(row[:keys])
            if not all(isinstance(v, str) and v.strip() for v in labels) or labels in seen:
                raise ValueError("Missing/duplicate AFAC city-pair grain")
            seen.add(labels)
            if keys == 4 and sum(folded(v) == "MEXICO" for v in [row[1], row[3]]) != 1:
                raise ValueError("AFAC international city pair lacks one Mexican endpoint")
            for metric, offset in [("flights_as_reported", flights), ("passengers", pax)]:
                observed = values(row, offset, last)
                sum_rows[metric] = [a + b for a, b in zip(sum_rows[metric], observed, strict=True)]
                for m, value in enumerate(observed[:last], 1):
                    output.append(
                        observation(
                            original,
                            year,
                            m,
                            metric,
                            value,
                            f"{sheet}!R{index}C{offset + m}",
                            scope="directed_city_pair_all_carriers",
                            market=market,
                            origin=row[0],
                            destination=row[1] if keys == 2 else row[2],
                            origin_country="Mexico" if keys == 2 else row[1],
                            destination_country="Mexico" if keys == 2 else row[3],
                        )
                    )
        if len(total_rows) != 1 or not seen:
            raise ValueError("AFAC route grand total absent/repeated")
        for metric, offset in [("flights_as_reported", flights), ("passengers", pax)]:
            if values(total_rows[0], offset, last) != sum_rows[metric]:
                raise ValueError("AFAC route monthly grand total mismatch")
            totals[(market, metric)] = sum_rows[metric]
            checks += 12
    return output, totals, checks


def footnotes(rows, year):
    rules = []
    for row in rows:
        text = row[0]
        if not isinstance(text, str) or not text.startswith("*"):
            continue
        match = re.fullmatch(r"\*+ Datos estimados de (.+?) para (.+?) (20\d{2})\.", text)
        if not match or int(match[3]) != year:
            raise ValueError("Unreviewed AFAC estimated-cell note")
        months = match[2].split(" y ")
        if any(m not in SPANISH for m in months):
            raise ValueError("Unreviewed AFAC estimated month")
        rules.append((folded(match[1]), {SPANISH.index(m) + 1 for m in months}, text))
    return rules


def carriers(book, original, year, last):
    output = []
    totals = defaultdict(lambda: [0] * 12)
    checks = 0
    all_notes = []
    for sheet, metric in [("PAXREG", "passengers"), ("VLOSREG", "flights_as_reported")]:
        rows = list(book[sheet].values)
        if not any(row[0] == SOURCE_NOTE for row in rows):
            raise ValueError("AFAC airline-provided source note missing")
        if rows[0][13] != year:
            raise ValueError("AFAC carrier workbook year differs")
        expected_metric = (
            "TRÁFICO DE PASAJEROS / PASSENGER TRAFFIC" if sheet == "PAXREG" else "VUELOS / FLIGHTS"
        )
        if expected_metric not in rows[2]:
            raise ValueError("AFAC carrier metric header changed")
        if "ESTADÍSTICA POR EMPRESA / AIR CARRIER STATISTICS" not in rows[1]:
            raise ValueError("AFAC carrier report identity changed")
        rules = footnotes(rows, year)
        all_notes.extend(note for _, _, note in rules)
        matched_notes = set()
        blocks = []
        for index, row in enumerate(rows):
            if isinstance(row[0], str) and row[0].startswith("EMPRESAS "):
                block = (
                    "national"
                    if row[0].startswith("EMPRESAS NACIONALES /")
                    else "foreign"
                    if row[0].startswith("EMPRESAS EXTRANJERAS /")
                    else None
                )
                service = rows[index + 1][0]
                market = (
                    "domestic"
                    if service == "EN SERVICIO REGULAR NACIONAL / SCHEDULED DOMESTIC SERVICE"
                    else "international"
                    if service == "EN SERVICIO REGULAR INTERNACIONAL / SCHEDULED INTERNATIONAL SERVICE"
                    else None
                )
                if block is None or market is None:
                    raise ValueError("AFAC carrier block/service changed")
                blocks.append((block, market, index))
        if [(b, m) for b, m, _ in blocks] != [
            ("national", "domestic"),
            ("national", "international"),
            ("foreign", "international"),
        ]:
            raise ValueError("AFAC carrier block domain changed")
        for block, market, start in blocks:
            headers = [
                i
                for i in range(start + 2, min(start + 8, len(rows)))
                if folded(rows[i][0]).startswith("EMPRESAAIRCARRIER")
            ]
            if (
                len(headers) != 1
                or list(rows[headers[0]][1:13]) != MONTH_HEADERS
                or rows[headers[0]][13] != "Total/Total"
            ):
                raise ValueError("AFAC carrier month/header layout changed")
            sums = [0] * 12
            seen = set()
            closed = False
            for index in range(headers[0] + 1, len(rows)):
                row = rows[index]
                name = row[0]
                if name is None:
                    continue
                name = str(name)
                if folded(name) == "TOTAL":
                    total = values(row, 1, last)
                    if total != sums:
                        raise ValueError("AFAC carrier block total does not reconcile")
                    totals[(market, metric)] = [
                        a + b for a, b in zip(totals[(market, metric)], sums, strict=True)
                    ]
                    checks += 12
                    closed = True
                    break
                if name.startswith("Total "):
                    continue  # Regional subtotals must never duplicate carrier cells.
                if name.startswith(("EMPRESAS", "EN SERVICIO", "FUENTE:", "*")) or name in seen:
                    raise ValueError("AFAC carrier block unclosed/duplicate")
                marker = re.search(r"\*+$", name)
                applicable_rules = [
                    (fragment, months, note)
                    for fragment, months, note in rules
                    if fragment in folded(name) and marker and marker[0] == re.match(r"\*+", note)[0]
                ]
                if bool(marker) != bool(applicable_rules):
                    raise ValueError("AFAC estimated carrier marker lacks matching source note")
                matched_notes.update(note for _, _, note in applicable_rules)
                seen.add(name)
                observed = values(row, 1, last)
                sums = [a + b for a, b in zip(sums, observed, strict=True)]
                for m, value in enumerate(observed[:last], 1):
                    matching = [
                        note for fragment, months, note in rules if fragment in folded(name) and m in months
                    ]
                    output.append(
                        observation(
                            original,
                            year,
                            m,
                            metric,
                            value,
                            f"{sheet}!R{index + 1}C{m + 1}",
                            scope="reporting_company_no_city_pair",
                            market=market,
                            carrier=name,
                            block=block,
                            notes=" | ".join(matching) or None,
                            estimated=bool(matching),
                        )
                    )
            if not closed or not seen:
                raise ValueError("AFAC carrier block total missing")
        if matched_notes != {note for _, _, note in rules} or any(
            max(months) > last for _, months, _ in rules
        ):
            raise ValueError("AFAC source estimate note lacks matching current-edition carrier/month")
    return output, totals, checks, sorted(set(all_notes))


def parse(inputs, period):
    if not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("AFAC margins require explicit report month")
    year, last = int(period[:4]), int(period[-2:])
    route_bytes, route_original = inputs["routes"]
    carrier_bytes, carrier_original = inputs["carriers"]
    with closing(load(route_bytes)) as route_book, closing(load(carrier_bytes)) as carrier_book:
        summary = list(carrier_book["Resumen"].values)
        captions = {v for row in summary for v in row if isinstance(v, str) and v.startswith("Acumulado\n")}
        if summary[0][15] != year or captions != {f"Acumulado\nene-{MONTHS[last - 1].split('/')[0].lower()}"}:
            raise ValueError("Carrier cumulative edition month/year not verified in content")
        route_rows, route_totals, route_checks = routes(route_book, route_original, year, last)
        carrier_rows, carrier_totals, carrier_checks, notes = carriers(
            carrier_book, carrier_original, year, last
        )
    reconciliations = []
    for key in sorted(route_totals):
        if route_totals[key] != carrier_totals[key]:
            raise ValueError(f"AFAC same-edition route/carrier totals disagree: {key}")
        for m in range(1, last + 1):
            reconciliations.append(
                dict(
                    market=key[0],
                    metric_key=key[1],
                    period_id=f"{year}M{m:02d}",
                    route_total=route_totals[key][m - 1],
                    carrier_total=carrier_totals[key][m - 1],
                    difference=0,
                )
            )
    frame = pd.DataFrame(route_rows + carrier_rows)
    frame["source_cell_estimated"] = pd.array(frame.source_cell_estimated, dtype="boolean")
    if frame.empty or frame.duplicated(GRAIN).any():
        raise ValueError("Empty/duplicate AFAC margin grain")
    return frame, dict(
        rows=len(frame),
        report_period=period,
        months_validated=sorted(frame.period_id.unique()),
        source_total_crosschecks=route_checks + carrier_checks,
        reconciliations=reconciliations,
        route_rows=len(route_rows),
        carrier_rows=len(carrier_rows),
        source_estimated_carrier_cells=int(frame.source_cell_estimated.eq(True).sum()),
        source_estimate_notes=notes,
        route_cell_estimation_status="not_specified_by_city_pair_source",
        future_template_months_imported=0,
        published_at=None,
        release_lag_days=None,
        scope="same_edition_regular_city_pair_and_reporting_company_margins_not_company_by_route",
        estimator_executed=False,
        zero_semantics="source_numeric_zero_only",
    )
