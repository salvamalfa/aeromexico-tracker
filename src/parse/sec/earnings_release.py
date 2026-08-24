"""Parse quarterly Aeromexico earnings releases from SEC HTML exhibits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
import unicodedata
from typing import Any

from bs4 import BeautifulSoup, Tag
import polars as pl

from src.common.quality import log_issue
from src.config import PATHS
from src.ingest.sec.discover import classify_6k
from src.parse.sec.common import (
    html_text,
    previous_year_period,
    quarter_dates,
    read_bronze_verified,
    write_parquet_atomic,
)
from src.parse.profiles import CarrierProfile


PARSER_VERSION = "sec_earnings_v1.0.0"
QUARTER_TOKEN = re.compile(r"(?P<quarter>[1-4])Q(?P<year>\d{2,4})", re.I)
QUARTER_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4}


@dataclass(frozen=True, slots=True)
class MetricSpec:
    metric_key: str
    label_pattern: str
    table_name: str
    unit_raw: str
    scale_multiplier: float
    unit_normalized: str
    segment: str | None = "total"
    statement_type: str | None = None


OPERATING_SPECS = (
    MetricSpec("asm_total", r"^total asms?\b", "operating", "ASMs (millions)", 1e6, "miles"),
    MetricSpec("rpm_total", r"^total rpms?\b", "operating", "RPMs (millions)", 1e6, "miles"),
    MetricSpec("load_factor_total", r"^load factor on scheduled flights", "operating", "%", 0.01, "fraction"),
    MetricSpec("passengers", r"^passengers\b", "operating", "Passengers ('000)", 1e3, "count"),
    MetricSpec("on_time_departure_pct", r"^on-time departure performance", "operating", "%", 0.01, "fraction"),
    MetricSpec("fuel_liters", r"^total liters of fuel", "operating", "liters ('000)", 1e3, "liters"),
    MetricSpec("yield", r"^yield \(usd cents\)", "operating", "USD cents", 1.0, "usd_cents"),
    MetricSpec("trasm", r"^total revenue\s*/\s*asm", "operating", "USD cents", 1.0, "usd_cents"),
    MetricSpec("prasm", r"^passenger revenue\s*/\s*asm", "operating", "USD cents", 1.0, "usd_cents"),
    MetricSpec("casm", r"^total cost\s*/\s*asm", "operating", "USD cents", 1.0, "usd_cents"),
    MetricSpec("casm_ex_fuel", r"^total cost excluding fuel\s*/\s*asm", "operating", "USD cents", 1.0, "usd_cents"),
    MetricSpec("fleet_size", r"^grupo aeromexico$", "operating", "aircraft", 1.0, "count"),
)

FINANCIAL_SPECS = (
    MetricSpec("total_revenue", r"^total revenue(?: \(usd millions\))?$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("passenger_revenue", r"^(?:passenger revenue|passenger)$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("cargo_revenue", r"^air cargo$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("other_revenue", r"^other$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("adjusted_ebitdar", r"^adjusted ebitdar(?:\s*(?:\(\d+\)|\d+))?(?: \(usd millions\))?$", "financial", "USD millions", 1e6, "usd", None, "non_ifrs"),
    MetricSpec("ebitdar_margin", r"^adjusted ebitdar margin", "financial", "%", 0.01, "fraction", None, "non_ifrs"),
    MetricSpec("jet_fuel_expense", r"^jet-fuel$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("wages_salaries_benefits", r"^wages, salaries and benefits$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("maintenance_expense", r"^maintenance$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("aircraft_communications_traffic_services", r"^aircraft, communications and traffic services$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("passenger_services_expense", r"^passenger services$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("travel_agent_commissions", r"^travel agent commissions$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("selling_administrative_expense", r"^selling and administrative$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("aircraft_leasing_expense", r"^aircraft leasing$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("depreciation_amortization", r"^depreciation and amortization$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("impairment_reversal", r"^impairment \(reversal\)$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("other_income_loss_net", r"^other \(income\) loss, net$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("equity_investees_share", r"^share of gain on equity accounted investees", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("operating_expenses_total", r"^total operating expenses$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("operating_income", r"^total operating income", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("operating_margin", r"^operating margin", "financial", "%", 0.01, "fraction", None, "income_statement"),
    MetricSpec("net_finance_cost", r"^net finance cost$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("income_before_tax", r"^income before income tax$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("income_tax", r"^income tax(?: \(benefit\))?$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
    MetricSpec("net_income", r"^net income (?:\(loss\)|for the period)$", "financial", "USD millions", 1e6, "usd", None, "income_statement"),
)


def specs_from_profile(profile: CarrierProfile) -> tuple[MetricSpec, ...]:
    """Translate a declarative carrier profile into the generic table parser specs."""

    return tuple(
        MetricSpec(
            metric_key=metric.metric_key,
            label_pattern="(?:" + "|".join(metric.patterns) + ")",
            table_name=metric.table_name,
            unit_raw=metric.unit_raw,
            scale_multiplier=metric.scale_multiplier,
            unit_normalized=metric.unit_normalized,
            segment="total" if metric.table_name == "operating" else None,
            statement_type=(
                "income_statement" if metric.table_name == "financial" else None
            ),
        )
        for metric in profile.metric_patterns
    )


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.replace("\xa0", " "))
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", normalized).casefold().strip()


def detect_current_period(text: str) -> str:
    normalized = _normalize(text[:10_000])
    word_pattern = re.compile(
        r"(?:reports?|results)[^.!]{0,100}?"
        r"(first|second|third|fourth) quarter\s+(20\d{2})"
    )
    match = word_pattern.search(normalized)
    if match:
        quarter = QUARTER_WORDS[match.group(1)]
        return f"{match.group(2)}Q{quarter}"
    token_pattern = re.compile(r"\b([1-4])q(\d{2})\b[^.!]{0,60}?results")
    match = token_pattern.search(normalized)
    if match:
        return f"20{match.group(2)}Q{match.group(1)}"
    raise ValueError("Unable to determine the earnings release quarter from its title")


def _period_from_header(value: str) -> str | None:
    match = QUARTER_TOKEN.search(value)
    if not match:
        return None
    year_text = match.group("year")
    year = int(year_text) if len(year_text) == 4 else 2000 + int(year_text)
    return f"{year}Q{int(match.group('quarter'))}"


def _row_cells(row: Tag) -> list[str]:
    cells = [" ".join(cell.stripped_strings) for cell in row.find_all(["td", "th"], recursive=False)]
    return [cell for cell in cells if cell.strip()]


def _numeric_slot(value: str) -> tuple[bool, float | None]:
    cleaned = value.replace("\xa0", " ").strip()
    if cleaned in {"—", "–", "-", "N/A", "n/a"}:
        return True, None
    if not re.match(r"^\(?\s*[-+]?\$?\d", cleaned):
        return False, None
    negative = cleaned.startswith("(")
    match = re.search(r"[-+]?\$?([\d,]+(?:\.\d+)?)", cleaned)
    if not match:
        return False, None
    value_number = float(match.group(1).replace(",", ""))
    return True, -value_number if negative else value_number


def _numeric_values(cells: list[str]) -> list[float | None]:
    values: list[float | None] = []
    for cell in cells[1:]:
        is_slot, value = _numeric_slot(cell)
        if is_slot:
            values.append(value)
    return values


def _quarter_headers(table: Tag) -> list[tuple[str | None, bool, bool]]:
    for row in table.find_all("tr"):
        cells = _row_cells(row)
        periods = [_period_from_header(cell) for cell in cells]
        if sum(period is not None for period in periods) < 2:
            continue
        headers: list[tuple[str | None, bool, bool]] = []
        for cell, period in zip(cells, periods, strict=True):
            normalized = _normalize(cell)
            if period is not None:
                headers.append((period, "normalized" in normalized, False))
            elif "var" in normalized:
                headers.append((None, False, True))
        return headers
    return []


def _select_period_values(
    table: Tag, values: list[float | None], current_period: str
) -> list[tuple[str, float | None]]:
    headers = _quarter_headers(table)
    previous_period = previous_year_period(current_period)
    selected: list[tuple[str, float | None]] = []
    if headers and len(headers) <= len(values):
        for target in (current_period, previous_period):
            for index, (period, is_normalized, is_variance) in enumerate(headers):
                if period != target or is_normalized or is_variance:
                    continue
                value = values[index]
                selected.append((target, value))
                break
        return selected
    # Some 2026 releases use year-only headings for parallel three- and six-month
    # groups. The first two numeric slots are the current and prior-year quarters.
    if values:
        selected.append((current_period, values[0]))
    if len(values) > 1:
        selected.append((previous_period, values[1]))
    return selected


def _find_metric_values(
    soup: BeautifulSoup, spec: MetricSpec, current_period: str
) -> tuple[str, list[tuple[str, float | None]]] | None:
    pattern = re.compile(spec.label_pattern, re.I)
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = _row_cells(row)
            if not cells:
                continue
            label = _normalize(cells[0])
            if not pattern.search(label):
                continue
            values = _numeric_values(cells)
            selected = _select_period_values(table, values, current_period)
            if selected:
                return cells[0], selected
    return None


def _find_company_normalized_values(
    soup: BeautifulSoup, spec: MetricSpec
) -> tuple[str, list[tuple[str, float | None]]] | None:
    pattern = re.compile(spec.label_pattern, re.I)
    for table in soup.find_all("table"):
        headers = _quarter_headers(table)
        if not any(period and is_normalized for period, is_normalized, _ in headers):
            continue
        for row in table.find_all("tr"):
            cells = _row_cells(row)
            if not cells or not pattern.search(_normalize(cells[0])):
                continue
            values = _numeric_values(cells)
            selected = [
                (period, values[index])
                for index, (period, is_normalized, is_variance) in enumerate(headers)
                if period is not None
                and is_normalized
                and not is_variance
                and index < len(values)
            ]
            if selected:
                return cells[0], selected
    return None


def _narrative_overrides(text: str) -> dict[str, float]:
    normalized = text.replace("\xa0", " ")
    overrides: dict[str, float] = {}
    ebitdar = re.search(
        r"Adjusted EBITDAR[^.]{0,100}?totaled\s*\$([\d,.]+)\s*million"
        r"[^.]{0,100}?([\d.]+)%\s*margin",
        normalized,
        re.I,
    )
    if ebitdar:
        overrides["adjusted_ebitdar"] = float(ebitdar.group(1).replace(",", ""))
        overrides["ebitdar_margin"] = float(ebitdar.group(2))
    operating_candidates = []
    for margin_pattern in (
        r"(?:with\s+)?(?:a\s+)?margin\s+of\s+([\d.]+)%",
        r"with\s+(?:a\s+)?([\d.]+)%\s+margin",
        r"representing\s+(?:a\s+)?([\d.]+)%\s+operating margin",
    ):
        match = re.search(
            r"Operating income[^.]{0,100}?(?:totaled|reached|recorded)\s*"
            r"\$([\d,.]+)\s*million[^.]{0,100}?" + margin_pattern,
            normalized,
            re.I,
        )
        if match:
            operating_candidates.append(match)
    operating = min(operating_candidates, key=lambda match: match.start(), default=None)
    if operating:
        overrides["operating_income"] = float(operating.group(1).replace(",", ""))
        overrides["operating_margin"] = float(operating.group(2))
    return overrides


def _base_record(
    *,
    document: dict[str, Any],
    period_id: str,
    metric_key: str,
    segment: str | None,
    value_raw: float | None,
    unit_raw: str,
    scale_multiplier: float,
    unit_normalized: str,
    extraction_method: str,
    extraction_confidence: float,
    metric_label_raw: str,
    is_preliminary: bool,
    carrier_key: str = "AEROMEXICO",
) -> dict[str, object]:
    start_date, end_date = quarter_dates(period_id)
    return {
        "carrier_key": carrier_key,
        "accession_number": document["accession_number"],
        "period_id": period_id,
        "period_type": "quarter",
        "period_start_date": start_date,
        "period_end_date": end_date,
        "metric_key": metric_key,
        "metric_label_raw": metric_label_raw,
        "segment": segment,
        "value_raw": value_raw,
        "unit_raw": unit_raw,
        "scale_multiplier": scale_multiplier,
        "value_normalized": (
            value_raw * scale_multiplier if value_raw is not None else None
        ),
        "unit_normalized": unit_normalized,
        "is_preliminary": is_preliminary,
        "is_yoy_comparison": False,
        "extraction_method": extraction_method,
        "extraction_confidence": extraction_confidence,
        "source_system": "sec_edgar",
        "source_file": document["source_file"],
        "source_hash": document["source_hash"],
        "ingested_at": datetime.fromisoformat(document["ingested_at"]),
        "parser_version": PARSER_VERSION,
    }


def parse_earnings_document(
    document: dict[str, Any], profile: CarrierProfile | None = None
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    content = read_bronze_verified(document["source_file"], document["source_hash"])
    return parse_earnings_content(content, document, profile)


def parse_earnings_content(
    content: bytes,
    document: dict[str, Any],
    profile: CarrierProfile | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Parse verified exhibit bytes; exposed separately for frozen fixtures."""

    soup = BeautifulSoup(content, "lxml")
    text = html_text(content)
    current_period = detect_current_period(text)
    is_preliminary = "unaudited" in text.casefold()
    operating: list[dict[str, object]] = []
    financial: list[dict[str, object]] = []
    specs = (
        specs_from_profile(profile)
        if profile is not None
        else (*OPERATING_SPECS, *FINANCIAL_SPECS)
    )
    carrier_key = profile.carrier_key if profile is not None else "AEROMEXICO"
    for spec in specs:
        found = _find_metric_values(soup, spec, current_period)
        if found is None:
            continue
        label, period_values = found
        for period_id, value in period_values:
            record = _base_record(
                document=document,
                period_id=period_id,
                metric_key=spec.metric_key,
                segment=spec.segment,
                value_raw=value,
                unit_raw=spec.unit_raw,
                scale_multiplier=spec.scale_multiplier,
                unit_normalized=spec.unit_normalized,
                extraction_method="html_table",
                extraction_confidence=0.98,
                metric_label_raw=label,
                is_preliminary=is_preliminary,
                carrier_key=carrier_key,
            )
            if spec.table_name == "financial":
                record["statement_type"] = spec.statement_type
                financial.append(record)
            else:
                operating.append(record)
        if spec.table_name == "financial":
            normalized = _find_company_normalized_values(soup, spec)
            if normalized is not None:
                normalized_label, normalized_values = normalized
                for period_id, value in normalized_values:
                    record = _base_record(
                        document=document,
                        period_id=period_id,
                        metric_key=f"{spec.metric_key}_company_normalized",
                        segment=spec.segment,
                        value_raw=value,
                        unit_raw=spec.unit_raw,
                        scale_multiplier=spec.scale_multiplier,
                        unit_normalized=spec.unit_normalized,
                        extraction_method="html_table",
                        extraction_confidence=0.98,
                        metric_label_raw=normalized_label,
                        is_preliminary=is_preliminary,
                        carrier_key=carrier_key,
                    )
                    record["statement_type"] = spec.statement_type
                    financial.append(record)

    overrides = _narrative_overrides(text)
    for collection in (operating, financial):
        for record in collection:
            if record["period_id"] != current_period:
                continue
            override = overrides.get(str(record["metric_key"]))
            if override is None:
                continue
            record["value_raw"] = override
            record["value_normalized"] = override * float(record["scale_multiplier"])
            record["extraction_method"] = "regex_text"
            record["extraction_confidence"] = 0.99
    return operating, financial


def parse_all_earnings() -> tuple[pl.DataFrame, pl.DataFrame]:
    documents = pl.read_parquet(PATHS.silver / "sec_filing_documents.parquet")
    operating_records: list[dict[str, object]] = []
    financial_records: list[dict[str, object]] = []
    for document in documents.filter(
        (pl.col("form_type") == "6-K")
        & pl.col("archive_filename").str.contains(r"(?i)ex99")
        & pl.col("archive_filename").str.ends_with(".htm")
    ).iter_rows(named=True):
        content = read_bronze_verified(document["source_file"], document["source_hash"])
        category, _, _ = classify_6k(content.decode("utf-8", errors="replace"))
        if category != "earnings":
            continue
        operating, financial = parse_earnings_document(document)
        operating_records.extend(operating)
        financial_records.extend(financial)

    if not operating_records or not financial_records:
        raise ValueError("No SEC earnings metrics were extracted")
    operating_frame = pl.DataFrame(operating_records).sort(
        ["period_id", "metric_key", "accession_number"]
    )
    financial_frame = pl.DataFrame(financial_records).sort(
        ["period_id", "metric_key", "accession_number"]
    )
    for frame, table_name in (
        (operating_frame, "sec_operating_metrics"),
        (financial_frame, "sec_financials"),
    ):
        ambiguous = frame.filter(pl.col("unit_normalized").is_null())
        for source_file in ambiguous["source_file"].unique().to_list():
            log_issue(
                "silver",
                table_name,
                source_file,
                "error",
                "unit_ambiguity",
                "Parser extracted a metric without a normalized unit.",
                affected_rows=ambiguous.filter(pl.col("source_file") == source_file).height,
            )
    write_parquet_atomic(
        operating_frame, PATHS.silver / "sec_operating_metrics.parquet"
    )
    write_parquet_atomic(financial_frame, PATHS.silver / "sec_financials.parquet")
    return operating_frame, financial_frame
