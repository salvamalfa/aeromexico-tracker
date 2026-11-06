#!/usr/bin/env python3
"""Calculate deterministic AMR query, departure, return, and URL dates."""

from __future__ import annotations

import argparse
import calendar
import json
from datetime import date, datetime, timedelta


SHEET_DATE = "%d/%m/%Y"


def parse_sheet_date(value: str) -> date:
    return datetime.strptime(value, SHEET_DATE).date()


def add_calendar_months(value: date, months: int) -> date:
    if months < 0:
        raise ValueError("months must be nonnegative")
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def calculate(query_date: date, months: int, shift_days: int = 0) -> dict[str, object]:
    if shift_days not in (0, 1):
        raise ValueError("shift_days must be 0 or 1")

    base_departure = add_calendar_months(query_date, months)
    base_return = base_departure + timedelta(days=7)
    departure = base_departure + timedelta(days=shift_days)
    return_date = base_return + timedelta(days=shift_days)

    return {
        "query_date": query_date.strftime(SHEET_DATE),
        "months": months,
        "date_shift_days": shift_days,
        "base_departure_date": base_departure.strftime(SHEET_DATE),
        "base_return_date": base_return.strftime(SHEET_DATE),
        "departure_date": departure.strftime(SHEET_DATE),
        "return_date": return_date.strftime(SHEET_DATE),
        "departure_url_date": departure.isoformat(),
        "return_url_date": return_date.isoformat(),
    }


def self_test() -> None:
    cases = [
        (date(2026, 8, 2), 6, date(2027, 2, 2)),
        (date(2026, 8, 31), 6, date(2027, 2, 28)),
        (date(2027, 8, 31), 6, date(2028, 2, 29)),
        (date(2026, 1, 31), 1, date(2026, 2, 28)),
        (date(2028, 2, 29), 12, date(2029, 2, 28)),
    ]
    for query, months, expected in cases:
        actual = add_calendar_months(query, months)
        assert actual == expected, (query, months, actual, expected)

    base = calculate(date(2026, 8, 31), 6, 0)
    shifted = calculate(date(2026, 8, 31), 6, 1)
    assert base["departure_date"] == "28/02/2027"
    assert base["return_date"] == "07/03/2027"
    assert shifted["departure_date"] == "01/03/2027"
    assert shifted["return_date"] == "08/03/2027"
    print(json.dumps({"ok": True, "tests": len(cases) + 4}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query-date", help="DD/MM/YYYY")
    parser.add_argument("--months", type=int, choices=(1, 3, 6))
    parser.add_argument("--shift-days", type=int, choices=(0, 1), default=0)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return
    if args.query_date is None or args.months is None:
        parser.error("--query-date and --months are required")

    print(json.dumps(calculate(parse_sheet_date(args.query_date), args.months, args.shift_days)))


if __name__ == "__main__":
    main()
