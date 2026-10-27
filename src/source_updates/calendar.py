"""Explicit Mexican banking days, evidence-bound releases and finite retries."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
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


def report_day(release: dict, as_of: str) -> date:
    """Use a reviewed issuer day without manufacturing a publication instant."""
    cutoff = local_time(as_of)
    precision = release.get("publication_precision", "timestamp")
    if precision == "day":
        value = release.get("published_on")
        if (
            release.get("published_at") is not None
            or not isinstance(value, str)
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        ):
            raise ValueError("Day precision requires published_on and a null published_at")
        day = date.fromisoformat(value)
        if day > cutoff.date():
            raise ValueError("Report day is after cutoff")
        return day
    if precision != "timestamp" or release.get("published_on") is not None:
        raise ValueError("Choose day or timestamp publication precision without conflicting dates")
    if not isinstance(release.get("published_at"), str):
        raise ValueError("Timestamp precision requires a zoned published_at")
    stamp = local_time(release["published_at"])
    if stamp > cutoff:
        raise ValueError("Report timestamp is after cutoff")
    return stamp.date()


def verify_report_evidence(release: dict, as_of: str) -> dict:
    """Verify located documentary review, independently of numerical ingestion.

    Exact passages establish their physical location. Their entity/period/day
    interpretation remains the explicit confirmed review, never machine approval.
    """
    from src.source_updates.primary_review import original, verify_evidence

    evidence = release["documentary_evidence"]
    if not isinstance(evidence, dict) or set(evidence) != {"bronze_root", "source", "passages"}:
        raise ValueError("Documentary release requires exact physical review fields")
    source, passages = evidence["source"], evidence["passages"]
    keys = {"source_file", "source_system", "source_url", "sha256", "bytes", "downloaded_at", "http_status"}
    if not isinstance(source, dict) or set(source) != keys or source["http_status"] != 200:
        raise ValueError("Documentary source requires exact identity and HTTP200")
    aliases = {"AEROMEXICO": "aeromexico_ir", "VOLARIS": "sec", "VIVA_AEROBUS": "viva_ir"}
    if source["source_system"] != aliases.get(release["entity"]) or (
        release["entity"] == "VOLARIS"
        and not re.match(r"https://www\.sec\.gov/Archives/edgar/data/1520504/", source["source_url"])
    ):
        raise ValueError("Documentary source belongs to a different financial institution")
    if (source["source_url"], source["sha256"]) != (release["document_url"], release["source_sha256"]):
        raise ValueError("Documentary release artifact identity differs")
    if release.get("publication_precision") != "day" or release.get("confirmed") is not True:
        raise ValueError("Documentary detection requires a confirmed day-precision review")
    day = report_day(release, as_of)
    captured = local_time(source["downloaded_at"])
    if captured > local_time(as_of) or day > captured.date():
        raise ValueError("Documentary release date/capture is after its evidence cutoff")
    root = Path(evidence["bronze_root"])
    path = original(root, source)
    if json.loads(Path(str(path) + ".meta.json").read_text()).get("http_status") != 200:
        raise ValueError("Documentary evidence requires a successful original capture")
    if not isinstance(passages, dict) or set(passages) != {"entity", "period", "published_on"}:
        raise ValueError("Located entity, quarter and report day are all required")
    for key, passage in passages.items():
        if (
            not isinstance(passage, dict)
            or set(passage) != {"value", "locator", "excerpt"}
            or passage["value"] != release[key]
        ):
            raise ValueError("Documentary reviewed metadata differs from release")
        verify_evidence(passage, path, {})
    return {
        "release_sha256": hashlib.sha256(
            json.dumps(release, sort_keys=True, allow_nan=False).encode()
        ).hexdigest(),
        "basis": "physically_located_confirmed_review_not_completed_numerical_ingestion",
        "published_on": day.isoformat(),
        "published_at": None,
    }


def quarterly(quarter: str, releases: list[dict], as_of: str, holidays: dict) -> dict:
    """Propose a date from reviewed reports; this never certifies their numbers."""
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
        try:
            day = report_day(release, as_of)
        except ValueError:
            continue
        if period_end < day:
            entity = release["entity"]
            latest[entity] = max(day, latest.get(entity, day))
    missing = sorted(CENTRAL - latest.keys())
    due = None if missing else add_business_days(max(latest.values()), 2, holidays).isoformat()
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
