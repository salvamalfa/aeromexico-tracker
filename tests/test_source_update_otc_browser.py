"""Synthetic native-format contracts; the real Library capture is checked separately."""

import os
import shutil
from datetime import date
from email.message import EmailMessage
from uuid import uuid4

import pytest

from src.source_updates import availability, equity_calendar, otc_calendar
from src.source_updates.catalog import ROOT


def table():
    # Independent literal fixture: public calendar facts, not the captured browser file.
    rows = [
        ("New Year's Day", "January 1"),
        ("Martin Luther King, Jr. Day", "January 19"),
        ("Presidents' Day", "February 16"),
        ("Good Friday", "April 3"),
        ("Memorial Day", "May 25"),
        ("Juneteenth National Independence Day", "June 19"),
        ("Independence Day*", "July 3"),
        ("Labor Day", "September 7"),
        ("Thanksgiving Day*", "November 26*"),
        ("Christmas", "December 25*"),
    ]
    return (
        "<html>OTC Markets Group observes the following holidays: "
        "Normal Market Hours: Monday through Friday 9:30 A.M. to 4:00 P.M. ET"
        "<table><tr><th></th><th>2026</th><th>2027</th></tr>"
        + "".join(
            f"<tr><td>{label}</td><td>{day}</td><td>not certified here</td></tr>" for label, day in rows
        )
        + "</table>"
        "*Early closings, at 2PM, are observed for the day after Thanksgiving, "
        "the day before Independence Day and Christmas Eve if they do not occur on a weekend.</html>"
    )


def archive(html, *, location=otc_calendar.URL, duplicate=False):
    message = EmailMessage()
    message["Date"] = "Wed, 28 Oct 2026 23:35:23 +0000"
    message["Snapshot-Content-Location"] = location
    message.make_related()
    for loc, text in [(otc_calendar.URL, html), ("https://irrelevant.invalid/frame", "<p>Ignored</p>")]:
        part = EmailMessage()
        part.set_content(text, subtype="html")
        part["Content-Location"] = loc
        message.attach(part)
        if duplicate and loc == otc_calendar.URL:
            message.attach(part)
    return message.as_bytes()


@pytest.fixture
def source():
    root = ROOT / "tmp/source-updates" / ("test-otc-native-" + uuid4().hex)
    root.mkdir()
    path = root / "synthetic.mhtml"
    path.write_bytes(archive(table()))
    identity = "libfile_" + "a" * 32
    os.setxattr(path, "user.library-file-id", identity.encode())
    record = dict(
        downloaded_at="2026-10-28T23:35:23Z",
        download_method="browser_mhtml",
        http_status=None,
        source_representation="native_browser_mhtml",
        is_raw_http_response=False,
        library_file_id=identity,
    )
    yield path, record
    shutil.rmtree(root)


def test_otc_own_table_has_full_closures_and_partial_sessions_without_certifying_2027():
    proof = otc_calendar.html_calendar(table().encode())
    assert len(proof["closed"]) == 10 and date(2026, 7, 3) in proof["closed"]
    assert proof["timezone"] == "America/New_York" and proof["early_close_hours"] == "14:00"
    assert proof["normal_hours"] == "09:30–16:00" and not proof["other_years_certified"]
    assert proof["early"] == {date(2026, 11, 27), date(2026, 12, 24)}
    sessions = equity_calendar.sessions(date(2026, 11, 26), date(2026, 11, 27), proof["closed"])
    assert sessions == {date(2026, 11, 27)}
    for changed in (
        table().replace("January 19", "January 20"),
        table().replace("2PM", "1PM"),
        table().replace("<td>December 25*</td>", ""),
        table() + table(),
    ):
        with pytest.raises(ValueError):
            otc_calendar.html_calendar(changed.encode())
    assert otc_calendar.html_calendar(b"<html>Enable JavaScript</html>") is None


def test_native_snapshot_reads_only_exact_root_and_preserves_unknown_HTTP(source):
    path, record = source
    raw = path.read_bytes()
    result = otc_calendar.rendered_html(raw, record, path, "2026-10-28T23:40:00Z")
    assert otc_calendar.html_calendar(result)["year"] == 2026
    assert path.read_bytes() == raw and record["http_status"] is None
    for change in (
        {"download_method": "httpx"},
        {"http_status": 200},
        {"is_raw_http_response": True},
        {"downloaded_at": "2026-10-29T23:35:23Z"},
        {"library_file_id": "libfile_" + "b" * 32},
    ):
        with pytest.raises(ValueError):
            otc_calendar.rendered_html(raw, {**record, **change}, path, "2026-10-29T23:40:00Z")
    with pytest.raises(ValueError):
        otc_calendar.rendered_html(raw, record, path, "2026-10-28T23:34:00Z")
    for altered in (archive(table(), location="https://wrong.invalid"), archive(table(), duplicate=True)):
        with pytest.raises(ValueError):
            otc_calendar.rendered_html(altered, record, path, "2026-10-28T23:40:00Z")


def test_supplemental_binding_has_all_five_equities_and_disjoint_physical_inputs(source):
    path, _ = source
    binding = dict(
        workspace=str(path.parent / "collection"),
        run_id="a" * 32,
        series_items={k: k for k in ["AERO", "VLRS", "RYAAY", "DAL", "ICAGY"]},
        equity_calendar_root=str(path.parent / "calendar"),
    )
    candidate = str(path.parent / "candidate")
    assert availability.preflight(binding, candidate) == path.parent / "collection"
    for changed in (
        {**binding, "series_items": {"ICAGY": "ICAGY"}},
        {**binding, "equity_calendar_root": binding["workspace"]},
        {**binding, "equity_calendar_root": candidate},
    ):
        with pytest.raises(ValueError):
            availability.preflight(changed, candidate)
    with pytest.raises(ValueError, match="only"):
        equity_calendar.verify_task(
            dict(product="fuel", adapter="series"), path.parent, "2026-10-28T23:40:00Z"
        )
