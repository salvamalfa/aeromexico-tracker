"""The sampling plan decides both the bill and whether the seed is any good.

A sample spread across the month covers every day of the week; a run of
consecutive days does not, and carrier mix moves with the weekly schedule.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.ingest.aerodatabox.__main__ import day_weights, main, month_days, plan


def test_a_whole_month_is_every_day_of_it() -> None:
    days = month_days("2026M07")
    assert len(days) == 31
    assert days[0] == date(2026, 7, 1) and days[-1] == date(2026, 7, 31)


def test_february_length_follows_the_calendar() -> None:
    assert len(month_days("2026M02")) == 28
    assert len(month_days("2024M02")) == 29


@pytest.mark.parametrize("period_id", ["2026M07", "2026M02", "2026M04", "2024M02"])
def test_a_seven_day_sample_covers_every_weekday_once(period_id: str) -> None:
    """The whole point of sampling days: no weekday may be over-represented."""

    days = month_days(period_id, sample=7)
    assert len(days) == len(set(days)) == 7
    assert len({day.weekday() for day in days}) == 7
    assert days == sorted(days)


@pytest.mark.parametrize("sample", [4, 7, 10, 14])
def test_a_sample_is_spread_across_the_month_not_consecutive(sample: int) -> None:
    days = month_days("2026M07", sample=sample)
    assert len(days) == len(set(days)) == sample
    assert max(days).day - min(days).day > sample, "concentrado en días seguidos"


def test_a_sample_larger_than_the_month_is_just_the_month() -> None:
    assert month_days("2026M02", sample=60) == month_days("2026M02")


def test_the_plan_matches_the_measured_unit_cost() -> None:
    """Two windows a day at two units a call -- both measured against the API."""

    assert plan(airports=58, days=30) == 6_960
    assert plan(airports=58, days=7) == 1_624


def test_dry_run_spends_nothing_and_reports_the_cost(capsys: pytest.CaptureFixture) -> None:
    assert main(["2026M07", "--dry-run"]) == 0
    assert "7,192 unidades" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Weekday weighting: what lets a sampled week stand in for a whole month.
# --------------------------------------------------------------------------

@pytest.mark.parametrize("period_id,length", [("2026M07", 31), ("2026M02", 28),
                                              ("2024M02", 29), ("2026M04", 30)])
def test_the_weights_of_a_sampled_week_sum_to_the_whole_month(
    period_id: str, length: int
) -> None:
    """The scaled-up sample has to represent the month, not merely resemble it."""

    days = month_days(period_id, sample=7)
    assert sum(day_weights(period_id, days).values()) == pytest.approx(length)


def test_a_full_month_weights_every_day_at_one() -> None:
    days = month_days("2026M07")
    assert set(day_weights("2026M07", days).values()) == {1.0}


def test_a_long_month_weights_its_extra_weekdays_more() -> None:
    """July 2026 starts on a Wednesday, so Wed/Thu/Fri occur five times."""

    days = month_days("2026M07", sample=7)
    weights = {day.strftime("%a"): w for day, w in day_weights("2026M07", days).items()}
    assert weights["Wed"] == weights["Thu"] == weights["Fri"] == 5.0
    assert weights["Sat"] == weights["Sun"] == weights["Mon"] == weights["Tue"] == 4.0


def test_weighting_corrects_a_weekday_that_was_sampled_twice() -> None:
    """Two Mondays must share one Monday's worth of weight, not double it."""

    days = [date(2026, 7, 6), date(2026, 7, 13)]     # ambos lunes
    weights = day_weights("2026M07", days)
    assert sum(weights.values()) == pytest.approx(4.0)
    assert set(weights.values()) == {2.0}
