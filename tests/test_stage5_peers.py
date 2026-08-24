from __future__ import annotations

import pytest

from src.parse.peers.stage5 import (
    _delta_period_from_url,
    _inline_xbrl_quarter_value,
    _period_from_earnings_text,
    _ryanair_fiscal_id,
)
from src.parse.profiles import load_profile
from src.parse.sec.earnings_release import specs_from_profile


@pytest.mark.parametrize(
    ("carrier_key", "cik"),
    [
        ("AEROMEXICO", "0001561861"),
        ("VOLARIS", "0001520504"),
        ("RYANAIR", "0001038683"),
        ("DELTA", "0000027904"),
        ("VIVA_AEROBUS", None),
    ],
)
def test_carrier_profiles_are_valid(carrier_key: str, cik: str | None) -> None:
    profile = load_profile(carrier_key)

    assert profile.carrier_key == carrier_key
    assert profile.cik == cik
    assert profile.metric_patterns


def test_sec_earnings_parser_accepts_declarative_profile() -> None:
    profile = load_profile("VOLARIS")
    specs = specs_from_profile(profile)

    assert {spec.metric_key for spec in specs} == {
        metric.metric_key for metric in profile.metric_patterns
    }
    revenue = next(spec for spec in specs if spec.metric_key == "total_revenue")
    assert revenue.table_name == "financial"


def test_peer_periods_are_derived_from_source_evidence() -> None:
    assert _period_from_earnings_text("Ticker: VLRS Quarter: 2 Year: 2025") == "2025Q2"
    assert (
        _delta_period_from_url(
            "https://www.sec.gov/Archives/edgar/data/27904/filing/dal-20250630.htm"
        )
        == "2025Q2"
    )
    assert _delta_period_from_url("https://example.com/dal-20251231.htm") is None


def test_ryanair_fiscal_calendar_boundary() -> None:
    assert _ryanair_fiscal_id(2025, 3) == "FY2025Q4"
    assert _ryanair_fiscal_id(2025, 4) == "FY2026Q1"


def test_delta_inline_xbrl_uses_consolidated_quarter_context() -> None:
    content = b"""
    <html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"
          xmlns:xbrli="http://www.xbrl.org/2003/instance">
      <xbrli:context id="consolidated">
        <xbrli:entity><xbrli:identifier scheme="cik">27904</xbrli:identifier></xbrli:entity>
        <xbrli:period>
          <xbrli:startDate>2025-04-01</xbrli:startDate>
          <xbrli:endDate>2025-06-30</xbrli:endDate>
        </xbrli:period>
      </xbrli:context>
      <xbrli:context id="segment">
        <xbrli:entity>
          <xbrli:identifier scheme="cik">27904</xbrli:identifier>
          <xbrli:segment><xbrli:explicitMember>Passenger</xbrli:explicitMember></xbrli:segment>
        </xbrli:entity>
        <xbrli:period>
          <xbrli:startDate>2025-04-01</xbrli:startDate>
          <xbrli:endDate>2025-06-30</xbrli:endDate>
        </xbrli:period>
      </xbrli:context>
      <ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="consolidated"
                      scale="6" sign="-">289</ix:nonFraction>
      <ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="segment"
                      scale="6">40</ix:nonFraction>
    </html>
    """

    assert _inline_xbrl_quarter_value(content, "NetIncomeLoss", "2025Q2") == -289.0
