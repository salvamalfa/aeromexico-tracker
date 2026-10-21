"""Viva historical traffic source units and policy-bound monthly PDF selection.

The reviewed November 2021 layout is intentionally distinct from the unread
2026 edition. A historical replay never certifies current source availability.
"""

from __future__ import annotations

import hashlib
import io
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from urllib.parse import urljoin

import pandas as pd
from bs4 import BeautifulSoup
from pypdf import PdfReader

from src.source_updates.catalog import load_catalog
from src.source_updates.checks import period_end
from src.source_updates.collection import validate_url

VERSION = "viva_traffic_reviewed_2021m11_v1"
TABLE = "fact_viva_monthly_source_metrics"
GRAIN = ["period_id", "metric_key", "definition"]
MONTHS = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
NUMBER = r"(?:0|[1-9]\d{0,2}(?:,\d{3})+|[1-9]\d*)(?:\.\d+)?"
METRICS = [
    ("Pasajeros", "passengers_booked", "count", "booked_for_report_month_not_necessarily_flown"),
    ("Factor de Ocupación (RPK/ASK)", "load_factor_reserved", "percent", "reported_reserved_seats_share"),
    ("RPK's (millones)", "rpk", "million passenger-km", "reported_revenue_passenger_kilometers"),
    ("ASK's (millones)", "ask", "million seat-km", "reported_available_seat_kilometers"),
]


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
    url = candidates.pop()
    validate_url(url, load_catalog()["viva_ir"]["allowed_hosts"])
    return {
        "version": 1,
        "discovery": {"catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(), "period": period},
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
        for index, observed in [(0, "2021M11"), (1, "2020M11"), (3, "2019M11")]:
            token = tokens[index]
            records.append(
                {
                    "period_id": observed,
                    "period_type": "month",
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
                    "published_date": published,
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
        "published_date": published.isoformat(),
        "release_lag_days": (published - period_end(period)).days,
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
        "agent_eligible": False,
        "activation": "none",
    }


def validate(frame: pd.DataFrame) -> None:
    expected = {
        (period, metric, definition)
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


def parse(inputs: dict, period: str) -> tuple[pd.DataFrame, dict]:
    content, original = inputs["pdf"]
    if not content.startswith(b"%PDF-") or len(content) > 2_000_000:
        raise ValueError("Expected a bounded original Viva traffic PDF")
    pdf = PdfReader(io.BytesIO(content))
    if pdf.is_encrypted or len(pdf.pages) != 1:
        raise ValueError("Viva traffic page/encryption contract changed")
    return texts([page.extract_text() or "" for page in pdf.pages], period, original)
