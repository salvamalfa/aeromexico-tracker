"""Read the official OTC table from a native browser snapshot, without executing it."""

import os
import re
from datetime import date, datetime
from email import policy
from email.parser import BytesParser
from email.utils import parsedate_to_datetime

from bs4 import BeautifulSoup

from src.source_updates.calendar import local_time

URL = "https://www.otcmarkets.com/market-hours"
HOLIDAYS = {
    "New Year's Day": "January 1",
    "Martin Luther King, Jr. Day": "January 19",
    "Presidents' Day": "February 16",
    "Good Friday": "April 3",
    "Memorial Day": "May 25",
    "Juneteenth National Independence Day": "June 19",
    "Independence Day*": "July 3",
    "Labor Day": "September 7",
    "Thanksgiving Day*": "November 26*",
    "Christmas": "December 25*",
}
NORMAL = "Normal Market Hours: Monday through Friday 9:30 A.M. to 4:00 P.M. ET"
EARLY = (
    "*Early closings, at 2PM, are observed for the day after Thanksgiving, "
    "the day before Independence Day and Christmas Eve if they do not occur on a weekend."
)


def rendered_html(body, record, path, cutoff):
    if len(body) > 2_000_000:
        raise ValueError("OTC snapshot is outside the reviewed native browser format")
    message = BytesParser(policy=policy.default).parsebytes(body)
    observed = parsedate_to_datetime(message["Date"])
    if (
        not message.is_multipart()
        or message.get_content_type() != "multipart/related"
        or message.get("Snapshot-Content-Location") != URL
        or observed.tzinfo is None
        or local_time(observed.isoformat()) != local_time(record["downloaded_at"])
        or local_time(observed.isoformat()) > local_time(cutoff)
        or record.get("source_representation") != "native_browser_mhtml"
        or record.get("is_raw_http_response") is not False
        or record.get("http_status") is not None
        or record.get("download_method") != "browser_mhtml"
        or not re.fullmatch(r"libfile_[a-f0-9]{32}", str(record.get("library_file_id", "")))
        or os.getxattr(path, "user.library-file-id", follow_symlinks=False).decode()
        != record["library_file_id"]
    ):
        raise ValueError("OTC native snapshot origin, chronology, Library identity or method differs")
    roots = [
        part
        for part in message.walk()
        if part.get_content_type() == "text/html" and part.get("Content-Location") == URL
    ]
    if len(roots) != 1:
        raise ValueError("OTC snapshot must contain one exact official root document")
    # Ignore advertising frames, scripts and other parts. No resource is executed or fetched.
    return roots[0].get_payload(decode=True)


def html_calendar(body):
    soup = BeautifulSoup(body, "html.parser")
    tables = [
        [
            [" ".join(c.get_text(" ", strip=True).split()) for c in r.find_all(["th", "td"])]
            for r in t.find_all("tr")
        ]
        for t in soup.find_all("table")
    ]
    matches = [t for t in tables if t and t[0] == ["", "2026", "2027"]]
    if not matches:
        return None  # A JavaScript shell or another venue's table cannot certify OTC.
    if len(matches) != 1 or len(matches[0]) != 11:
        raise ValueError("OTC holiday table is incomplete or ambiguous")
    rows = matches[0][1:]
    if any(len(row) != 3 for row in rows) or {r[0]: r[1] for r in rows} != HOLIDAYS:
        raise ValueError("OTC 2026 holiday labels, dates or duplicate rows changed")
    text = " ".join(soup.get_text(" ", strip=True).split())
    if (
        NORMAL not in text
        or EARLY not in text
        or "OTC Markets Group observes the following holidays:" not in text
    ):
        raise ValueError("OTC normal market hours, venue or early-close rule missing")
    closed = {
        datetime.strptime(token.rstrip("*") + ", 2026", "%B %d, %Y").date() for token in HOLIDAYS.values()
    }
    # Partial trading days remain sessions. July 3 is already a full observed holiday.
    early = {date(2026, 7, 3), date(2026, 11, 27), date(2026, 12, 24)} - closed
    return dict(
        closed=closed,
        early=early,
        timezone="America/New_York",
        normal_hours="09:30–16:00",
        early_close_hours="14:00",
        year=2026,
        early_close_rule=EARLY,
        other_years_certified=False,
    )
