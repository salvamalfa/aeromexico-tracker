"""Synthetic contracts; real retained originals are exercised separately offline."""

import json
import shutil
from copy import deepcopy
from datetime import date
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates import equity_calendar as subject
from src.source_updates.catalog import ROOT


def calendar_html(venue):
    if venue == "NYSE":
        header = "<tr><th>Holiday</th><th>2025</th><th>2026</th><th>2027</th></tr>"
        rows = "".join(
            f"<tr><td>Fixture holiday</td><td>unused</td><td>{d.strftime('%A, %B')} {d.day}"
            "</td><td>unused</td></tr>"
            for d in sorted(subject.CLOSED_2026)
        )
        note = (
            "All NYSE markets observe U.S. holidays; Friday, November 27, 2026; Thursday, December 24, 2026"
        )
    else:
        header = "<tr><th>Holiday</th><th>Date</th><th>Market Status</th></tr>"
        rows = "".join(
            f"<tr><td>Fixture holiday</td><td>{d.strftime('%B')} {d.day}, 2026</td><td>{status}</td></tr>"
            for days, status in [(subject.CLOSED_2026, "Closed"), (subject.EARLY_2026, "1:00 p.m.")]
            for d in sorted(days)
        )
        note = "Nasdaq trading hours are as follows, Monday through Friday:"
    return f"<html><p>{note}</p><table>{header}{rows}</table></html>".encode()


def prices():
    days = sorted(subject.sessions(date(2026, 1, 1), date(2026, 12, 31), subject.CLOSED_2026))
    return pd.DataFrame(
        [(t, pd.Timestamp(d)) for t in subject.VENUES for d in days], columns=["ticker", "date"]
    )


def calendars():
    return {
        venue: {"closed": subject.CLOSED_2026, "early": subject.EARLY_2026}
        for venue in set(subject.VENUES.values())
    }


def test_semantic_editions_and_early_closes_are_sessions():
    for venue in ["NYSE", "NASDAQ"]:
        proof = subject.html_calendar(venue, calendar_html(venue))
        assert proof == {"closed": subject.CLOSED_2026, "early": subject.EARLY_2026}
        november = subject.sessions(date(2026, 11, 1), date(2026, 11, 30), proof["closed"])
        assert date(2026, 11, 26) not in november and date(2026, 11, 27) in november
    assert subject.html_calendar("OTC", b"<html>You need to enable JavaScript</html>") is None
    # Even an otherwise valid NYSE table cannot certify a different venue.
    assert subject.html_calendar("OTC", calendar_html("NYSE")) is None


def test_changed_or_ambiguous_official_calendar_fails():
    for venue in ["NYSE", "NASDAQ"]:
        body = calendar_html(venue)
        for changed in [
            body.replace(b"September 7", b"September 8"),
            body + body,
            body.replace(b"<th>Holiday", b"<th>Other"),
        ]:
            with pytest.raises(ValueError):
                subject.html_calendar(venue, changed)
    with pytest.raises(ValueError, match="status changed"):
        subject.html_calendar("NASDAQ", calendar_html("NASDAQ").replace(b"1:00 p.m.", b"Closed early"))


def test_both_periods_include_ytd_and_return_warmup_without_inventing_otc():
    frame, schedules = prices(), calendars()
    for period, count in [("2026M09", 21), ("2026Q3", 64)]:
        proof = subject.assess(frame, period, schedules)
        assert proof["calendar_completeness_certified"]  # Synthetic complete contract only.
        assert all(
            r["expected_period_count"] == count and r["expected_YTD_count"] == 187
            for r in proof["series"].values()
        )
        assert all(
            r["expected_return_YTD_anchor"] == "2026-01-02" and r["return_YTD_anchor_verified"]
            for r in proof["series"].values()
        )
        schedules_without_otc = {k: v for k, v in schedules.items() if k != "OTC"}
        incomplete = subject.assess(frame, period, schedules_without_otc)
        assert not incomplete["calendar_completeness_certified"]
        assert sum(r["complete"] for r in incomplete["series"].values()) == 4
        assert incomplete["series"]["ICAGY"]["reason"] == "official_calendar_evidence_pending"
        assert not incomplete["series"]["ICAGY"]["calendar_inferred_from_other_venue_or_quotes"]


def test_equal_counts_wrong_dates_and_hidden_history_gaps_are_rejected():
    schedules = calendars()
    for omitted in ["2026-09-08", "2026-08-31", "2026-01-02"]:
        frame = prices()
        frame = frame.loc[~(frame.ticker.eq("AERO") & frame.date.eq(omitted))]
        result = subject.assess(frame, "2026M09", schedules)["series"]
        assert not result["AERO"]["complete"]
        assert result["AERO"]["missing_dates"] == [omitted]
        assert result["RYAAY"]["complete"]
        if omitted == "2026-08-31":
            assert not result["AERO"]["prior_prices_for_30_return_warmup_verified"]
            assert not result["AERO"]["prior_year_calendar_required"]
        if omitted == "2026-01-02":
            assert not result["AERO"]["return_YTD_anchor_verified"]
    frame = prices()
    frame.loc[frame.ticker.eq("AERO") & frame.date.eq("2026-09-08"), "date"] = pd.Timestamp("2026-09-07")
    result = subject.assess(frame, "2026M09", schedules)["series"]["AERO"]
    assert result["expected_period_count"] == result["observed_period_count"] == 21
    assert not result["complete"] and result["unexpected_dates"] == ["2026-09-07"]
    holiday_anchor = pd.concat(
        [prices(), pd.DataFrame([{"ticker": "AERO", "date": pd.Timestamp("2026-01-01")}])]
    )
    anchor = subject.assess(holiday_anchor, "2026M09", schedules)["series"]["AERO"]
    assert not anchor["complete"] and not anchor["return_YTD_anchor_verified"]
    assert not subject.assess(prices(), "2026M01", schedules)["calendar_completeness_certified"]


def test_domain_unique_native_dates_and_year_are_not_tolerances():
    frame = prices()
    bad = [frame.loc[frame.ticker.ne("ICAGY")], pd.concat([frame, frame.iloc[[0]]])]
    non_native = frame.copy()
    non_native["date"] = non_native.date.map(lambda stamp: stamp.replace(hour=1))
    bad.append(non_native)
    aware = frame.copy()
    aware["date"] = aware.date.dt.tz_localize("UTC")
    bad.append(aware)
    for changed in bad:
        with pytest.raises(ValueError):
            subject.assess(changed, "2026M09", calendars())
    with pytest.raises(ValueError, match="year 2026"):
        subject.assess(frame, "2027M09", calendars())


def test_existing_receipt_must_bind_status_identity_window_and_retention():
    item = dict(period="2026M09", receipt_id="a" * 32, candidate_as_of="2026-10-27T18:00:00+00:00")
    receipt = dict(
        version=1,
        status="checks_passed",
        product="equities",
        period=item["period"],
        retention_run_id=item["receipt_id"],
        effective_as_of=item["candidate_as_of"],
        activation="none",
        publication="not_authorized",
        retention_receipt_sha256="a" * 64,
        output_sha256={"silver/market_prices": "b" * 64},
    )
    subject.validate_candidate_receipt(item, receipt, "a" * 64, "b" * 64)
    for key, value in [
        ("status", "blocked"),
        ("product", "fuel"),
        ("period", "2026Q3"),
        ("retention_run_id", "c" * 32),
        ("effective_as_of", "2099-01-01T00:00:00+00:00"),
        ("retention_receipt_sha256", "c" * 64),
        ("activation", "active"),
        ("output_sha256", {"silver/market_prices": "c" * 64}),
    ]:
        bad = deepcopy(receipt)
        bad[key] = value
        with pytest.raises(ValueError, match="exact retained candidate"):
            subject.validate_candidate_receipt(item, bad, "a" * 64, "b" * 64)


def test_run_rejects_duplicate_ids_and_mismatched_period_or_adapter(monkeypatch):
    monkeypatch.setattr(subject, "physical_calendars", lambda *_: ({}, {}))
    recipe = {
        "version": 1,
        "monthly_period": "2026M09",
        "quarterly_period": "2026Q3",
        "items": [
            dict(id=c, product="equities", adapter="series", cadence=c, period=p)
            for c, p in [("monthly", "2026M09"), ("quarterly", "2026Q3")]
        ],
    }
    for field, value in [
        ("id", "monthly"),
        ("cadence", "monthly"),
        ("adapter", "retained"),
        ("period", "2026Q2"),
    ]:
        bad = deepcopy(recipe)
        bad["items"][1][field] = value
        with pytest.raises(ValueError, match="exact monthly and quarterly"):
            subject.run(bad, Path("unused"), "2026-10-27T19:00:00+00:00")


@pytest.fixture
def originals():
    root = ROOT / "tmp/source-updates" / ("test-equity-calendar-" + uuid4().hex)
    save_bronze(
        calendar_html("NYSE"),
        "equity_calendar_reference",
        "NYSE",
        "2026",
        "html",
        subject.URLS["NYSE"],
        "httpx",
        bronze_root=root,
        http_status=200,
    )
    try:
        yield root
    finally:
        shutil.rmtree(root)


def test_physical_binding_rejects_corruption_url_capture_role_and_sidecar(originals):
    root = originals
    manifest = root / "_manifest.jsonl"
    original = manifest.read_text()
    row = json.loads(original)
    selected, before = subject.physical_calendars(root, "2099-01-01T00:00:00+00:00")
    assert selected["NYSE"][0] == calendar_html("NYSE") and len(before) == 3
    for key, value in [
        ("source_url", subject.URLS["NYSE"] + "?other=1"),
        ("http_status", 503),
        ("source_system", "yahoo_finance"),
        ("logical_key", "equity_calendar_reference|OTC|2026|html"),
        ("download_method", "manual"),
        ("sha256", "0" * 64),
        ("source_file", "../outside.html"),
    ]:
        bad = deepcopy(row)
        bad[key] = value
        manifest.write_text(json.dumps(bad) + "\n")
        with pytest.raises(ValueError):
            subject.physical_calendars(root, "2099-01-01T00:00:00+00:00")
    manifest.write_text(original)
    with pytest.raises(ValueError, match="before cutoff"):
        subject.physical_calendars(root, "2020-01-01T00:00:00+00:00")
    source = root / row["source_file"]
    source.write_bytes(b"modified")
    with pytest.raises(ValueError, match="integrity"):
        subject.physical_calendars(root, "2099-01-01T00:00:00+00:00")
