"""Independent scheduling counterexamples; no asserted real release dates."""

import json
from copy import deepcopy

import pytest

from src.source_updates import calendar
from src.source_updates.catalog import ROOT


@pytest.fixture
def holidays():
    return json.loads((ROOT / "config/source_update_holidays.json").read_text())


def reports(published_at="2026-10-30T23:00:00Z"):
    return [
        {
            "entity": entity,
            "period": "2026Q3",
            "kind": "financial_report",
            "confirmed": True,
            "document_url": "https://example.test/synthetic-report.pdf",
            "published_at": published_at,
        }
        for entity in sorted(calendar.CENTRAL)
    ]


@pytest.mark.parametrize("quarter", ["2026Q0", "2026Q5", "2026M09", "Q3", "bad"])
def test_quarterly_rejects_invalid_requested_period(quarter, holidays):
    with pytest.raises(ValueError, match="YYYYQn"):
        calendar.quarterly(quarter, [], "2026-11-01T00:00:00Z", holidays)


def test_quarterly_cannot_schedule_before_target_quarter_closes(holidays):
    with pytest.raises(ValueError, match="not closed"):
        calendar.quarterly("2026Q3", reports("2026-06-01T12:00:00Z"), "2026-07-01T12:00:00Z", holidays)


@pytest.mark.parametrize("stamp", ["2026-06-01T12:00:00Z", "2026-09-30T23:00:00-06:00"])
def test_financial_report_inside_or_before_period_is_not_actual_quarter_release(stamp, holidays):
    result = calendar.quarterly("2026Q3", reports(stamp), "2026-11-01T00:00:00Z", holidays)
    assert result["date"] is None
    assert result["missing_central_reports"] == sorted(calendar.CENTRAL)


@pytest.mark.parametrize(
    "url",
    [
        "https://",
        "https:///report.pdf",
        "https://user:pass@example.test/report.pdf",
        "https://example.test:8080/report.pdf",
        "https://example.test/report.pdf#unverified-fragment",
        "https://example.test:bad/report.pdf",
    ],
)
def test_report_needs_a_public_well_formed_document_url(url, holidays):
    releases = reports()
    releases[0]["document_url"] = url
    result = calendar.quarterly("2026Q3", releases, "2026-11-01T00:00:00Z", holidays)
    assert result["date"] is None
    assert result["available_entities"] == [row["entity"] for row in releases[1:]]


def test_combination_preserves_target_periods_does_not_mutate_and_never_chains():
    rounds = [
        {"kind": "monthly", "date": "2026-10-15", "period": "2026M09"},
        {"kind": "quarterly", "date": "2026-10-22", "period": "2026Q3"},
        {"kind": "quarterly", "date": "2026-10-29", "period": "2026Q2"},
    ]
    original = deepcopy(rounds)
    result = calendar.combine(rounds)
    assert rounds == original
    assert len(result) == 2
    assert result[0]["date"] == "2026-10-22"
    assert [member["period"] for member in result[0]["members"]] == ["2026M09", "2026Q3"]
    assert result[1] == rounds[2]
