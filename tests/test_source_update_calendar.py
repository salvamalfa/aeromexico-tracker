"""Calendar semantics and bounded retry proposals, without live sources."""

import json
from datetime import date

import pytest

from src.source_updates import calendar
from src.source_updates.catalog import FAMILIES, ROOT, load_catalog, plan, product_map


@pytest.fixture
def holidays():
    return json.loads((ROOT / "config/source_update_holidays.json").read_text())


def test_monthly_holiday_weekend_and_no_unverified_year(holidays):
    assert calendar.monthly(2026, 8, holidays) == date(2026, 8, 17)
    assert calendar.monthly(2026, 11, holidays) == date(2026, 11, 17)
    assert calendar.monthly(2026, 10, holidays) == date(2026, 10, 15)
    assert calendar.roll_forward(date(2026, 11, 2), holidays) == date(2026, 11, 3)
    with pytest.raises(ValueError, match="Unverified"):
        calendar.monthly(2027, 1, holidays)


def releases():
    # Synthetic scheduling fixture. These are NOT assertions about actual releases.
    return [
        {
            "entity": entity,
            "period": "2026Q3",
            "published_at": "2026-10-30T23:00:00Z",
            "kind": "financial_report",
            "confirmed": True,
            "document_url": "https://example.test/report",
        }
        for entity in calendar.CENTRAL
    ]


def test_quarterly_two_strictly_later_business_days_and_local_zone(holidays):
    result = calendar.quarterly("2026Q3", releases(), "2026-11-01T00:00:00Z", holidays)
    assert result["date"] == "2026-11-04"  # Friday report; Monday Nov 2 is bank holiday.
    assert calendar.local_time("2026-11-01T02:00:00Z").date() == date(2026, 10, 31)


@pytest.mark.parametrize("change", ["missing", "announcement", "unconfirmed", "future", "different_quarter"])
def test_quarterly_unknown_dates_are_not_invented(holidays, change):
    records = releases()
    if change == "missing":
        records.pop()
    elif change == "announcement":
        records[0]["kind"] = "earnings_call"
    elif change == "unconfirmed":
        records[0]["confirmed"] = False
    elif change == "future":
        records[0]["published_at"] = "2026-11-02T12:00:00-06:00"
    else:
        records[0]["period"] = "2026Q2"
    assert calendar.quarterly("2026Q3", records, "2026-11-01T00:00:00Z", holidays)["date"] is None


@pytest.mark.parametrize(("quarter_date", "expected_count"), [("2026-10-22", 1), ("2026-10-23", 2)])
def test_combine_uses_inclusive_seven_natural_days(quarter_date, expected_count):
    rounds = [{"kind": "monthly", "date": "2026-10-15"}, {"kind": "quarterly", "date": quarter_date}]
    result = calendar.combine(rounds)
    assert len(result) == expected_count
    if len(result) == 1:
        assert result[0]["date"] == quarter_date
        assert result[0]["kind"] == "combined"


def test_retries_are_proposals_with_a_two_reschedule_limit(holidays):
    result = calendar.retry_date(today=date(2026, 10, 30), attempts=0, reason="technical", holidays=holidays)
    assert result["date"] == "2026-11-03"
    assert (
        calendar.retry_date(today=date(2026, 10, 30), attempts=2, reason="unknown", holidays=holidays)[
            "status"
        ]
        == "blocked_for_decision"
    )


def test_catalogue_all_sources_have_unique_family_and_products():
    sources = load_catalog()
    assert len(sources) == 29
    assert set(sources) == {key for keys in FAMILIES.values() for key in keys}
    assert {row["source_key"] for row in product_map().values()} == set(sources)
    assert not any("aerodatabox" in key for key in product_map())


def test_plan_is_source_collection_not_gold_freshness():
    result = plan("monthly", "2026-10-18T12:00:00Z")
    assert result["network_requests"] == 0 and result["writes"] == []
    assert {"rss", "gdelt"} <= {row["id"] for row in result["products"]}
    assert all(row["target_period"] == "2026M09" for row in result["products"])
    assert all(row["latest_validated_period"] is None for row in result["products"])
    quarterly = plan("quarterly", "2026-10-18T12:00:00Z", "2026Q3")
    assert not {"rss", "gdelt"} & {row["id"] for row in quarterly["products"]}
    assert {"anac", "aerocivil", "caa"} <= {row["id"] for row in quarterly["products"]}


def test_cannot_plan_unclosed_quarter():
    with pytest.raises(ValueError, match="not closed"):
        plan("quarterly", "2026-10-18T12:00:00Z", "2026Q4")
