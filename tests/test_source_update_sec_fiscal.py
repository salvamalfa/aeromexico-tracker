from __future__ import annotations

import json

import pytest

from src.source_updates import sec_fiscal as module


def specimen():
    namespaces = {
        "xbrli": module.NS["x"],
        "ix": module.NS["ix"],
        "ifrs-full": "https://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full",
        "dei": "http://xbrl.sec.gov/dei/2025",
        "iso4217": "http://www.xbrl.org/2003/iso4217",
        "ixt": "http://www.xbrl.org/inlineXBRL/transformation/2022-02-16",
    }
    parts = ["<html " + " ".join(f'xmlns:{key}="{value}"' for key, value in namespaces.items()) + ">"]
    for kind, dates in [
        (
            "duration",
            "<xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate>",
        ),
        ("instant", "<xbrli:instant>2026-03-31</xbrli:instant>"),
    ]:
        parts.append(
            f'<xbrli:context id="{kind}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0001038683</xbrli:identifier></xbrli:entity><xbrli:period>{dates}</xbrli:period></xbrli:context>'
        )
    parts.append('<xbrli:unit id="eur"><xbrli:measure>iso4217:EUR</xbrli:measure></xbrli:unit>')
    for name, value in {
        "EntityCentralIndexKey": "0001038683",
        "EntityRegistrantName": "Ryanair Holdings plc",
        "DocumentType": "20-F",
        "DocumentFiscalPeriodFocus": "FY",
        "AmendmentFlag": "false",
    }.items():
        parts.append(f'<ix:nonNumeric name="dei:{name}" contextRef="duration">{value}</ix:nonNumeric>')
    parts.append(
        '<ix:nonNumeric name="dei:DocumentPeriodEndDate" contextRef="duration" format="ixt:date-monthname-day-year-en"><ix:nonNumeric name="dei:CurrentFiscalYearEndDate" contextRef="duration" format="ixt:date-monthname-day-en">March 31</ix:nonNumeric>, <ix:nonNumeric name="dei:DocumentFiscalYearFocus" contextRef="duration">2026</ix:nonNumeric></ix:nonNumeric>'
    )
    values = {
        "Revenue": "15,544.3",
        "ProfitLoss": "2,173.7",
        "CashFlowsFromUsedInOperatingActivities": "3,694.9",
        "Assets": "19,747.7",
        "Liabilities": "9,646.3",
        "Equity": "10,101.4",
    }
    for concept, kind in module.METRICS.items():
        for n in range(2 if concept == "Revenue" else 1):
            parts.append(
                f'<ix:nonFraction id="{concept}{n}" name="ifrs-full:{concept}" contextRef="{kind}" unitRef="eur" scale="6" decimals="-5" format="ixt:num-dot-decimal">{values[concept]}</ix:nonFraction>'
            )
    parts.append("</html>")
    body = "".join(parts).encode()
    submissions = {
        "cik": "0001038683",
        "name": "RYANAIR HOLDINGS PLC",
        "fiscalYearEnd": "0331",
        "filings": {
            "recent": {
                key: [value]
                for key, value in {
                    "accessionNumber": module.ACCESSION,
                    "form": "20-F",
                    "reportDate": "2026-03-31",
                    "primaryDocument": module.DOCUMENT,
                    "filingDate": "2026-06-22",
                    "acceptanceDateTime": "2026-06-22T12:47:18.000Z",
                }.items()
            }
        },
    }
    index = {
        "directory": {"name": module.DIRECTORY, "item": [{"name": module.DOCUMENT, "size": str(len(body))}]}
    }
    meta = {
        "source_url": "https://www.sec.gov" + module.DIRECTORY + "/" + module.DOCUMENT,
        "source_system": "sec",
        "source_file": "sec/report.htm",
        "sha256": "a" * 64,
        "downloaded_at": "2026-08-24T03:14:57Z",
    }
    return {
        "html": (body, meta),
        "submissions": (json.dumps(submissions).encode(), {}),
        "index": (json.dumps(index).encode(), {}),
    }


def changed(inputs, before, after):
    body, meta = inputs["html"]
    assert before in body
    body = body.replace(before, after)
    inputs["html"] = (body, meta)
    index = json.loads(inputs["index"][0])
    index["directory"]["item"][0]["size"] = str(len(body))
    inputs["index"] = (json.dumps(index).encode(), {})
    return inputs


def test_fiscal_year_units_and_repeated_facts_are_not_calendar_quarters():
    frame, details = module.parse(specimen(), "2026Q2")
    assert len(frame) == 6
    assert frame.set_index("metric_key").loc["ifrs-full:Revenue", "value"] == 15_544_300_000
    assert frame.period_id.eq("RYANAIR_FY2026").all() and frame.unit.eq("EUR").all()
    assert frame.loc[frame.metric_key.eq("ifrs-full:Revenue"), "repeated_inline_facts"].item() == 2
    assert frame.loc[frame.period_type.eq("fiscal_year_end_instant"), "period_start_date"].isna().all()
    assert details["sec_filing_lag_days"] == 83 and details["release_lag_days"] is None
    assert details["published_at"] is None and details["balance_residual_EUR"] == 0
    assert not frame.agent_eligible.any()


@pytest.mark.parametrize(
    ("before", "after", "reason"),
    [
        (b"0001038683", b"0001520504", "entity"),
        (b"2025-04-01", b"2025-01-01", "duration"),
        (b"<xbrli:instant>2026-03-31", b"<xbrli:instant>2025-03-31", "instant"),
        (b"iso4217:EUR", b"iso4217:USD", "unit"),
        (b'scale="6"', b'scale="3"', "precision"),
        (b'decimals="-5"', b'decimals="INF"', "precision"),
        (b"ixt:num-dot-decimal", b"ixt:num-comma-decimal", "format"),
        (b"15,544.3", b"15.544,3", "format"),
        (b'name="ifrs-full:Equity"', b'name="ifrs-full:Wrong"', "Missing"),
        (b">10,101.4<", b">10,102.4<", "balance"),
        (b">FY<", b">Q1<", "DEI"),
        (b">false<", b">true<", "DEI"),
        (
            b"https://xbrl.ifrs.org/taxonomy/2025-03-27/ifrs-full",
            b"https://wrong.example/ifrs-full",
            "namespace",
        ),
        (
            b'name="ifrs-full:Revenue"',
            b'xmlns:ifrs-full="https://wrong.example/ifrs-full" name="ifrs-full:Revenue"',
            "unit/format",
        ),
        (b"<xbrli:entity>", b"<xbrli:entity><scenario/>", "structure"),
        (b"<html ", b'<!DOCTYPE html [<!ENTITY x SYSTEM "file:///etc/passwd">]><html ', "DTD"),
    ],
)
def test_wrong_entity_period_currency_scaling_dimension_identity_and_xml_block(before, after, reason):
    with pytest.raises(ValueError, match=reason):
        module.parse(changed(specimen(), before, after), "2026Q2")


def test_conflicting_repeated_fact_blocks_instead_of_first_match():
    inputs = specimen()
    body, meta = inputs["html"]
    body = body.replace(b">15,544.3<", b">15,545.3<", 1)
    inputs["html"] = (body, meta)
    with pytest.raises(ValueError, match="Conflicting"):
        module.parse(inputs, "2026Q2")


@pytest.mark.parametrize("target", ["submissions", "index"])
def test_other_filing_or_wrong_index_size_blocks(target):
    inputs = specimen()
    payload = json.loads(inputs[target][0])
    if target == "submissions":
        payload["filings"]["recent"]["accessionNumber"][0] = "another-accession"
    else:
        payload["directory"]["item"][0]["size"] = "1"
    inputs[target] = (json.dumps(payload).encode(), {})
    with pytest.raises(ValueError):
        module.parse(inputs, "2026Q2")


def test_new_review_period_requires_adaptation():
    with pytest.raises(ValueError, match="Q2 review"):
        module.parse(specimen(), "2026Q3")


@pytest.mark.parametrize("kind", ["context", "unit"])
def test_missing_ids_and_references_cannot_resolve_through_none(kind):
    inputs = specimen()
    if kind == "context":
        inputs = changed(inputs, b' id="duration"', b"")
        inputs = changed(inputs, b' contextRef="duration"', b"")
    else:
        inputs = changed(inputs, b' id="eur"', b"")
        inputs = changed(inputs, b' unitRef="eur"', b"")
    with pytest.raises(ValueError, match="identifiers"):
        module.parse(inputs, "2026Q2")


@pytest.mark.parametrize("tag", ["exclude", "continuation", "nonFraction"])
def test_nested_inline_content_is_not_imported_as_a_fiscal_value(tag):
    inputs = changed(specimen(), b">15,544.3<", ("><ix:" + tag + ">15,544.3</ix:" + tag + "><").encode())
    with pytest.raises(ValueError, match="nested inline"):
        module.parse(inputs, "2026Q2")


def test_cross_concept_fact_identifier_collision_blocks_ambiguous_locator():
    inputs = changed(specimen(), b'id="ProfitLoss0"', b'id="Revenue0"')
    with pytest.raises(ValueError, match="document-wide"):
        module.parse(inputs, "2026Q2")


def test_nested_dei_date_cannot_hide_excluded_or_different_context_text():
    inputs = changed(specimen(), b">March 31<", b"><ix:exclude>March 31</ix:exclude><")
    with pytest.raises(ValueError, match="date"):
        module.parse(inputs, "2026Q2")
