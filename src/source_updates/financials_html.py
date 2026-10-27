"""AM Q3 official IR 6-K, financial Exhibit99.1 only; same twenty source metrics."""

import hashlib
import re

import pandas as pd
from bs4 import BeautifulSoup, Tag

from src.source_updates.financials import GRAIN, PATTERNS, STATEMENT, value

URL = "https://ir.aeromexico.com/node/9131/html"
PERIOD = "2026Q3"
DAY = "2026-10-19"
TITLE = "Aeroméxico Reports Unaudited Third Quarter 2026 Results"
ANCHORS = (
    "aeromxicoreportsunauditedt.htm",
    "aeromxicojulytrafficreport.htm",
    "aeromxicoaugusttrafficrepo.htm",
    "aeromxicoseptembertrafficr.htm",
)
STATEMENT_TITLE = "Consolidated Statements of Profit or Loss and other Comprehensive Income (Unaudited)"
LABELS = {
    "total_revenue": "Total revenue",
    "operating_expenses_total": "Total operating expenses",
    "operating_income": "Total operating income",
    "net_income": "Net income (loss) for the period",
    "income_before_tax": "Income before income tax",
    "income_tax": "Income tax (benefit)",
    "jet_fuel_expense": "Jet-fuel",
    "wages_salaries_benefits": "Wages, salaries and benefits",
    "maintenance_expense": "Maintenance",
    "depreciation_amortization": "Depreciation and amortization",
    "aircraft_leasing_expense": "Aircraft leasing",
    "adjusted_ebitdar": "Adjusted EBITDAR (1)",
    "ebitdar_margin": "Adjusted EBITDAR margin (1) (% revenue)",
    "operating_margin": "Operating income margin (% of revenue)",
    "asm": "Total ASMs (millions)",
    "rpm": "Total RPMs (millions)",
    "load_factor": "Load factor on scheduled flights (%)",
    "passengers": "Passengers ('000)",
    "fuel_liters": "Total liters of fuel ('000)",
    "casm_ex_fuel": "Total cost excluding fuel / ASM (USD cents)",
}


def text(node):
    return " ".join(node.get_text(" ", strip=True).split())


def cells(row):
    return row.find_all(["td", "th"], recursive=False)


def document(body, original):
    if (
        not 0 < len(body) <= 600_000
        or original.get("source_system") != "aeromexico_ir"
        or original.get("source_url") != URL
        or original.get("logical_key") != "aeromexico_ir|am_financials_2026Q3_6K|2026Q3|html"
        or original.get("sha256") != hashlib.sha256(body).hexdigest()
    ):
        raise ValueError("AM Q3 requires the exact official IR HTML identity and physical SHA integrity")
    soup = BeautifulSoup(body, "html.parser")
    blocks = soup.select("#block-client-site-content")
    if len(blocks) != 1:
        raise ValueError("AM IR filing content is absent or ambiguous")
    block = blocks[0]
    documents = block.find_all("html", recursive=False)
    if len(documents) != 5:
        raise ValueError("Reviewed AM 6-K must contain cover and four separately bounded exhibits")
    cover = documents[0]
    cover_text = text(cover)
    required = (
        "FORM 6-K",
        "For the month of October 2026",
        "Commission File Number: 001-42931",
        "Grupo Aeroméxico, S.A.B. de C.V.",
        "On October 19, 2026, Grupo Aeroméxico, S.A.B. de C.V.",
        TITLE,
        "as Exhibit 99.1",
        "Date: October 19, 2026",
    )
    if any(token not in cover_text for token in required):
        raise ValueError("AM 6-K cover issuer, financial exhibit attribution or report day changed")
    rows = [cells(row) for table in cover.find_all("table") for row in table.find_all("tr")]
    index_rows = [row for row in rows if row and text(row[0]) in {"99.1", "99.2", "99.3", "99.4"}]
    if len(index_rows) != 4 or [text(row[0]) for row in index_rows] != ["99.1", "99.2", "99.3", "99.4"]:
        raise ValueError("AM exhibit index must separate financial99.1 from traffic99.2-.4")
    for i, row in enumerate(index_rows):
        links = [a.get("href") for cell in row for a in cell.find_all("a", href=True)]
        if not links or set(links) != {"#" + ANCHORS[i]}:
            raise ValueError("AM financial/traffic exhibit index links changed")
    if TITLE not in text(index_rows[0][-1]) or "October 19, 2026" not in text(index_rows[0][-1]):
        raise ValueError("AM financial exhibit index title/day changed")
    markers = []
    for name in ANCHORS:
        found = block.find_all("a", attrs={"name": name})
        if len(found) != 1 or found[0].parent.parent is not block:
            raise ValueError("AM exhibit anchor missing, duplicated or nested outside reviewed boundary")
        markers.append(found[0].parent)
    between = []
    for node in markers[0].next_siblings:
        if node is markers[1]:
            break
        if isinstance(node, Tag):
            between.append(node)
    if len(between) != 1 or between[0] is not documents[1]:
        raise ValueError("Financial99.1 must be one HTML document ending before traffic99.2")
    exhibit = between[0]
    intro = text(exhibit)
    required = (
        TITLE,
        "Mexico City, Mexico, October 19, 2026 - Grupo Aeroméxico S.A.B. de C.V.",
        "reported unaudited consolidated financial results for the three months ended September 30, 2026",
        "The Company has used the U.S. dollar, its functional currency, as the presentation currency",
        "All figures are expressed in millions of U.S. dollars unless otherwise indicated.",
        "available seat miles (ASMs)",
    )
    if any(token not in intro for token in required) or "preliminary" in intro.casefold():
        raise ValueError("AM financial body issuer/day/quarter/currency/ASM or preliminary status changed")
    return exhibit


def headers(table, statement):
    rows = [cells(row) for row in table.find_all("tr")]
    groups = [
        row
        for row in rows
        if [text(c) for c in row] == ["", "Three Months Ended September 30", "Nine Months Ended September 30"]
    ]
    if len(groups) != 1 or [c.get("colspan", "1") for c in groups[0]] != ["3", "9", "9"]:
        raise ValueError("AM quarterly versus nine-month column groups changed")
    required = [""] if statement else ["Financial Indicators", "Operating Indicators"]
    for label in required:
        found = [
            row
            for row in rows
            if len(row) == 7
            and text(row[0]) == label
            and [text(c) for c in row[1:]]
            == [
                "2026",
                "2025",
                "Var. %" if statement else "Var.",
                "2026",
                "2025",
                "Var. %" if statement else "Var.",
            ]
        ]
        if len(found) != 1 or any(c.get("colspan") != "3" for c in found[0]):
            raise ValueError("AM current/prior year headers or section column spans changed")


def monetary_headings(table):
    """Local table declarations override the introductory USD-millions default.

    Inspect unit headings, not every occurrence of 'thousand' or 'cents': native
    passenger/fuel quantities and CASM ratio labels keep their reported units.
    """
    declaration = re.compile(
        r"^\(?\s*(?:(?:amounts?|figures?|cifras|montos|importes|valores)\s+"
        r"(?:(?:are|son|se)\s+)?(?:(?:expressed|presented|expresad[oa]s?|presentad[oa]s?)\s+)?"
        r"(?:in|en)\b|(?:in|en)\s+(?:thousands?|millions?|miles|millones)\b|"
        r"(?:usd|mxn|eur|u\.s\.\s*dollars?|d[oó]lares|pesos)\b)",
        re.I,
    )
    usd = r"(?:usd|u\.s\.\s*dollars?|us\s+dollars?|d[oó]lares\s+estadounidenses)"
    monetary_thousands = re.compile(
        rf"(?:\b(?:thousands?\s+(?:of\s+)?|miles\s+de\s+){usd}\b|"
        rf"\b{usd}\s*\(?\s*(?:in\s+)?(?:thousands?|miles|'?000)\b)",
        re.I,
    )
    for row in table.find_all(["tr", "caption"]):
        columns = [row] if row.name == "caption" else cells(row)
        if not columns or text(columns[0]) in LABELS.values():
            continue
        heading = " ".join(text(c) for c in columns).strip()
        if (
            re.search(r"\b(?:mxn|pesos?|eur|euros?)\b", heading, re.I)
            or monetary_thousands.search(heading)
            or declaration.match(heading)
            and (
                not re.search(rf"\b{usd}\b", heading, re.I)
                or not re.search(r"\b(?:millions?|millones)\b", heading, re.I)
            )
        ):
            raise ValueError("AM local monetary table heading contradicts reported USD millions")


def parse(inputs, period):
    if set(inputs) != {"html"} or period != PERIOD:
        raise ValueError("AM official HTML edition supports only the reviewed 2026Q3 financial quarter")
    body, original = inputs["html"]
    exhibit = document(body, original)
    tables = exhibit.find_all("table")
    statements = [(i, t) for i, t in enumerate(tables, 1) if STATEMENT_TITLE in text(t)]
    summaries = [
        (i, t)
        for i, t in enumerate(tables, 1)
        if any(text(c[0]) == "Financial Indicators" for row in t.find_all("tr") if (c := cells(row)))
    ]
    if len(statements) != 1 or len(summaries) != 1:
        raise ValueError("AM financial statement/indicator table missing or duplicated inside99.1")
    monetary_headings(statements[0][1])
    monetary_headings(summaries[0][1])
    headers(statements[0][1], True)
    headers(summaries[0][1], False)
    statement_keys = set(STATEMENT) - {"rent_depreciation_amortization_combined"}
    definitions = {key: (unit, definition) for key, _, unit, definition in PATTERNS}
    if set(LABELS) != statement_keys | set(definitions):
        raise ValueError("AM financial domain must remain exactly the existing twenty metrics")
    output = []
    for key, label in LABELS.items():
        table_index, table = statements[0] if key in statement_keys else summaries[0]
        matches = [
            (i, c)
            for i, row in enumerate(table.find_all("tr"), 1)
            if (c := cells(row)) and text(c[0]) == label
        ]
        if len(matches) != 1:
            raise ValueError("AM source metric row missing or duplicated inside its financial table")
        row_index, columns = matches[0]
        if len(columns) != 7 or any(c.get("colspan") != "3" for c in columns):
            raise ValueError("AM source metric column layout changed")
        unit, definition = ("USD millions", "reported") if key in statement_keys else definitions[key]
        token = text(columns[1])
        if (unit == "percent") != token.endswith("%"):
            raise ValueError("AM current-quarter token percent style differs from source unit")
        amount = value(token)
        if unit == "percent" and not -100 <= amount <= 100 or key == "load_factor" and amount < 0:
            raise ValueError("AM source ratio outside its reported percent domain")
        if key in {"asm", "rpm", "passengers", "fuel_liters", "casm_ex_fuel"} and amount < 0:
            raise ValueError("AM physical/source denominator metric is negative")
        output.append(
            dict(
                period_id=period,
                period_type="quarter",
                metric_key=key,
                definition=definition,
                value=amount,
                unit=unit,
                source_value=token,
                source_label=label,
                carrier_key="AEROMEXICO",
                is_preliminary=None,
                is_unaudited=True,
                not_ytd=True,
                normalized_unit_conversion_performed=False,
                source_system=original["source_system"],
                source_file=original["source_file"],
                source_hash=original["sha256"],
                ingested_at=pd.Timestamp(original["downloaded_at"]),
                source_locator=f"exhibit:99.1/{ANCHORS[0]}/table:{table_index}/tr:{row_index}/td:2/quarter-current",
                parser_version="am_ir_2026q3_html_source_units_v1",
                agent_eligible=False,
            )
        )
    frame = pd.DataFrame(output)
    if len(frame) != 20 or frame.duplicated(GRAIN).any() or frame.value.isna().any():
        raise ValueError("AM financial metric domain/grain/missingness changed")
    metrics = frame.set_index("metric_key").value
    if (
        abs(metrics.total_revenue - metrics.operating_expenses_total - metrics.operating_income) > 1
        or abs(metrics.income_before_tax - metrics.income_tax - metrics.net_income) > 1
    ):
        raise ValueError("AM rounded statement accounting identities disagree beyond one reported million")
    return frame, dict(
        rows=20,
        report_period=period,
        months_validated=[],
        quarters_validated=[period],
        statement_accounting_checks=2,
        scope="retained_AM_2026Q3_official_IR_HTML_financial_Ex99.1_unaudited_twenty_reported_quarter_metrics_only",
        asm_not_ask=True,
        casm_not_cask=True,
        normalized_unit_conversion_performed=False,
        published_at=None,
        first_publication_date=None,
        release_lag_days=None,
        source_report_date_as_reported=DAY,
        printed_report_date_literal="October 19, 2026",
        source_preliminary=None,
        source_unaudited=True,
        ytd_columns_imported=0,
        financial_exhibit="99.1",
        excluded_traffic_exhibits=["99.2", "99.3", "99.4"],
    )
