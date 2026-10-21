"""Viva monthly traffic in native units, with distinct 2021 and 2026 layouts."""

from __future__ import annotations

import hashlib
import io
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import pandas as pd
from bs4 import BeautifulSoup
from pypdf import PdfReader

from src.source_updates.calendar import local_time
from src.source_updates.catalog import load_catalog
from src.source_updates.checks import period_end
from src.source_updates.collection import validate_url

VERSION = "viva_traffic_native_monthly_v3"
TABLE = "fact_viva_monthly_source_metrics"
GRAIN = ["period_id", "metric_key", "segment", "definition"]
MONTHS = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
NUMBER = r"(?:0|[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)(?:\.\d+)?"
METRICS = [
    ("Pasajeros", "passengers_booked", "count", "booked_for_report_month_not_necessarily_flown"),
    ("Factor de Ocupación (RPK/ASK)", "load_factor_reserved", "percent", "reported_reserved_seats_share"),
    ("RPK's (millones)", "rpk", "million passenger-km", "reported_revenue_passenger_kilometers"),
    ("ASK's (millones)", "ask", "million seat-km", "reported_available_seat_kilometers"),
]
CURRENT_METRICS = [
    (
        "Pasajeros",
        "passengers_booked",
        "thousand booked passengers",
        "booked_not_necessarily_flown_itinerary_and_charter",
    ),
    ("Factor de Ocupación", "load_factor_itinerary", "percent", "reported_itinerary_RPM_div_ASM"),
    ("RPMs", "rpm", "million passenger-miles", "reported_itinerary_and_charter_revenue_passenger_miles"),
    ("ASMs", "asm", "million seat-miles", "reported_itinerary_and_charter_available_seat_miles"),
]
ABBREVIATIONS = "Ene Feb Mar Abr May Jun Jul Ago Sep Oct Nov Dic".split()


def select(catalog: Path, period: str, *, catalog_url: str) -> dict:
    """Use a real unique traffic link; validate source policy before acquisition."""
    if not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("Viva traffic selection requires one explicit month")
    year, month = int(period[:4]), int(period[-2:])
    candidates = {
        urljoin(catalog_url, a["href"])
        for a in BeautifulSoup(catalog.read_bytes(), "html.parser").select("a[href]")
        if re.search(rf"trafico-{MONTHS[month - 1]}-{year}\.pdf$", a["href"], re.I)
    }
    if len(candidates) != 1:
        raise ValueError("Viva month absent or ambiguous in the actual preserved catalogue")
    selection = selection_for_url(candidates.pop(), period)
    selection["discovery"] = {
        "catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(),
        "period": period,
    }
    return selection


def selection_for_url(url: str, period: str) -> dict:
    """Explicit official PDF selection; a filename never verifies its period."""
    if not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("Viva traffic selection requires one explicit month")
    validate_url(url, load_catalog()["viva_ir"]["allowed_hosts"])
    if not urlsplit(url).path.lower().endswith(".pdf"):
        raise ValueError("Select the actual official PDF URL, not a portal or invented filename")
    return {
        "version": 1,
        "discovery": {
            "mode": "explicit_official_pdf_selection",
            "period": period,
            "content_period_verification": "required_before_certification",
        },
        "items": [
            {
                "id": "viva-traffic-" + period,
                "product": "viva_traffic",
                "source_system": "viva_ir",
                "entity": "viva_traffic",
                "period": period,
                "purpose": "data",
                "url": url,
                "extension": "pdf",
                "mode": "get",
                "relative_dir": "peers/viva_aerobus/traffic/" + period,
            }
        ],
    }


def numeric(token: str) -> Decimal:
    if not re.fullmatch(NUMBER, token):
        raise ValueError("Missing or noncanonical Viva numeric token; never fill with zero")
    return Decimal(token.replace(",", ""))


def texts(pages: list[str], period: str, original: dict) -> tuple[pd.DataFrame, dict]:
    if period != "2021M11":
        raise ValueError(
            "Only reviewed Viva 2021M11 traffic layout is supported; current edition requires its original"
        )
    if len(pages) != 1 or original.get("source_system") != "viva_ir":
        raise ValueError("Require the one-page historical Viva original with its actual source alias")
    text = " ".join(pages[0].split())
    required = [
        "Cifras Mensuales de Pasajeros: noviembre 2021",
        "VIVA AEROBUS REPORTA RESULTADOS MENSUALES DE TRÁFICO",
        "Ciudad de México, 07 de diciembre 2021",
        "Concepto Mensual Year to Date (enero – noviembre)",
        "Noviembre 2021 Noviembre 2020 VAR Noviembre 2019 VAR Octubre 2021 VAR 2021 2020 VAR 2019 VAR",
        "Pasajeros: Personas que adquirieron su boleto para volar en el mes del reporte "
        "indistintamente si efectúan o no su vuelo",
        "Factor de ocupación: Porcentaje de asientos reservados en una aeronave o flota "
        "en un determinado periodo de tiempo",
        "ASK (Available Seat Kilometers / Asientos disponibles por kilómetro)",
        "RPK (Revenue Passenger Kilometers / Ingresos Pasajero Kilómetro)",
    ]
    if any(text.count(token) != 1 for token in required):
        raise ValueError(
            "Viva identity/month/column order/units/booked-passenger glossary not established uniquely"
        )
    published = date(2021, 12, 7)
    if local_time(original["downloaded_at"]).date() < published:
        raise ValueError("Viva document date must precede its source capture date in Mexico")
    grid, records = {}, []
    for pos, (label, metric, unit, definition) in enumerate(METRICS):
        start = text.index(label + " ", text.index("INFORMACIÓN MENSUAL"))
        following = METRICS[pos + 1][0] if pos + 1 < len(METRICS) else "*NOTA:"
        end = text.index(following, start + len(label))
        if text.count(label + " ", text.index("INFORMACIÓN MENSUAL"), text.index("*NOTA:")) != 1:
            raise ValueError("Duplicate Viva native metric row")
        row = text[start:end].strip()
        values_text = row[len(label) :].strip()
        percent = metric == "load_factor_reserved"
        value = NUMBER + ("%" if percent else "")
        delta = r"[+-]?\d+(?:\.\d+)?\s*pp" if percent else r"[+-]?\d+(?:\.\d+)?%"
        pattern = (
            rf"({value})\s+({value})\s+({delta})\s+({value})\s+({delta})\s+({value})\s+({delta})"
            rf"\s+({value})\s+({value})\s+({delta})\s+({value})\s+({delta})"
        )
        match = re.fullmatch(pattern, values_text)
        if match is None:
            raise ValueError("Viva table has missing, extra or changed monthly/YTD cells")
        tokens = match.groups()
        all_values = [numeric(tokens[index].rstrip("%")) for index in (0, 1, 3, 5, 7, 8, 10)]
        if percent and any(value > 100 for value in all_values):
            raise ValueError("Viva reported reserved-seat factor outside percent domain")
        if metric == "passengers_booked" and (
            any(value != int(value) for value in all_values)
            or any("." in tokens[index] for index in (0, 1, 3, 5, 7, 8, 10))
        ):
            raise ValueError("Viva passenger counts must remain exact integers")
        grid[metric] = all_values
        if not percent and any(
            all_values[monthly] > all_values[ytd] for monthly, ytd in ((0, 4), (1, 5), (2, 6))
        ):
            raise ValueError("Viva monthly value exceeds same-year cumulative YTD in native units")
        for index, observed in [(0, "2021M11"), (1, "2020M11"), (3, "2019M11")]:
            token = tokens[index]
            records.append(
                {
                    "period_id": observed,
                    "period_type": "month",
                    "segment": "total",
                    "reported_in_period": period,
                    "entity_as_reported": (
                        "Viva Aerobus brand; legal issuer/operator not established by this release"
                    ),
                    "carrier_key": "VIVA_AEROBUS",
                    "metric_key": metric,
                    "value": float(numeric(token.rstrip("%"))),
                    "unit": unit,
                    "definition": definition,
                    "source_value": token,
                    "source_label": label,
                    "source_locator": "page:1;monthly-table;" + label + ";" + observed,
                    "source_excerpt": row,
                    "source_page": 1,
                    "document_date": published,
                    "source_system": original["source_system"],
                    "source_file": original["source_file"],
                    "source_hash": original["sha256"],
                    "ingested_at": pd.Timestamp(original["downloaded_at"]),
                    "parser_version": VERSION,
                }
            )
    for rpk, ask in zip(grid["rpk"], grid["ask"], strict=True):
        if rpk > ask:
            raise ValueError("Viva reported RPK exceeds ASK; preserve source for review")
    frame = pd.DataFrame(records).sort_values(GRAIN).reset_index(drop=True)
    validate(frame)
    return frame, {
        "rows": len(frame),
        "monthly_rows": 4,
        "comparison_rows": 8,
        "observation_months": sorted(frame.period_id.unique()),
        "latest_validated_period": period,
        "document_date": published.isoformat(),
        "published_date": None,
        "reported_document_lag_days": (published - period_end(period)).days,
        "release_lag_days": None,
        "first_available_at": None,
        "publication_time": None,
        "reporting_status": "not_stated_in_this_release",
        "excluded_columns": ["previous_month", "year_to_date", "reported_changes"],
        "passenger_definition": "booked_for_report_month_not_necessarily_flown",
        "load_factor_policy": (
            "source row labelled RPK/ASK, glossary defines reserved seats; "
            "no recalculation or claim of transported passengers"
        ),
        "entity_attribution": "brand_only_no_legal_issuer_or_operator_mapping",
        "current_source_availability": "not_certified_by_historical_layout",
        "scope": "reviewed_2021M11_snapshot_and_2019_2020_comparatives_not_current_availability",
        "agent_eligible": False,
        "activation": "none",
    }


def validate(frame: pd.DataFrame) -> None:
    if set(frame.reported_in_period) != {"2021M11"}:
        validate_current(frame)
        return
    expected = {
        (period, metric, "total", definition)
        for period in ("2021M11", "2020M11", "2019M11")
        for _, metric, _, definition in METRICS
    }
    if len(frame) != 12 or frame[GRAIN].isna().any().any() or frame.duplicated(GRAIN).any():
        raise ValueError("Viva native monthly grain incomplete or duplicated")
    if set(frame[GRAIN].itertuples(index=False, name=None)) != expected:
        raise ValueError("Viva native metric/definition/month domain changed")
    if frame.value.isna().any() or not frame.value.map(lambda value: 0 <= value < 2**53).all():
        raise ValueError("Viva values must be finite, nonnegative and representable")
    for _, metric, unit, _ in METRICS:
        if not frame.loc[frame.metric_key.eq(metric), "unit"].eq(unit).all():
            raise ValueError("Viva source units changed; no implicit ASM/ASK conversion")
    if not frame.loc[frame.metric_key.eq("load_factor_reserved"), "value"].le(100).all():
        raise ValueError("Viva reserved-seat factor outside percent domain")


def parse(inputs: dict, period: str) -> tuple[pd.DataFrame, dict]:
    content, original = inputs["pdf"]
    if not content.startswith(b"%PDF-") or len(content) > 2_000_000:
        raise ValueError("Expected a bounded original Viva traffic PDF")
    pdf = PdfReader(io.BytesIO(content))
    expected_pages = 1 if period == "2021M11" else 2
    if pdf.is_encrypted or len(pdf.pages) != expected_pages:
        raise ValueError("Viva traffic page/encryption contract changed")
    pages = [page.extract_text() or "" for page in pdf.pages]
    return texts(pages, period, original) if period == "2021M11" else current_texts(pages, period, original)


def current_texts(pages: list[str], period: str, original: dict) -> tuple[pd.DataFrame, dict]:
    """Check monthly/current-prior columns, glossary and all twelve native rows."""
    if not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period) or int(period[:4]) < 2022:
        raise ValueError("Select an explicit month compatible with the current Viva traffic layout")
    if len(pages) != 2 or original.get("source_system") != "viva_ir":
        raise ValueError("Require the two-page Viva traffic original and its actual source alias")
    year, month = int(period[:4]), int(period[-2:])
    name, abbr = MONTHS[month - 1], ABBREVIATIONS[month - 1]
    first, glossary = [" ".join(page.split()) for page in pages]
    required = [
        f"Viva anunció hoy sus resultados preliminares de tráfico correspondientes a {name} de {year}",
        f"Reporte de Tráfico | {name.title()} {year}",
        f"Cifras mensuales Cifras acumuladas (Ene-{abbr})",
        f"{abbr} {year} {abbr} {year - 1} Var% {year} {year - 1} Var%",
        "asientos por milla disponibles (ASMs)",
    ]
    required_glossary = [
        "Glosario",
        "Pasajeros: Clientes que adquirieron su boleto para volar en el mes del reporte "
        "indistintamente si efectúan o no su vuelo.",
        "ASMs (por sus siglas en inglés)",
        "capacidad de asientos de la aeronave multiplicada por el número de millas.",
        "se calcula dividiendo los pasajeros pago millas (RPMs) de itinerario "
        "por asientos disponibles por millas (ASMs) de itinerario.",
        "RPMs: “Pasajeros pago millas”",
        "Viva es una aerolínea mexicana de ultra bajo costo",
    ]
    if any(first.count(value) != 1 for value in required) or any(
        glossary.count(value) != 1 for value in required_glossary
    ):
        raise ValueError(
            "Viva month/entity/preliminary/column order/mile units/glossary not established uniquely"
        )
    dates = re.findall(r"Ciudad de México, (\d{1,2}) de ([a-z]+) de (20\d{2})", first)
    if len(dates) != 1 or dates[0][1] not in MONTHS:
        raise ValueError("Viva source document dateline absent or ambiguous")
    published = date(int(dates[0][2]), MONTHS.index(dates[0][1]) + 1, int(dates[0][0]))
    if published <= period_end(period) or local_time(original["downloaded_at"]).date() < published:
        raise ValueError("Viva document date must follow the month and precede its source capture")
    header = required[3]
    table = first.split(header, 1)[1].split(required[1], 1)[0].strip()
    headings = [
        "Pasajeros (itinerario & chárter, miles)",
        "Factor de Ocupación (itinerario, RPM/ASM)",
        "RPMs (itinerario & chárter, millones)",
        "ASMs (itinerario & chárter, millones)",
    ]
    if any(table.count(heading) != 1 for heading in headings):
        raise ValueError("Viva monthly metric headings changed or duplicated")
    records, grid = [], {}
    for position, (label, metric, unit, definition) in enumerate(CURRENT_METRICS):
        heading = headings[position]
        section = table.split(heading, 1)[1]
        if position + 1 < len(headings):
            section = section.split(headings[position + 1], 1)[0]
        percent = metric == "load_factor_itinerary"
        number = NUMBER + ("%" if percent else "")
        delta = r"[+-]?\d+(?:\.\d+)?\s*pp" if percent else r"[+-]?\d+(?:\.\d+)?%"
        six = rf"({number})\s+({number})\s+({delta})\s+({number})\s+({number})\s+({delta})"
        match = re.fullmatch(rf"\s*{six}\s+Nacional\s+{six}\s+Internacional\s+{six}\s*", section)
        if match is None:
            raise ValueError("Viva requires exactly three six-cell monthly/YTD segment rows per metric")
        native = {}
        for segment, offset in [("total", 0), ("domestic", 6), ("international", 12)]:
            tokens = match.groups()[offset : offset + 6]
            values = [numeric(tokens[index].rstrip("%")) for index in (0, 1, 3, 4)]
            if percent and any(value > 100 for value in values):
                raise ValueError("Viva itinerary load factor outside percent domain")
            if not percent and any("." in tokens[index] for index in (0, 1, 3, 4)):
                raise ValueError("Viva current table uses rounded integer thousands/millions; format changed")
            native[segment] = values
            if not percent and (values[0] > values[2] or values[1] > values[3]):
                raise ValueError("Viva monthly value exceeds same-year cumulative YTD in native units")
            for index, observed in [(0, period), (1, f"{year - 1}M{month:02d}")]:
                records.append(
                    {
                        "period_id": observed,
                        "period_type": "month",
                        "segment": segment,
                        "reported_in_period": period,
                        "entity_as_reported": (
                            "Viva brand; legal issuer/operator not established by this release"
                        ),
                        "carrier_key": "VIVA_AEROBUS",
                        "metric_key": metric,
                        "value": float(numeric(tokens[index].rstrip("%"))),
                        "unit": unit,
                        "definition": definition,
                        "source_value": tokens[index],
                        "source_label": heading,
                        "source_locator": f"page:1;monthly-table;{label};{segment};{observed}",
                        "source_excerpt": section.strip(),
                        "source_page": 1,
                        "document_date": published,
                        "reporting_status": "preliminary",
                        "is_preliminary": True,
                        "source_system": original["source_system"],
                        "source_file": original["source_file"],
                        "source_hash": original["sha256"],
                        "ingested_at": pd.Timestamp(original["downloaded_at"]),
                        "parser_version": VERSION,
                    }
                )
        for column in range(4):
            domestic, international, total = [
                native[segment][column] for segment in ("domestic", "international", "total")
            ]
            if percent:
                if (
                    not min(domestic, international) - Decimal("0.1")
                    <= total
                    <= max(domestic, international) + Decimal("0.1")
                ):
                    raise ValueError("Viva total itinerary load factor outside component range")
            elif abs(domestic + international - total) > Decimal("1.5"):
                raise ValueError("Viva segment totals do not reconcile within native-unit rounding")
        grid[metric] = native
    for segment in ("total", "domestic", "international"):
        if any(rpm > asm for rpm, asm in zip(grid["rpm"][segment], grid["asm"][segment], strict=True)):
            raise ValueError("Viva RPM exceeds ASM in the same reported universe")
    frame = pd.DataFrame(records).sort_values(GRAIN).reset_index(drop=True)
    validate_current(frame)
    return frame, {
        "rows": len(frame),
        "monthly_rows": 12,
        "comparison_rows": 12,
        "observation_months": sorted(frame.period_id.unique()),
        "latest_validated_period": period,
        "document_date": published.isoformat(),
        "published_date": None,
        "reported_document_lag_days": (published - period_end(period)).days,
        "release_lag_days": None,
        "first_available_at": None,
        "publication_time": None,
        "reporting_status": "preliminary",
        "excluded_columns": ["year_to_date", "reported_changes"],
        "native_reconciliations": 16,
        "rounding_policy": (
            "sum of rounded components within1.5 published thousands/millions; "
            "load factor within component range"
        ),
        "passenger_definition": "booked_for_report_month_not_necessarily_flown_itinerary_and_charter",
        "load_factor_policy": (
            "reported itinerary-only RPM/ASM; other metrics include charter; "
            "no recalculation from a different universe"
        ),
        "entity_attribution": "brand_only_no_legal_issuer_or_operator_mapping",
        "scope": (
            "one_verified_monthly_document_and_its_prior_year_comparative_"
            "not_complete_family_or_latest_catalogue"
        ),
        "agent_eligible": False,
        "activation": "none",
    }


def validate_current(frame: pd.DataFrame) -> None:
    if frame.empty or len(set(frame.reported_in_period)) != 1:
        raise ValueError("Viva monthly candidate requires one source report month")
    period = frame.reported_in_period.iloc[0]
    if not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("Viva source report month is invalid")
    prior = f"{int(period[:4]) - 1}M{period[-2:]}"
    expected = {
        (month, metric, segment, definition)
        for month in (period, prior)
        for _, metric, _, definition in CURRENT_METRICS
        for segment in ("total", "domestic", "international")
    }
    if (
        len(frame) != 24
        or frame[GRAIN].isna().any().any()
        or frame.duplicated(GRAIN).any()
        or set(frame[GRAIN].itertuples(index=False, name=None)) != expected
        or frame.value.isna().any()
        or not frame.value.map(lambda value: 0 <= value < 2**53).all()
        or not frame.period_type.eq("month").all()
        or not frame.source_system.eq("viva_ir").all()
    ):
        raise ValueError("Viva monthly metric/segment/definition/month/value contract changed")
    for _, metric, unit, _ in CURRENT_METRICS:
        if not frame.loc[frame.metric_key.eq(metric), "unit"].eq(unit).all():
            raise ValueError("Viva native units changed; never relabel ASM/RPM miles as ASK/RPK kilometers")
    if (
        not frame.loc[frame.metric_key.eq("load_factor_itinerary"), "value"].le(100).all()
        or not frame.carrier_key.eq("VIVA_AEROBUS").all()
    ):
        raise ValueError("Viva itinerary load-factor/carrier domain changed")
    if not frame.reporting_status.eq("preliminary").all() or not frame.is_preliminary.eq(True).all():
        raise ValueError("Viva preliminary source status lost")
