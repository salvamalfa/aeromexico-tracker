from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.config import PATHS
from src.ingest.airports import groups
from src.ingest.airports.reference import OPERATOR_AIRPORTS, operator_group
from src.ingest.news.rss_gdelt import _parse_rss
from src.transform.stage4 import EVENTS, _complete_business_calendar


FIXTURES = Path(__file__).parent / "fixtures" / "stage4"
DUMMY_LINEAGE = {
    "source_file": "airports/fixture.html",
    "source_hash": "0" * 64,
    "ingested_at": pd.Timestamp("2026-08-20", tz="UTC"),
    "parser_version": "stage4_v1.0.0",
}


def test_operator_groups_have_unique_airport_codes() -> None:
    codes = [code for values in OPERATOR_AIRPORTS.values() for code in values]
    assert len(codes) == len(set(codes))
    assert operator_group("MEX") == "GOVERNMENT"
    assert operator_group("CUN") == "ASUR"
    assert operator_group("MTY") == "OMA"


def test_asur_parser_extracts_current_and_comparison_period(monkeypatch) -> None:
    monkeypatch.setattr(groups, "lineage", lambda _: DUMMY_LINEAGE)
    rows = groups._parse_asur(
        (FIXTURES / "asur_sample.html").read_bytes(), FIXTURES / "asur_sample.html"
    )
    totals = {row["period_id"]: row for row in rows if row["is_group_total"]}
    assert totals["2025M06"]["passengers_total"] == 300
    assert totals["2026M06"]["passengers_domestic"] == 210
    airport = next(row for row in rows if row["airport_iata"] == "CUN" and row["period_id"] == "2026M06")
    assert airport["passengers_total"] == 225


def test_gap_parser_scales_thousands(monkeypatch) -> None:
    monkeypatch.setattr(groups, "lineage", lambda _: DUMMY_LINEAGE)
    rows = groups._parse_gap(
        (FIXTURES / "gap_sample.html").read_bytes(), FIXTURES / "gap_sample.html"
    )
    airport = next(row for row in rows if row["airport_iata"] == "GDL" and row["period_id"] == "2026M05")
    assert airport["passengers_total"] == 170_000
    assert airport["passengers_international"] == 60_000


def test_aicm_parser_selects_current_year_columns() -> None:
    text = "ENERO 2,252,082 1,463,026 3,715,108 2,218,147 1,545,153 3,763,300 -1.5 5.6 1.3"
    assert groups._aicm_current_values(text)[1] == (2_218_147, 1_545_153, 3_763_300)


def test_aifa_monthly_block_extracts_seven_months() -> None:
    frame = pd.DataFrame([[None, None, month, i, i + 1, i * 2 + 1] for i, month in enumerate(
        ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO", "JULIO"], start=1
    )])
    result = groups._aifa_monthly_block(frame)
    assert len(result) == 7
    assert result[7] == (7.0, 8.0, 15.0)


def test_aifa_year_comes_from_header_not_later_values() -> None:
    frame = pd.DataFrame([[None, None] for _ in range(12)])
    frame.iloc[1, 0] = "NUMERALIA AEROPORTUARIA 2026"
    frame.iloc[11, 1] = 2041
    assert groups._aifa_publication_year(frame) == 2026


def test_business_calendar_flags_but_does_not_hide_fills() -> None:
    source = pd.DataFrame(
        {"date": pd.to_datetime(["2026-08-17", "2026-08-19"]), "value": [1.0, 3.0]}
    )
    result = _complete_business_calendar(source, "value")
    filled = result.loc[result["date"].eq(pd.Timestamp("2026-08-18"))].iloc[0]
    assert filled["value"] == 1.0
    assert not bool(filled["is_published"])
    assert filled["fill_method"] == "prior_published_value"


def test_rss_fixture_preserves_headline_lineage(monkeypatch) -> None:
    import src.ingest.news.rss_gdelt as module

    monkeypatch.setattr(module, "lineage", lambda _: DUMMY_LINEAGE)
    rows = _parse_rss(FIXTURES / "rss_sample.xml", "google_en")
    assert rows[0]["title"] == "Aeromexico test headline"
    assert rows[0]["source_system"] == "rss"


def test_curated_events_meet_minimum_and_have_urls() -> None:
    assert len(EVENTS) >= 15
    assert all(str(event[-1]).startswith("https://") for event in EVENTS)


@pytest.mark.parametrize(
    "filename,required_columns",
    [
        ("fx_rates.parquet", {"date", "currency_pair", "rate_close", "source_system", "source_hash"}),
        ("fuel_prices.parquet", {"date", "price_usd_per_gallon", "source_system", "source_hash"}),
        ("market_prices.parquet", {"date", "ticker", "close", "source_system", "source_hash"}),
        ("airport_traffic.parquet", {"period_id", "airport_iata", "passengers_total", "source_system", "source_hash"}),
        ("news_headlines.parquet", {"published_at", "title", "url", "source_system", "source_hash"}),
    ],
)
def test_stage4_silver_contracts(filename: str, required_columns: set[str]) -> None:
    path = PATHS.silver / filename
    if not path.exists():
        pytest.skip("Stage 4 local data artifacts are intentionally not versioned")
    assert required_columns <= set(pd.read_parquet(path).columns)
