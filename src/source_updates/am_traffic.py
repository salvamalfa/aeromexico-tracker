"""Source-faithful monthly Aeromexico IR traffic PDF selection and extraction."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
import hashlib
import io
from pathlib import Path
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import pandas as pd
from pypdf import PdfReader

from src.parse.sec.traffic_report import MONTHS, detect_traffic_period
from src.source_updates.catalog import load_catalog
from src.source_updates.checks import period_end
from src.source_updates.collection import validate_url
from src.transform.silver_contracts import validate_silver_table


ENTRY = "https://ir.aeromexico.com/news-events/traffic-reports"
VERSION = "am_ir_monthly_pdf_v1"
METRICS = {
    "Passengers": ("passengers", "thousands", Decimal(1000), "count", "itinerary_and_charter"),
    "ASMs": ("asm_total", "millions", Decimal(1000000), "miles", "itinerary_and_charter"),
    "RPMs": ("rpm_total", "millions", Decimal(1000000), "miles", "itinerary_and_charter"),
    "Load Factor": ("load_factor_total", "percent", Decimal("0.01"), "fraction", "itinerary_only"),
}
NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"


def select(catalog: Path, period: str) -> dict:
    if not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("Select one explicit monthly period")
    found = set()
    for anchor in BeautifulSoup(catalog.read_bytes(), "html.parser").select("a[href]"):
        title = anchor.get_text(" ", strip=True)
        try:
            observed = detect_traffic_period(title)
        except ValueError:
            continue
        if observed == period and re.search(r"Aerom[eé]xico", title, re.I):
            found.add(urljoin(ENTRY, anchor["href"]))
    if len(found) != 1:
        raise ValueError("Monthly Aeromexico IR report absent or ambiguous in the preserved catalogue")
    url = found.pop()
    validate_url(url, load_catalog()["aeromexico_ir"]["allowed_hosts"])
    return {
        "version": 1,
        "discovery": {"catalog_sha256": hashlib.sha256(catalog.read_bytes()).hexdigest(), "period": period},
        "items": [
            {
                "id": f"am-traffic-{period}",
                "product": "am_traffic_ir",
                "source_system": "aeromexico_ir",
                "entity": "am_traffic_ir",
                "period": period,
                "purpose": "data",
                "url": url,
                "extension": "pdf",
                "mode": "get",
                "relative_dir": f"aeromexico_ir/traffic/{period}",
            }
        ],
    }


def pdf_text(content: bytes) -> str:
    if len(content) > 2_000_000 or not content.startswith(b"%PDF-"):
        raise ValueError("Expected a bounded original traffic PDF")
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted or not 1 <= len(reader.pages) <= 10:
        raise ValueError("Unverified traffic PDF layout or encryption")
    # Plain mode preserves this PDF's table; layout mode silently omits it.
    return "\n\f\n".join(page.extract_text() or "" for page in reader.pages)


def parse(text: str, period: str, original: dict) -> tuple[pd.DataFrame, dict]:
    actual = detect_traffic_period(text)
    if actual != period or not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("Requested month does not match the traffic PDF title")
    year, month = int(period[:4]), int(period[-2:])
    compact = re.sub(r"\s+", " ", text)
    month_name = list(MONTHS)[month - 1].title()
    if not re.search(rf"Aerom[eé]xico {month_name} {year} Traffic Results", compact) or not re.search(
        r"Grupo Aerom[eé]xico S\.A\.B\. de C\.V\.", compact
    ):
        raise ValueError("Traffic PDF does not establish Grupo Aeromexico identity")
    if f"{year} {year - 1} Var. {year} {year - 1} Var." not in compact:
        raise ValueError("Unverified current/prior and cumulative traffic column order")
    if f"{month_name} Cumulative to {month_name}" not in compact:
        raise ValueError("Monthly and year-to-date columns must be distinguished")
    required = [
        "itinerary + charter, thousands",
        "itinerary + charter, millions",
        "itinerary, %",
        "not been audited",
        "Figures may not sum to total due to rounding",
    ]
    if any(token not in compact for token in required):
        raise ValueError("Traffic units, service basis, audit status or rounding note not established")
    stamp = re.search(r"Mexico City, Mexico, ([A-Za-z]+ \d{1,2}, 20\d{2})", compact)
    if stamp is None:
        raise ValueError("Official traffic publication date missing")
    published = datetime.strptime(stamp[1], "%B %d, %Y").date()
    if published <= period_end(period):
        raise ValueError("Publication does not follow the completed observation month")
    grid, section, page, header_pp = {}, None, 1, False
    header_seen, in_table = False, False
    for line in text.split("\n"):
        if line == "\f":
            page += 1
        normalized_line = " ".join(line.split())
        if normalized_line == f"{year} {year - 1} Var. {year} {year - 1} Var.":
            if header_seen:
                raise ValueError("Ambiguous repeated traffic column header")
            header_seen, in_table = True, True
            continue
        if normalized_line == f"{month_name} Cumulative to {month_name}":
            in_table = False
        if not in_table:
            continue
        standalone = re.fullmatch(
            r"\s*(Passengers|ASMs|RPMs|Load Factor)\s+\((itinerary(?: \+ charter)?, (?:thousands|millions|%))\)(\s+p\.p\.\s+p\.p\.)?\s*",
            line,
        )
        if standalone:
            section = standalone[1]
            expected_basis = {
                "Passengers": "itinerary + charter, thousands",
                "ASMs": "itinerary + charter, millions",
                "RPMs": "itinerary + charter, millions",
                "Load Factor": "itinerary, %",
            }[section]
            if standalone[2] != expected_basis or (standalone[3] and section != "Load Factor"):
                raise ValueError("Unverified traffic metric heading units")
            header_pp = bool(standalone[3])
            continue
        match = re.fullmatch(
            r"\s*(?:(Passengers|ASMs|RPMs|Load Factor)\s+)?(Domestic|International|Total)\s+(.+?)\s*", line
        )
        if not match:
            continue
        if match[1]:
            section, header_pp = match[1], False
        if section not in METRICS or (section, match[2].lower()) in grid:
            raise ValueError("Duplicate or unclassified corporate traffic row")
        lf = section == "Load Factor"
        value = NUMBER + ("%" if lf else "")
        delta = (
            (r"[+-]?\d+(?:\.\d+)?" if header_pp else r"[+-]?\d+(?:\.\d+)?\s*p\.p\.")
            if lf
            else r"[+-]?\d+(?:\.\d+)?%"
        )
        pattern = rf"({value})\s+({value})\s+({delta})\s+({value})\s+({value})\s+({delta})"
        cells = re.fullmatch(pattern, match[3])
        if cells is None:
            raise ValueError("Incomplete or unknown six-column traffic row; no missing-value coercion")
        tokens = cells.groups()
        values = [Decimal(tokens[i].replace(",", "").rstrip("%")) for i in (0, 1, 3, 4)]
        if any(v < 0 or (lf and v > 100) for v in values) or (not lf and any(v != int(v) for v in values)):
            raise ValueError("Traffic values outside the verified published units")
        grid[(section, match[2].lower())] = (tokens, values, line.strip(), page)
    expected = {
        (section, segment) for section in METRICS for segment in ("domestic", "international", "total")
    }
    if set(grid) != expected:
        raise ValueError("Incomplete traffic grid: require four metrics and all three segments")
    for section in METRICS:
        for col in range(4):
            d, i, total = [
                grid[(section, segment)][1][col] for segment in ("domestic", "international", "total")
            ]
            if section == "Load Factor":
                if not min(d, i) - Decimal("0.1") <= total <= max(d, i) + Decimal("0.1"):
                    raise ValueError("Total reported load factor outside component range")
            elif abs(d + i - total) > Decimal("1.5"):
                raise ValueError(
                    "Domestic/international traffic does not reconcile within published rounding"
                )
    records = []
    for (section, segment), (tokens, values, excerpt, source_page) in grid.items():
        metric, unit, scale, normalized, service = METRICS[section]
        for offset in (0, 1):
            observed = f"{year - offset}M{month:02d}"
            records.append(
                {
                    "carrier_key": "AEROMEXICO",
                    "accession_number": f"IR-{period}",
                    "period_id": observed,
                    "period_type": "month",
                    "period_start_date": date(year - offset, month, 1),
                    "period_end_date": period_end(observed),
                    "calendar_period_id": observed,
                    "fiscal_period_id": observed,
                    "metric_key": metric,
                    "metric_label_raw": section,
                    "segment": segment,
                    "value_raw": float(values[offset]),
                    "source_value": tokens[offset],
                    "unit_raw": unit,
                    "scale_multiplier": float(scale),
                    "value_normalized": float(values[offset] * scale),
                    "unit_normalized": normalized,
                    "service_scope": service,
                    "reporting_status": "unaudited",
                    "is_preliminary": False,
                    "is_yoy_comparison": bool(offset),
                    "reported_in_period": period,
                    "source_excerpt": excerpt,
                    "source_page": source_page,
                    "published_date": published,
                    "extraction_method": "pdf_plain_text_monthly_columns_only",
                    "extraction_confidence": 0.99,
                    "source_system": "aeromexico_ir",
                    "source_file": original["source_file"],
                    "source_hash": original["sha256"],
                    "ingested_at": pd.Timestamp(original["downloaded_at"]),
                    "parser_version": VERSION,
                }
            )
    frame = pd.DataFrame(records).sort_values(["period_id", "metric_key", "segment"]).reset_index(drop=True)
    validate(frame)
    return frame, {
        "published_date": published.isoformat(),
        "publication_time": None,
        "first_available_at": None,
        "release_lag_days": (published - period_end(period)).days,
        "rows": len(frame),
        "observation_months": sorted(frame.period_id.unique()),
        "monthly_rows": 12,
        "comparative_rows": 12,
        "cumulative_rows_imported": 0,
        "rounding_policy": "sum of rounded components within 1.5 published units",
        "load_factor_policy": "reported itinerary-only; not derived from itinerary-plus-charter RPM/ASM",
    }


def validate(frame: pd.DataFrame) -> None:
    # Reuse the established operating-observation grain/direct-artifact contract,
    # plus this product's explicit domain. The candidate table is not a SEC filing.
    validate_silver_table("sec_operating_metrics", frame)
    if len(frame) != 24 or set(frame.source_system) != {"aeromexico_ir"}:
        raise ValueError("Expected 24 source-faithful IR monthly/comparative observations")
    for section, (metric, unit, scale, normalized, service) in METRICS.items():
        rows = frame.loc[frame.metric_key.eq(metric)]
        if len(rows) != 6 or set(rows.segment) != {"domestic", "international", "total"}:
            raise ValueError("Incomplete metric or segment coverage")
        if (
            set(rows.unit_raw) != {unit}
            or set(rows.unit_normalized) != {normalized}
            or set(rows.service_scope) != {service}
        ):
            raise ValueError("Corporate traffic units or service scope changed")
        scaled = rows.value_raw.map(lambda raw: float(Decimal(str(raw)) * scale))
        if not rows.scale_multiplier.eq(float(scale)).all() or not rows.value_normalized.eq(scaled).all():
            raise ValueError("Corporate traffic scaling changed")
