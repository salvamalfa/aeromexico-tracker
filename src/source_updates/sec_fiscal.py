"""Reviewed retained Ryanair FY2026 inline XBRL, never a calendar-quarter conversion."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import json
import re

from lxml import etree
import pandas as pd

VERSION = "retained_ryanair_sec_fy2026_v1"
TABLE = "fact_ryanair_retained_fiscal_xbrl"
GRAIN = ["period_id", "metric_key"]
ACCESSION = "0001104659-26-076131"
DOCUMENT = "tmb-20260331x20f.htm"
DIRECTORY = "/Archives/edgar/data/1038683/000110465926076131"
NS = {"x": "http://www.xbrl.org/2003/instance", "ix": "http://www.xbrl.org/2013/inlineXBRL"}
METRICS = {
    "Revenue": "duration",
    "ProfitLoss": "duration",
    "CashFlowsFromUsedInOperatingActivities": "duration",
    "Assets": "instant",
    "Liabilities": "instant",
    "Equity": "instant",
}


def unique(items, description):
    if len(items) != 1:
        raise ValueError(f"Expected exactly one {description}")
    return items[0]


def text(node):
    if node.get("continuedAt") or any(
        isinstance(child.tag, str) and etree.QName(child).namespace == NS["ix"]
        for child in node.iterdescendants()
    ):
        raise ValueError("Unreviewed nested inline/excluded/continued XBRL content")
    return " ".join("".join(node.itertext()).split())


def fiscal_end_date_text(node, context):
    children = [
        child
        for child in node.iterdescendants()
        if isinstance(child.tag, str) and etree.QName(child).namespace == NS["ix"]
    ]
    expected = [
        ("dei:CurrentFiscalYearEndDate", "March 31", "ixt:date-monthname-day-en"),
        ("dei:DocumentFiscalYearFocus", "2026", None),
    ]
    if (
        node.get("continuedAt")
        or node.get("format") != "ixt:date-monthname-day-year-en"
        or len(children) != 2
    ):
        raise ValueError("Unreviewed DEI fiscal end-date inline structure")
    for child, (name, value, transformation) in zip(children, expected, strict=True):
        if (
            child.tag != "{" + NS["ix"] + "}nonNumeric"
            or child.get("name") != name
            or child.get("contextRef") != context
            or child.get("format") != transformation
            or child.nsmap.get("dei") != node.nsmap.get("dei")
            or child.nsmap.get("ixt") != node.nsmap.get("ixt")
            or text(child) != value
        ):
            raise ValueError("Unreviewed nested DEI fiscal date/year")
    return " ".join("".join(node.itertext()).split())


def parse(inputs, review_period):
    if review_period != "2026Q2":
        raise ValueError(
            "Reviewed SEC filing only: Q2 review of FY2026 ending March 31, not quarterly metrics"
        )
    body, original = inputs["html"]
    submissions = json.loads(inputs["submissions"][0])
    index = json.loads(inputs["index"][0])["directory"]
    if (
        str(submissions.get("cik")).lstrip("0") != "1038683"
        or submissions.get("name") != "RYANAIR HOLDINGS PLC"
        or submissions.get("fiscalYearEnd") != "0331"
    ):
        raise ValueError("SEC submissions entity mismatch")
    recent = submissions["filings"]["recent"]
    position = unique(
        [i for i, value in enumerate(recent["accessionNumber"]) if value == ACCESSION], "selected accession"
    )
    if any(
        recent[key][position] != value
        for key, value in {
            "form": "20-F",
            "reportDate": "2026-03-31",
            "primaryDocument": DOCUMENT,
            "filingDate": "2026-06-22",
            "acceptanceDateTime": "2026-06-22T12:47:18.000Z",
        }.items()
    ):
        raise ValueError("SEC filing metadata changed; review the actual edition")
    entry = unique([item for item in index["item"] if item["name"] == DOCUMENT], "index document")
    if index["name"] != DIRECTORY or int(entry["size"]) != len(body):
        raise ValueError("SEC index directory or document size mismatch")
    if not original["source_url"].endswith(DIRECTORY + "/" + DOCUMENT):
        raise ValueError("Selected inline XBRL URL does not identify the filing")
    if len(body) > 20_000_000 or b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise ValueError("Unreviewed XML size or DTD/entity declaration")
    try:
        root = etree.fromstring(
            body, etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
        )
    except etree.XMLSyntaxError as exc:
        raise ValueError("Invalid inline XBRL XML") from exc
    identifiers = [node.get("id") for node in root.iter() if node.get("id") is not None]
    if any(not value.strip() for value in identifiers) or len(identifiers) != len(set(identifiers)):
        raise ValueError("Missing/duplicate document-wide XBRL/HTML identifiers")
    if any(
        root.nsmap.get(key) != value
        for key, value in {
            "ifrs-full": "https://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full",
            "dei": "http://xbrl.sec.gov/dei/2025",
            "iso4217": "http://www.xbrl.org/2003/iso4217",
            "ixt": "http://www.xbrl.org/inlineXBRL/transformation/2022-02-16",
        }.items()
    ):
        raise ValueError("Unreviewed XBRL taxonomy/transformation namespace")
    contexts = root.findall(".//x:context", NS)
    units = root.findall(".//x:unit", NS)
    if (
        any(not node.get("id", "").strip() for node in contexts + units)
        or len({node.get("id") for node in contexts}) != len(contexts)
        or len({node.get("id") for node in units}) != len(units)
    ):
        raise ValueError("Missing/duplicate XBRL context or unit identifiers")
    selected = {}
    for kind, end_tag in [("duration", "endDate"), ("instant", "instant")]:
        candidates = [
            node
            for node in contexts
            if node.find(".//x:segment", NS) is None
            and node.find("x:scenario", NS) is None
            and node.findtext(f"x:period/x:{end_tag}", namespaces=NS) == "2026-03-31"
            and (kind == "instant" or node.findtext("x:period/x:startDate", namespaces=NS) == "2025-04-01")
        ]
        node = unique(candidates, f"consolidated fiscal {kind} context")
        entity = unique(node.findall("x:entity", NS), "context entity element")
        period = unique(node.findall("x:period", NS), "context period element")
        expected_tags = {
            "{" + NS["x"] + "}" + key
            for key in (["startDate", "endDate"] if kind == "duration" else ["instant"])
        }
        if (
            len(node) != 2
            or len(entity) != 1
            or len(period) != len(expected_tags)
            or {child.tag for child in period} != expected_tags
        ):
            raise ValueError("Unreviewed consolidated context structure")
        identity = unique(entity.findall("x:identifier", NS), "context entity")
        if identity.get("scheme") != "http://www.sec.gov/CIK" or text(identity) != "0001038683":
            raise ValueError("XBRL context entity mismatch")
        selected[kind] = node.get("id")
    for name, expected in {
        "EntityCentralIndexKey": "0001038683",
        "EntityRegistrantName": "Ryanair Holdings plc",
        "DocumentType": "20-F",
        "DocumentFiscalYearFocus": "2026",
        "DocumentFiscalPeriodFocus": "FY",
        "DocumentPeriodEndDate": "March 31, 2026",
        "AmendmentFlag": "false",
    }.items():
        fact = unique(
            [
                node
                for node in root.findall(".//ix:nonNumeric", NS)
                if node.get("name") == "dei:" + name and node.get("contextRef") == selected["duration"]
            ],
            "DEI " + name,
        )
        value = (
            fiscal_end_date_text(fact, selected["duration"])
            if name == "DocumentPeriodEndDate"
            else text(fact)
        )
        if (
            fact.nsmap.get("dei") != root.nsmap["dei"]
            or fact.nsmap.get("ixt") != root.nsmap["ixt"]
            or value != expected
        ):
            raise ValueError("Filing DEI identity/period mismatch: " + name)
    rows = []
    for concept, kind in METRICS.items():
        facts = [
            node
            for node in root.findall(".//ix:nonFraction", NS)
            if node.get("name") == "ifrs-full:" + concept and node.get("contextRef") == selected[kind]
        ]
        if (
            not facts
            or len({node.get("id") for node in facts}) != len(facts)
            or any(not node.get("id") for node in facts)
        ):
            raise ValueError("Missing/ambiguous fiscal fact: " + concept)
        decoded = []
        for node in facts:
            unit = unique(
                [item for item in units if item.get("id") == node.get("unitRef")], "referenced unit"
            )
            measures = unit.findall("x:measure", NS)
            raw = text(node)
            if (
                len(unit) != 1
                or len(measures) != 1
                or text(measures[0]) != "iso4217:EUR"
                or measures[0].nsmap.get("iso4217") != root.nsmap["iso4217"]
                or any(node.nsmap.get(key) != root.nsmap[key] for key in ("ifrs-full", "ixt"))
                or node.get("scale") != "6"
                or node.get("decimals") != "-5"
                or node.get("format") != "ixt:num-dot-decimal"
                or node.get("sign") not in (None, "-")
                or node.get("continuedAt")
                or node.get("{%s}nil" % "http://www.w3.org/2001/XMLSchema-instance")
                or not re.fullmatch(r"(?:0|[1-9]\d{0,2}(?:,\d{3})*)\.\d", raw)
            ):
                raise ValueError("Unreviewed fiscal EUR unit/format/precision: " + concept)
            value = Decimal(raw.replace(",", "")) * 1_000_000 * (-1 if node.get("sign") == "-" else 1)
            if abs(value) > 2**53 - 1 or (concept in {"Revenue", "Assets", "Liabilities"} and value < 0):
                raise ValueError("Invalid fiscal numeric domain: " + concept)
            decoded.append((int(value), raw, node.get("sign")))
        if len(set(decoded)) != 1:
            raise ValueError("Conflicting repeated inline facts: " + concept)
        value, raw, sign = decoded[0]
        rows.append(
            dict(
                period_id="RYANAIR_FY2026",
                period_type="fiscal_year" if kind == "duration" else "fiscal_year_end_instant",
                period_start_date="2025-04-01" if kind == "duration" else None,
                period_end_date="2026-03-31",
                metric_key="ifrs-full:" + concept,
                value=value,
                unit="EUR",
                value_raw=raw,
                source_scale=6,
                source_decimals=-5,
                source_sign=sign,
                context_id=selected[kind],
                repeated_inline_facts=len(facts),
                source_locator="inline_ids:" + ",".join(node.get("id") for node in facts),
                parser_version=VERSION,
                source_system=original["source_system"],
                source_file=original["source_file"],
                source_hash=original["sha256"],
                ingested_at=pd.Timestamp(original["downloaded_at"]),
                carrier_key="RYANAIR",
                agent_eligible=False,
            )
        )
    frame = pd.DataFrame(rows)
    values = frame.set_index("metric_key").value
    residual = int(values["ifrs-full:Assets"] - values["ifrs-full:Liabilities"] - values["ifrs-full:Equity"])
    if abs(residual) > 150_000:
        raise ValueError("Fiscal balance-sheet identity outside reported rounding")
    return frame, dict(
        rows=len(frame),
        scope="retained_SEC_FY2026_consolidated_IFRS_EUR_not_calendar_quarter_not_latest_filing",
        fiscal_year_start="2025-04-01",
        fiscal_year_end="2026-03-31",
        review_period=review_period,
        source_filing_date="2026-06-22",
        sec_accepted_at="2026-06-22T12:47:18.000Z",
        sec_filing_lag_days=(date(2026, 6, 22) - date(2026, 3, 31)).days,
        published_at=None,
        release_lag_days=None,
        first_IR_publication_verified=False,
        repeated_inline_facts_verified=sum(frame.repeated_inline_facts),
        balance_residual_EUR=residual,
        months_validated=[],
        revisions="not_compared_no_baseline",
        historical_comparatives_imported=False,
    )
