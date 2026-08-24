"""Parse Stage 5 peer reports into comparable, fully traced silver facts."""

from __future__ import annotations

import calendar
from datetime import UTC, date, datetime
import io
import json
from pathlib import Path
import re
from typing import Any
import warnings

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import pandas as pd
import pdfplumber
import polars as pl

from src.config import PATHS
from src.parse.profiles import CarrierProfile, MetricPattern, load_profile
from src.parse.sec.common import quarter_dates, read_bronze_verified, write_parquet_atomic


PARSER_VERSION = "peer_metrics_v1.0.0"
MONTHS = {name.casefold(): index for index, name in enumerate(calendar.month_name) if name}
QUARTERS = {"first": 1, "second": 2, "third": 3, "fourth": 4}

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def _manifest() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (PATHS.bronze / "_manifest.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _latest_records(predicate) -> list[dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for record in _manifest():
        if predicate(record) and (PATHS.bronze / str(record["source_file"])).is_file():
            selected[str(record["source_url"])] = record
    return list(selected.values())


def _numbers(value: str) -> list[float]:
    tokens = re.findall(r"(?<![A-Za-z])\(?-?\d[\d,]*(?:\.\d+)?\)?%?", value)
    result: list[float] = []
    for token in tokens:
        negative = token.startswith("(") and token.endswith(")")
        cleaned = token.strip("()%").replace(",", "")
        number = float(cleaned)
        result.append(-number if negative else number)
    return result


def _line_value(text: str, patterns: tuple[str, ...]) -> tuple[str, float] | None:
    for line in text.splitlines():
        normalized = re.sub(r"\s+", " ", line).strip()
        lowered = normalized.casefold()
        for pattern in patterns:
            match = re.search(pattern, lowered, flags=re.I)
            if not match:
                continue
            suffix = normalized[match.end() :]
            values = _numbers(suffix)
            if values:
                return normalized[: match.end()].strip(), values[0]
    return None


def _base_record(
    *,
    carrier_key: str,
    period_id: str,
    metric: MetricPattern,
    value_raw: float,
    label: str,
    source: dict[str, Any],
    source_system: str,
    accession_number: str | None = None,
    extraction_method: str,
    fiscal_period_id: str | None = None,
) -> dict[str, object]:
    if "Q" in period_id:
        start, end = quarter_dates(period_id)
        period_type = "quarter"
    else:
        year = int(period_id[:4])
        month = int(period_id[-2:])
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
        period_type = "month"
    record: dict[str, object] = {
        "carrier_key": carrier_key,
        "accession_number": accession_number,
        "period_id": period_id,
        "calendar_period_id": period_id,
        "fiscal_period_id": fiscal_period_id or period_id,
        "period_type": period_type,
        "period_start_date": start,
        "period_end_date": end,
        "metric_key": metric.metric_key,
        "metric_label_raw": label,
        "segment": "total",
        "value_raw": float(value_raw),
        "unit_raw": metric.unit_raw,
        "scale_multiplier": metric.scale_multiplier,
        "value_normalized": float(value_raw) * metric.scale_multiplier,
        "unit_normalized": metric.unit_normalized,
        "is_preliminary": False,
        "is_yoy_comparison": False,
        "extraction_method": extraction_method,
        "extraction_confidence": 0.98,
        "source_system": source_system,
        "source_file": str(source["source_file"]),
        "source_hash": str(source["sha256"]),
        "ingested_at": datetime.fromisoformat(str(source["downloaded_at"])),
        "parser_version": PARSER_VERSION,
    }
    if metric.table_name == "financial":
        record["statement_type"] = "income_statement"
    return record


def _html_rows(content: bytes) -> str:
    soup = BeautifulSoup(content, "lxml")
    return "\n".join(" ".join(row.stripped_strings) for row in soup.find_all("tr"))


def _period_from_earnings_text(text: str) -> str:
    match = re.search(r"Quarter:\s*([1-4])\s+Year:\s*(20\d{2})", text, re.I)
    if match:
        return f"{match.group(2)}Q{match.group(1)}"
    match = re.search(
        r"(first|second|third|fourth) quarter(?: of)?\s+(20\d{2})", text, re.I
    )
    if match:
        return f"{match.group(2)}Q{QUARTERS[match.group(1).casefold()]}"
    match = re.search(r"\b([1-4])Q\s*(20\d{2}|\d{2})\b", text, re.I)
    if match:
        year = match.group(2)
        return f"{year if len(year) == 4 else '20' + year}Q{match.group(1)}"
    raise ValueError("Quarter not found in earnings report")


def _metric(profile: CarrierProfile, key: str) -> MetricPattern:
    return next(metric for metric in profile.metric_patterns if metric.metric_key == key)


def parse_volaris() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    profile = load_profile("VOLARIS")
    records = _latest_records(
        lambda row: row.get("source_system") == "sec"
        and "/1520504/" in str(row.get("source_url", ""))
        and ("ex99" in str(row.get("source_url", "")).casefold() or "ex-99" in str(row.get("source_url", "")).casefold())
    )
    operating: list[dict[str, object]] = []
    financial: list[dict[str, object]] = []
    for source in records:
        content = read_bronze_verified(str(source["source_file"]), str(source["sha256"]))
        visible = BeautifulSoup(content, "lxml").get_text(" ", strip=True)
        try:
            period_id = _period_from_earnings_text(visible)
        except ValueError:
            continue
        rows = _html_rows(content)
        accession = re.search(r"/(\d{18})/", str(source["source_url"]))
        accession_number = None
        if accession:
            compact = accession.group(1)
            accession_number = f"{compact[:10]}-{compact[10:12]}-{compact[12:]}"
        for metric in profile.metric_patterns:
            found = _line_value(rows, metric.patterns)
            if found is None:
                continue
            label, value = found
            record = _base_record(
                carrier_key="VOLARIS",
                period_id=period_id,
                metric=metric,
                value_raw=value,
                label=label,
                source=source,
                source_system="sec_edgar",
                accession_number=accession_number,
                extraction_method="profile_html_table",
            )
            (financial if metric.table_name == "financial" else operating).append(record)
    return operating, financial


def _pdf_text(content: bytes) -> str:
    with pdfplumber.open(io.BytesIO(content)) as document:
        return "\n".join(page.extract_text() or "" for page in document.pages)


def parse_viva() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    profile = load_profile("VIVA_AEROBUS")
    records = _latest_records(lambda row: row.get("source_system") == "viva_ir")
    operating: list[dict[str, object]] = []
    financial: list[dict[str, object]] = []
    for source in records:
        match = re.search(r"/(20\d{2})-([1-4])T\d{2}-en\.pdf", str(source["source_url"]), re.I)
        if not match:
            continue
        period_id = f"{match.group(1)}Q{match.group(2)}"
        text = _pdf_text(
            read_bronze_verified(str(source["source_file"]), str(source["sha256"]))
        )
        for metric in profile.metric_patterns:
            found = _line_value(text, metric.patterns)
            if found is None:
                continue
            label, value = found
            record = _base_record(
                carrier_key="VIVA_AEROBUS",
                period_id=period_id,
                metric=metric,
                value_raw=value,
                label=label,
                source=source,
                source_system="viva_ir",
                extraction_method="profile_pdf_text",
            )
            (financial if metric.table_name == "financial" else operating).append(record)
    return operating, financial


def _delta_period(text: str) -> str:
    match = re.search(r"quarterly period ended\s+(March|June|September)\s+\d{1,2},\s*(20\d{2})", text, re.I)
    if not match:
        raise ValueError("Delta 10-Q period not found")
    quarter = {"march": 1, "june": 2, "september": 3}[match.group(1).casefold()]
    return f"{match.group(2)}Q{quarter}"


def _delta_period_from_url(source_url: str) -> str | None:
    match = re.search(r"/dal-(20\d{2})(03|06|09)\d{2}\.htm$", source_url)
    if not match:
        return None
    quarter = {"03": 1, "06": 2, "09": 3}[match.group(2)]
    return f"{match.group(1)}Q{quarter}"


def _inline_xbrl_quarter_value(content: bytes, concept: str, period_id: str) -> float:
    """Return the non-dimensional current-quarter fact, expressed in USD millions."""
    soup = BeautifulSoup(content, "lxml")
    start, end = quarter_dates(period_id)
    eligible_contexts: set[str] = set()
    for context in soup.find_all(lambda tag: tag.name and tag.name.casefold().endswith("context")):
        start_tag = context.find(
            lambda tag: tag.name and tag.name.casefold().endswith("startdate")
        )
        end_tag = context.find(
            lambda tag: tag.name and tag.name.casefold().endswith("enddate")
        )
        has_segment = context.find(
            lambda tag: tag.name and tag.name.casefold().endswith("segment")
        ) is not None
        if (
            context.get("id")
            and start_tag is not None
            and end_tag is not None
            and start_tag.get_text(strip=True) == start.isoformat()
            and end_tag.get_text(strip=True) == end.isoformat()
            and not has_segment
        ):
            eligible_contexts.add(str(context["id"]))
    facts = soup.find_all(
        attrs={"name": lambda value: value and value.casefold() == f"us-gaap:{concept}".casefold()}
    )
    values: set[float] = set()
    for fact in facts:
        if str(fact.get("contextref")) not in eligible_contexts:
            continue
        numbers = _numbers(fact.get_text(" ", strip=True))
        if not numbers:
            continue
        value = numbers[0] * (10 ** int(fact.get("scale", 0)))
        if fact.get("sign") == "-":
            value = -abs(value)
        values.add(value / 1_000_000)
    if len(values) != 1:
        raise ValueError(
            f"Expected one consolidated {concept} value for {period_id}, found {sorted(values)}"
        )
    return values.pop()


def parse_delta() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    profile = load_profile("DELTA")
    records = _latest_records(
        lambda row: row.get("source_system") == "sec"
        and "/27904/" in str(row.get("source_url", ""))
        and re.search(r"/dal-20\d{6}\.htm$", str(row.get("source_url", ""))) is not None
    )
    operating: list[dict[str, object]] = []
    financial: list[dict[str, object]] = []
    financial_concepts = {
        "total_revenue": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "operating_income": "OperatingIncomeLoss",
        "net_income": "NetIncomeLoss",
    }
    for source in records:
        content = read_bronze_verified(str(source["source_file"]), str(source["sha256"]))
        period_id = _delta_period_from_url(str(source["source_url"]))
        if period_id is None:
            continue
        rows = _html_rows(content)
        accession = re.search(r"/(\d{18})/", str(source["source_url"]))
        compact = accession.group(1) if accession else ""
        accession_number = f"{compact[:10]}-{compact[10:12]}-{compact[12:]}" if compact else None
        for metric in profile.metric_patterns:
            if metric.table_name != "operating":
                continue
            found = _line_value(rows, metric.patterns)
            if found is None:
                continue
            label, value = found
            record = _base_record(
                carrier_key="DELTA",
                period_id=period_id,
                metric=metric,
                value_raw=value,
                label=label,
                source=source,
                source_system="sec_edgar",
                accession_number=accession_number,
                extraction_method="profile_html_table",
            )
            operating.append(record)
        for key, concept in financial_concepts.items():
            financial.append(
                _base_record(
                    carrier_key="DELTA",
                    period_id=period_id,
                    metric=_metric(profile, key),
                    value_raw=_inline_xbrl_quarter_value(content, concept, period_id),
                    label=f"us-gaap:{concept}",
                    source=source,
                    source_system="sec_edgar",
                    accession_number=accession_number,
                    extraction_method="inline_xbrl_consolidated_context",
                )
            )
    return operating, financial


def _ryanair_fiscal_id(year: int, month: int) -> str:
    fiscal_year = year + 1 if month >= 4 else year
    fiscal_quarter = ((month - 4) % 12) // 3 + 1
    return f"FY{fiscal_year}Q{fiscal_quarter}"


def parse_ryanair() -> list[dict[str, object]]:
    profile = load_profile("RYANAIR")
    records = _latest_records(lambda row: row.get("source_system") == "ryanair_ir")
    if len(records) != 1:
        raise ValueError(f"Expected one current Ryanair key-stats artifact, found {len(records)}")
    source = records[0]
    content = read_bronze_verified(str(source["source_file"]), str(source["sha256"]))
    soup = BeautifulSoup(content, "lxml")
    monthly: list[dict[str, object]] = []
    passenger_metric = _metric(profile, "passengers")
    lf_metric = _metric(profile, "load_factor_total")
    for table in soup.find_all("table"):
        heading = table.find_previous("h3")
        if heading is None:
            continue
        digits = re.sub(r"\D", "", heading.get_text(" ", strip=True))
        if len(digits) != 4:
            continue
        year = int(digits)
        frame = pd.read_html(io.StringIO(str(table)))[0]
        for row in frame.to_dict("records"):
            month_name = str(row.get("Month", "")).casefold()
            if month_name not in MONTHS:
                continue
            month = MONTHS[month_name]
            period_id = f"{year}M{month:02d}"
            fiscal_id = _ryanair_fiscal_id(year, month)
            passenger_value = float(str(row["Passengers"]).casefold().rstrip("m"))
            lf_value = float(str(row["Load Factor"]).rstrip("%"))
            monthly.extend(
                [
                    _base_record(
                        carrier_key="RYANAIR",
                        period_id=period_id,
                        metric=passenger_metric,
                        value_raw=passenger_value,
                        label="Passengers",
                        source=source,
                        source_system="ryanair_ir",
                        extraction_method="profile_html_table",
                        fiscal_period_id=fiscal_id,
                    ),
                    _base_record(
                        carrier_key="RYANAIR",
                        period_id=period_id,
                        metric=lf_metric,
                        value_raw=lf_value,
                        label="Load Factor",
                        source=source,
                        source_system="ryanair_ir",
                        extraction_method="profile_html_table",
                        fiscal_period_id=fiscal_id,
                    ),
                ]
            )
    monthly_frame = pl.DataFrame(monthly)
    values = monthly_frame.select(
        "period_id", "period_start_date", "value_raw", "metric_key"
    ).pivot(on="metric_key", index=["period_id", "period_start_date"], values="value_raw")
    quarterly_rows: list[dict[str, object]] = []
    for (year, quarter), group in values.with_columns(
        pl.col("period_start_date").dt.year().alias("year"),
        pl.col("period_start_date").dt.quarter().alias("quarter"),
    ).group_by("year", "quarter"):
        if group.height != 3:
            continue
        passengers = float(group["passengers"].sum())
        seats = float((group["passengers"] / (group["load_factor_total"] / 100)).sum())
        load_factor = passengers / seats * 100
        period_id = f"{year}Q{quarter}"
        first_month = (int(quarter) - 1) * 3 + 1
        fiscal_id = _ryanair_fiscal_id(int(year), first_month).rsplit("Q", 1)[0]
        for metric, value in ((passenger_metric, passengers), (lf_metric, load_factor)):
            quarterly_rows.append(
                _base_record(
                    carrier_key="RYANAIR",
                    period_id=period_id,
                    metric=metric,
                    value_raw=value,
                    label=f"Calendar-quarter {metric.metric_key} reconstructed from months",
                    source=source,
                    source_system="ryanair_ir",
                    extraction_method="monthly_calendar_reconstruction",
                    fiscal_period_id=fiscal_id,
                )
            )
    return monthly + quarterly_rows


def _delta_companyfacts_reconciliation(financial: pl.DataFrame) -> pl.DataFrame:
    records = _latest_records(
        lambda row: row.get("source_url")
        == "https://data.sec.gov/api/xbrl/companyfacts/CIK0000027904.json"
    )
    if len(records) != 1:
        raise ValueError("Delta companyfacts artifact is missing or ambiguous")
    source = records[0]
    payload = json.loads(
        read_bronze_verified(str(source["source_file"]), str(source["sha256"]))
    )
    concepts = {
        "total_revenue": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "operating_income": "OperatingIncomeLoss",
        "net_income": "NetIncomeLoss",
    }
    parsed = financial.filter(pl.col("carrier_key") == "DELTA").select(
        "period_id",
        "metric_key",
        "accession_number",
        pl.col("value_normalized").alias("parsed_10q_value"),
    )
    xbrl: list[dict[str, object]] = []
    for row in parsed.to_dicts():
        start, end = quarter_dates(str(row["period_id"]))
        concept = concepts[str(row["metric_key"])]
        units = payload["facts"]["us-gaap"][concept]["units"]["USD"]
        matches = {
            (float(fact["val"]), str(fact["filed"]))
            for fact in units
            if fact.get("accn") == row["accession_number"]
            and fact.get("form") == "10-Q"
            and fact.get("start") == start.isoformat()
            and fact.get("end") == end.isoformat()
        }
        if len(matches) != 1:
            raise ValueError(
                f"Expected one Companyfacts match for {row['period_id']} {row['metric_key']}, "
                f"found {sorted(matches)}"
            )
        value, filed = matches.pop()
        xbrl.append(
            {
                "period_id": row["period_id"],
                "metric_key": row["metric_key"],
                "accession_number": row["accession_number"],
                "companyfacts_value": value,
                "companyfacts_filed": filed,
            }
        )
    result = parsed.join(
        pl.DataFrame(xbrl), on=["period_id", "metric_key", "accession_number"], how="inner"
    )
    return result.with_columns(
        (
            (pl.col("parsed_10q_value") - pl.col("companyfacts_value")).abs()
            / pl.col("companyfacts_value").abs()
        ).alias("absolute_difference_pct"),
        pl.lit(str(source["source_file"])).alias("source_file"),
        pl.lit(str(source["sha256"])).alias("source_hash"),
        pl.lit(PARSER_VERSION).alias("parser_version"),
    ).sort(["period_id", "metric_key"])


def _ryanair_fiscal_reconciliation(operating: pl.DataFrame) -> pl.DataFrame:
    annual_sources = _latest_records(
        lambda row: row.get("source_system") == "sec"
        and "/1038683/" in str(row.get("source_url", ""))
        and str(row.get("source_url", "")).endswith("20f.htm")
    )
    reported: list[dict[str, object]] = []
    for source in annual_sources:
        match = re.search(r"tmb-(20\d{2})0331x20f\.htm$", str(source["source_url"]))
        if not match:
            continue
        text = _html_rows(
            read_bronze_verified(str(source["source_file"]), str(source["sha256"]))
        )
        passengers = _line_value(text, (r"^revenue passengers booked \(millions\)",))
        load_factor = _line_value(text, (r"^booked passenger load factor",))
        if passengers is None or load_factor is None:
            raise ValueError(f"Ryanair annual anchors missing from {source['source_file']}")
        reported.append(
            {
                "fiscal_year": int(match.group(1)),
                "reported_passengers_millions": passengers[1],
                "reported_load_factor_pct": load_factor[1],
                "reported_source_file": str(source["source_file"]),
                "reported_source_hash": str(source["sha256"]),
            }
        )
    monthly = (
        operating.filter(
            (pl.col("carrier_key") == "RYANAIR") & (pl.col("period_type") == "month")
        )
        .select("period_start_date", "metric_key", "value_raw")
        .pivot(on="metric_key", index="period_start_date", values="value_raw")
        .with_columns(
            pl.when(pl.col("period_start_date").dt.month() >= 4)
            .then(pl.col("period_start_date").dt.year() + 1)
            .otherwise(pl.col("period_start_date").dt.year())
            .alias("fiscal_year")
        )
        .group_by("fiscal_year")
        .agg(
            pl.len().alias("months"),
            pl.col("passengers").sum().alias("reconstructed_passengers_millions"),
            (
                pl.col("passengers").sum()
                / (pl.col("passengers") / (pl.col("load_factor_total") / 100)).sum()
                * 100
            ).alias("reconstructed_load_factor_pct"),
        )
        .filter(pl.col("months") == 12)
    )
    reconciliation = pl.DataFrame(reported).join(
        monthly, on="fiscal_year", how="inner", validate="1:1"
    ).with_columns(
        (
            (pl.col("reconstructed_passengers_millions") - pl.col("reported_passengers_millions"))
            .abs()
            / pl.col("reported_passengers_millions")
        ).alias("passenger_difference_pct"),
        (
            pl.col("reconstructed_load_factor_pct") - pl.col("reported_load_factor_pct")
        ).abs().alias("load_factor_difference_pp"),
        pl.lit(PARSER_VERSION).alias("parser_version"),
    ).sort("fiscal_year")
    return reconciliation


def build_peer_metrics() -> dict[str, object]:
    operating_records: list[dict[str, object]] = []
    financial_records: list[dict[str, object]] = []
    for parser in (parse_volaris, parse_viva, parse_delta):
        operating, financial = parser()
        operating_records.extend(operating)
        financial_records.extend(financial)
    operating_records.extend(parse_ryanair())
    operating = pl.DataFrame(operating_records).unique(
        subset=["carrier_key", "period_id", "metric_key", "segment"], keep="last"
    ).sort(["carrier_key", "period_type", "period_id", "metric_key"])
    financial = pl.DataFrame(financial_records).unique(
        subset=["carrier_key", "period_id", "metric_key"], keep="last"
    ).with_columns(
        pl.when(pl.col("statement_type").is_null())
        .then(pl.lit("income_statement"))
        .otherwise(pl.col("statement_type"))
        .alias("statement_type")
    ).sort(["carrier_key", "period_id", "metric_key"])
    write_parquet_atomic(operating, PATHS.silver / "peer_operating_metrics.parquet")
    write_parquet_atomic(financial, PATHS.silver / "peer_financials.parquet")
    reconciliation = _delta_companyfacts_reconciliation(financial)
    write_parquet_atomic(
        reconciliation, PATHS.silver / "delta_companyfacts_reconciliation.parquet"
    )
    ryanair_reconciliation = _ryanair_fiscal_reconciliation(operating)
    write_parquet_atomic(
        ryanair_reconciliation,
        PATHS.silver / "ryanair_fiscal_reconciliation.parquet",
    )
    return {
        "operating_rows": operating.height,
        "financial_rows": financial.height,
        "delta_reconciliation_rows": reconciliation.height,
        "ryanair_reconciliation_rows": ryanair_reconciliation.height,
    }


def main() -> int:
    print(json.dumps(build_peer_metrics(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
