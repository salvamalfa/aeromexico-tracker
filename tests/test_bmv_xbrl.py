from datetime import date
import hashlib
import json
from pathlib import Path
import zipfile

import polars as pl

from src.parse.bmv.derive import derive_quarters_from_ytd
from src.parse.bmv.xbrl import FACT_SCHEMA, parse_payload


FIXTURE = Path(__file__).parent / "fixtures" / "bmv" / "AERO_2026Q2.zip"
FIXTURE_HASH = "4c5b73eaf7b70d7ffc1d23964176a53d86346415544c6d8ef5afa16dbcf38fa8"


def _parsed_fixture() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == FIXTURE_HASH
    with zipfile.ZipFile(FIXTURE) as archive:
        assert archive.namelist() == ["ifrsxbrl_1573911_2026-02_1.json"]
        payload = json.loads(archive.read(archive.namelist()[0]).decode("utf-8"))
    package = {
        "carrier_key": "AEROMEXICO",
        "ticker": "AERO",
        "package_period_id": "2026Q2",
        "report_type": "quarter",
        "member_source_file": "fixture/AERO_2026Q2.json",
        "member_source_hash": FIXTURE_HASH,
        "ingested_at": "2026-08-20T00:00:00+00:00",
    }
    return parse_payload(payload, package)


def _base_value(facts: list[dict[str, object]], concept: str, start: date, end: date) -> float:
    rows = [
        row
        for row in facts
        if row["concept"] == concept
        and row["period_start_date"] == start
        and row["period_end_date"] == end
        and row["dimension_count"] == 0
    ]
    assert len(rows) == 1
    return float(rows[0]["value"])


def test_real_bmv_fixture_extracts_financial_anchors_and_presentation() -> None:
    facts, concepts = _parsed_fixture()

    assert _base_value(
        facts, "ifrs-full_Revenue", date(2026, 4, 1), date(2026, 6, 30)
    ) == 1_479_356_000
    assert _base_value(
        facts, "ifrs-full_Assets", date(2026, 6, 30), date(2026, 6, 30)
    ) == 7_379_438_000
    operating = next(
        row
        for row in facts
        if row["concept"] == "ifrs-full_ProfitLossFromOperatingActivities"
        and row["period_start_date"] == date(2026, 4, 1)
        and row["dimension_count"] == 0
    )
    assert operating["statement_type"] == "310000"
    assert operating["concept_label_es"]
    assert any(int(row["dimension_count"]) > 0 for row in facts)
    assert any(row["concept_is_extension"] for row in concepts)


def test_real_bmv_fixture_pnl_and_balance_equations_hold() -> None:
    facts, _ = _parsed_fixture()
    start, end = date(2026, 4, 1), date(2026, 6, 30)
    revenue = _base_value(facts, "ifrs-full_Revenue", start, end)
    cost = _base_value(facts, "ifrs-full_CostOfSales", start, end)
    gross = _base_value(facts, "ifrs-full_GrossProfit", start, end)
    assert revenue - cost == gross

    instant = date(2026, 6, 30)
    assets = _base_value(facts, "ifrs-full_Assets", instant, instant)
    liabilities = _base_value(facts, "ifrs-full_Liabilities", instant, instant)
    equity = _base_value(facts, "ifrs-full_Equity", instant, instant)
    assert assets == liabilities + equity


def _synthetic_fact(**updates: object) -> dict[str, object]:
    row = {column: None for column in FACT_SCHEMA}
    row.update(
        {
            "carrier_key": "VOLARIS",
            "ticker": "VOLAR",
            "package_report_type": "quarter",
            "context_period_type": "duration",
            "taxonomy": "ifrs-full",
            "taxonomy_namespace": "ifrs",
            "concept": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
            "concept_name": "CashFlowsFromUsedInOperatingActivities",
            "concept_is_extension": False,
            "dimensions_json": "[]",
            "dimension_count": 0,
            "unit_id": "usd",
            "unit": "ISO4217:USD",
            "currency": "USD",
            "decimals": "-3",
            "scale": 0,
            "statement_type": "520000",
            "is_consolidated": True,
            "is_derived": False,
            "source_system": "bmv",
            "ingested_at": "2026-01-01T00:00:00+00:00",
            "parser_version": "test",
        }
    )
    row.update(updates)
    return row


def test_ytd_derivation_creates_quarter_without_overwriting_sources() -> None:
    q1 = _synthetic_fact(
        package_period_id="2025Q1",
        fact_id="q1",
        context_id="q1",
        period_id="2025Q1",
        period_type="quarter",
        period_start_date=date(2025, 1, 1),
        period_end_date=date(2025, 3, 31),
        value=40.0,
        value_raw="40",
        is_ytd=False,
        source_file="q1.json",
        source_hash="1" * 64,
    )
    q2_ytd = _synthetic_fact(
        package_period_id="2025Q2",
        fact_id="q2ytd",
        context_id="q2ytd",
        period_id="2025Q2",
        period_type="quarter",
        period_start_date=date(2025, 1, 1),
        period_end_date=date(2025, 6, 30),
        value=100.0,
        value_raw="100",
        is_ytd=True,
        source_file="q2.json",
        source_hash="2" * 64,
    )
    frame = pl.DataFrame([q1, q2_ytd], schema=FACT_SCHEMA, strict=False)

    result = derive_quarters_from_ytd(frame)

    derived = result.filter(pl.col("is_derived"))
    assert result.height == 3
    assert derived["period_id"].to_list() == ["2025Q2"]
    assert derived["value"].to_list() == [60.0]
    assert derived["derivation_formula"].to_list() == ["Q2 = Q2_YTD - Q1_YTD"]
