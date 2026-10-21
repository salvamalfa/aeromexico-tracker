"""Explicit Mexican banking days, evidence-bound releases and finite retries."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("America/Mexico_City")
CENTRAL = frozenset({"AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"})


def local_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires an explicit timezone")
    return parsed.astimezone(ZONE)


def business_day(day: date, holidays: dict) -> bool:
    year = holidays["years"].get(str(day.year))
    if year is None:
        raise ValueError(f"Unverified banking calendar for {day.year}; supply official holidays first")
    return day.weekday() < 5 and day.isoformat() not in year["dates"]


def roll_forward(day: date, holidays: dict) -> date:
    while not business_day(day, holidays):
        day += timedelta(days=1)
    return day


def add_business_days(day: date, count: int, holidays: dict) -> date:
    if count < 1:
        raise ValueError("Business-day offset must be positive")
    while count:
        day += timedelta(days=1)
        if business_day(day, holidays):
            count -= 1
    return day


def monthly(year: int, month: int, holidays: dict) -> date:
    return roll_forward(date(year, month, 15), holidays)


def quarterly(quarter: str, releases: list[dict], as_of: str, holidays: dict) -> dict:
    """Announcements/calls do not stand in for a published central financial report."""
    cutoff = local_time(as_of)
    if not isinstance(quarter, str) or not re.fullmatch(r"\d{4}Q[1-4]", quarter):
        raise ValueError("Quarterly rounds need an explicit YYYYQn period")
    last_month = date(int(quarter[:4]), int(quarter[-1]) * 3, 1)
    next_month = (last_month.replace(day=28) + timedelta(days=4)).replace(day=1)
    if next_month > cutoff.date():
        raise ValueError("Cannot schedule a quarter that has not closed by the cutoff")
    period_end = next_month - timedelta(days=1)
    latest = {}
    for release in releases:
        if (
            release.get("period") != quarter
            or release.get("entity") not in CENTRAL
            or release.get("kind") != "financial_report"
            or release.get("confirmed") is not True
        ):
            continue
        # This verifies public URL syntax, not issuer authenticity or report
        # content. `confirmed` remains an explicit evidence-review assertion.
        # Reuse acquisition's credential/HTTPS guard without making a request.
        from src.source_updates.collection import validate_url

        try:
            url = release.get("document_url", "")
            validate_url(url, [urlsplit(url).hostname or ""])
        except (TypeError, ValueError):
            continue
        stamp = local_time(release["published_at"])
        if period_end < stamp.date() and stamp <= cutoff:
            entity = release["entity"]
            latest[entity] = max(stamp, latest.get(entity, stamp))
    missing = sorted(CENTRAL - latest.keys())
    due = None if missing else add_business_days(max(latest.values()).date(), 2, holidays).isoformat()
    return {
        "period": quarter,
        "date": due,
        "missing_central_reports": missing,
        "status": "waiting_for_reports" if missing else "dated",
        "available_entities": sorted(latest),
    }


def combine(rounds: list[dict]) -> list[dict]:
    """Pair a quarterly round to the nearest monthly within <=7 calendar days.

    No transitive clusters: a combined round never postpones an original >7 days.
    Input order breaks ties; a monthly round is consumed at most once.
    """
    output = [dict(item) for item in rounds]
    used = set()
    for qi, quarter in enumerate(output):
        if quarter.get("kind") != "quarterly" or not quarter.get("date"):
            continue
        candidates = []
        for mi, month in enumerate(output):
            if mi in used or month.get("kind") != "monthly" or not month.get("date"):
                continue
            distance = abs((date.fromisoformat(quarter["date"]) - date.fromisoformat(month["date"])).days)
            if distance <= 7:
                candidates.append((distance, mi))
        if candidates:
            _, mi = min(candidates)
            month = output[mi]
            output[qi] = {
                "kind": "combined",
                "date": max(quarter["date"], month["date"]),
                "members": [month, quarter],
            }
            used.add(mi)
    return sorted(
        (item for i, item in enumerate(output) if i not in used), key=lambda item: item.get("date") or "9999"
    )


def retry_date(
    *, today: date, attempts: int, reason: str, holidays: dict, announced_date: date | None = None
) -> dict:
    if attempts < 0:
        raise ValueError("attempts must be non-negative")
    if attempts >= 2:
        return {"status": "blocked_for_decision", "date": None, "reschedules": attempts}
    if reason == "announced":
        if announced_date is None or announced_date < today:
            raise ValueError("A future official release date is required")
        due = add_business_days(announced_date, 2, holidays)
    elif reason == "technical":
        due = add_business_days(today, 1, holidays)
    elif reason == "unknown":
        due = today + timedelta(days=7)
        while due > today and not business_day(due, holidays):
            due -= timedelta(days=1)
        if due == today:
            due = monthly(today.year, today.month, holidays)
            if due <= today:
                next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
                due = monthly(next_month.year, next_month.month, holidays)
    else:
        raise ValueError("reason must be announced, technical or unknown")
    return {"status": "proposed_only", "date": due.isoformat(), "reschedules": attempts + 1}
