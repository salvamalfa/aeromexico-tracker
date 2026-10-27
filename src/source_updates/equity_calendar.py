"""Read-only session evidence for retained equity candidates; never approve a round.

An HTTP200 JavaScript shell is a captured page, not a verified calendar. Missing
OTC evidence remains explicit: NYSE/Nasdaq are not substitutes for ICAGY.
"""

import argparse
import calendar
import hashlib
import io
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup
from pypdf import PdfReader

from src.pipeline.offline import block_network
from src.source_updates.calendar import local_time
from src.source_updates.collection import safe_workspace
from src.source_updates.retained import digest, originals
from src.source_updates.series_native import read, window

URLS = {
    "NYSE": "https://www.nyse.com/markets/hours-calendars",
    "NASDAQ": "https://www.nasdaq.com/market-activity/stock-market-holiday-schedule",
    "OTC": "https://www.otcmarkets.com/market-hours",
    "NYSE_trading_days": "https://www.nyse.com/publicdocs/Trading_Days.pdf",
}
VENUES = {"AERO": "NYSE", "VLRS": "NYSE", "DAL": "NYSE", "RYAAY": "NASDAQ", "ICAGY": "OTC"}
# Reviewed semantic edition, not a guessed holiday rule or an arbitrary user flag.
CLOSED_2026 = {
    date.fromisoformat(s)
    for s in (
        "2026-01-01 2026-01-19 2026-02-16 2026-04-03 2026-05-25 "
        "2026-06-19 2026-07-03 2026-09-07 2026-11-26 2026-12-25"
    ).split()
}
EARLY_2026 = {date(2026, 11, 27), date(2026, 12, 24)}


def sha(body):
    return hashlib.sha256(body).hexdigest()


def sessions(start, end, closed):
    return {
        start + timedelta(days=i)
        for i in range((end - start).days + 1)
        if (start + timedelta(days=i)).weekday() < 5 and start + timedelta(days=i) not in closed
    }


def physical_calendars(root, cutoff):
    root = safe_workspace(Path(root))
    manifest = root / "_manifest.jsonl"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Require physical calendar manifest")
    selected, files = {}, {"_manifest.jsonl": digest(manifest)}
    for line in manifest.read_text().splitlines():
        row = json.loads(line)
        roles = [role for role, url in URLS.items() if url == row.get("source_url")]
        if len(roles) != 1 or roles[0] in selected:
            raise ValueError("Calendar URLs/roles must be exact, unique reviewed official references")
        role = roles[0]
        extension = "pdf" if role == "NYSE_trading_days" else "html"
        period = "current" if extension == "pdf" else "2026"
        if (
            row.get("source_system") != "equity_calendar_reference"
            or row.get("logical_key") != f"equity_calendar_reference|{role}|{period}|{extension}"
            or row.get("http_status") != 200
            or row.get("download_method") != "httpx"
            or local_time(row["downloaded_at"]) > local_time(cutoff)
        ):
            raise ValueError("Calendar must bind actual public HTTP capture before cutoff")
        relative = Path(row["source_file"])
        path = root / relative
        if relative.is_absolute() or ".." in relative.parts or not path.resolve().is_relative_to(root):
            raise ValueError("Calendar file must remain inside its original root")
        sidecar = Path(str(path) + ".meta.json")
        if any(p.is_symlink() or not p.is_file() for p in (path, sidecar)):
            raise ValueError("Calendar source and sidecar must be regular physical files")
        body = path.read_bytes()
        if (
            row.get("sha256") != sha(body)
            or row.get("bytes") != len(body)
            or json.loads(sidecar.read_text()) != row
        ):
            raise ValueError("Calendar original/sidecar/manifest integrity differs")
        selected[role] = body, row
        files[relative.as_posix()] = sha(body)
        files[sidecar.relative_to(root).as_posix()] = digest(sidecar)
    return selected, files


def html_calendar(venue, body):
    if venue not in {"NYSE", "NASDAQ", "OTC"}:
        raise ValueError("Unsupported market calendar identity")
    soup = BeautifulSoup(body, "html.parser")
    text = " ".join(soup.get_text(" ", strip=True).split())
    tables = [
        [
            [" ".join(c.get_text(" ", strip=True).split()) for c in r.find_all(["th", "td"])]
            for r in t.find_all("tr")
        ]
        for t in soup.find_all("table")
    ]
    if venue == "OTC":
        # No reviewed, physically retained OTC calendar edition exists yet.
        return None
    header = ["Holiday", "2025", "2026", "2027"] if venue == "NYSE" else ["Holiday", "Date", "Market Status"]
    matches = [t for t in tables if t and t[0] == header]
    if len(matches) != 1:
        raise ValueError("Official holiday table missing or ambiguous")
    closed, early = set(), set()
    for row in matches[0][1:]:
        if len(row) != len(header):
            raise ValueError("Holiday table width changed")
        token = row[2] if venue == "NYSE" else row[1]
        if venue == "NYSE":
            match = re.fullmatch(r"([A-Za-z]+), ([A-Za-z]+ \d{1,2})\**(?: \([^)]*\))?", token)
            if not match:
                raise ValueError("NYSE 2026 date/weekday changed")
            day = datetime.strptime(match[2] + ", 2026", "%B %d, %Y").date()
            if day.strftime("%A") != match[1]:
                raise ValueError("NYSE weekday inconsistent with date")
            target = closed
        else:
            day = datetime.strptime(token, "%B %d, %Y").date()
            if row[2] not in {"Closed", "1:00 p.m."}:
                raise ValueError("Nasdaq closure/early-close status changed")
            target = closed if row[2] == "Closed" else early
        if day in closed | early:
            raise ValueError("Duplicate or contradictory holiday date")
        target.add(day)
    if venue == "NYSE":
        if "All NYSE markets observe U.S. holidays" not in text:
            raise ValueError("NYSE calendar scope changed")
        for day in EARLY_2026:
            token = f"{day.strftime('%A, %B')} {day.day}, {day.year}"
            if token not in text:
                raise ValueError("NYSE early-close session note missing")
        early = EARLY_2026.copy()
    elif "Nasdaq trading hours are as follows, Monday through Friday:" not in text:
        raise ValueError("Nasdaq weekday schedule missing")
    if closed != CLOSED_2026 or early != EARLY_2026:
        raise ValueError("Official holiday semantic edition changed; review rather than infer dates")
    return {"closed": closed, "early": early}


def nyse_counts(body, closed):
    text = PdfReader(io.BytesIO(body)).pages[0].extract_text(extraction_mode="layout")
    if "Trading days: 2026 Estimated" not in text or "US Cash Equities, US Equity Options" not in text:
        raise ValueError("NYSE trading-days PDF year/asset-class changed")
    section = text.split("Trading days: 2026 Estimated", 1)[1].split("Trading days: 2027", 1)[0]
    counts = {}
    for line in section.splitlines():
        match = re.fullmatch(
            r"\s*([A-Z][a-z]{2})\s+(\d+)(?:\s+\d+)?\s+\1\s+(\d+)(?:\s+\d+)?\s+\1\s+\d+(?:\s+\d+)?\s*", line
        )
        if match:
            m = list(calendar.month_abbr).index(match[1])
            if m in counts:
                raise ValueError("Duplicate NYSE monthly session count")
            counts[m] = int(match[3])
    expected = {
        m: len(sessions(date(2026, m, 1), date(2026, m, calendar.monthrange(2026, m)[1]), closed))
        for m in range(1, 13)
    }
    if counts != expected:
        raise ValueError("NYSE cash-equity count differs from weekday/holiday calendar")
    return {
        "source_label": "2026 Estimated",
        "asset_class": "US Cash Equities, US Equity Options",
        "monthly_session_counts": counts,
    }


def assess(frame, period, calendars):
    start, end, _ = window(period)
    if end.year != 2026 or set(frame.ticker) != set(VENUES):
        raise ValueError("Require all five exact tickers and the reviewed calendar year 2026")
    results = {}
    for ticker, venue in VENUES.items():
        selected = frame.loc[frame.ticker.eq(ticker)]
        if (
            selected.date.dt.tz is not None
            or selected.date.ne(selected.date.dt.normalize()).any()
            or selected.date.duplicated().any()
        ):
            raise ValueError("Market dates must be unique native New York daily labels")
        schedule = calendars.get(venue)
        observed = set(
            selected.loc[
                selected.date.between(pd.Timestamp(date(2026, 1, 1)), pd.Timestamp(end)), "date"
            ].dt.date
        )
        if schedule is None:
            results[ticker] = {
                "venue": venue,
                "complete": False,
                "reason": "official_calendar_evidence_pending",
                "observed_YTD_count": len(observed),
                "calendar_inferred_from_other_venue_or_quotes": False,
            }
            continue
        expected = sessions(date(2026, 1, 1), end, schedule["closed"])
        current = {d for d in expected if d >= start}
        # Thirty returns require today's price plus thirty preceding prices.
        previous = sorted(d for d in expected if d < start)
        history_in_this_calendar = len(previous) >= 30
        warmup = history_in_this_calendar and set(previous[-30:]) <= observed
        results[ticker] = {
            "venue": venue,
            "expected_YTD_count": len(expected),
            "observed_YTD_count": len(observed),
            "expected_period_count": len(current),
            "observed_period_count": len({d for d in observed if d >= start}),
            "missing_dates": sorted(d.isoformat() for d in expected - observed),
            "unexpected_dates": sorted(d.isoformat() for d in observed - expected),
            "expected_return_YTD_anchor": min(expected).isoformat(),
            "return_YTD_anchor_verified": min(expected) in observed,
            "prior_prices_for_30_return_warmup_verified": warmup,
            "prior_year_calendar_required": not history_in_this_calendar,
            "early_closes_are_sessions": True,
            "complete": expected == observed and warmup,
            "calendar_inferred_from_other_venue_or_quotes": False,
        }
    return {
        "period": period,
        "series": results,
        "calendar_completeness_certified": all(r["complete"] for r in results.values()),
    }


def validate_candidate_receipt(item, receipt, retention_hash, native_hash):
    expected = {
        "version": 1,
        "status": "checks_passed",
        "product": "equities",
        "period": item["period"],
        "retention_run_id": item["receipt_id"],
        "effective_as_of": item["candidate_as_of"],
        "activation": "none",
        "publication": "not_authorized",
        "retention_receipt_sha256": retention_hash,
    }
    if (
        any(receipt.get(k) != v for k, v in expected.items())
        or receipt.get("output_sha256", {}).get("silver/market_prices") != native_hash
    ):
        raise ValueError("Native prices must bind the exact retained candidate product/period/cutoff/receipt")


def run(recipe, calendar_root, cutoff):
    selected, inventory = physical_calendars(calendar_root, cutoff)
    calendars, evidence = {}, {}
    for venue in ("NYSE", "NASDAQ", "OTC"):
        if venue not in selected:
            continue
        body, row = selected[venue]
        calendars[venue] = html_calendar(venue, body)
        evidence[venue] = {
            k: row[k] for k in ("source_url", "source_file", "sha256", "downloaded_at", "http_status")
        }
        evidence[venue]["calendar_verified"] = calendars[venue] is not None
    if calendars.get("NYSE"):
        if "NYSE_trading_days" not in selected:
            raise ValueError("NYSE requires its linked cash-equity session-count PDF")
        body, row = selected["NYSE_trading_days"]
        evidence["NYSE_trading_days"] = {
            "sha256": row["sha256"],
            "source_url": row["source_url"],
            **nyse_counts(body, calendars["NYSE"]["closed"]),
        }
    items = [i for i in recipe["items"] if i["product"] == "equities"]
    if (
        recipe.get("version") != 1
        or len(items) != 2
        or len({i["id"] for i in items}) != 2
        or {i.get("cadence") for i in items} != {"monthly", "quarterly"}
        or any(i.get("adapter") != "series" or i["period"] != recipe[i["cadence"] + "_period"] for i in items)
    ):
        raise ValueError("Select the exact monthly and quarterly equity candidates")
    results = {}
    for item in items:
        workspace = safe_workspace(Path(item["workspace"]))
        if window(item["period"])[1] >= local_time(cutoff).date() or local_time(
            item["candidate_as_of"]
        ) > local_time(cutoff):
            raise ValueError("Equity session proof requires a closed observation window")
        inputs, receipt_sha = originals(workspace, "equities", item["receipt_id"], item["candidate_as_of"])
        silver, _ = read("equities", inputs, item["period"])
        path = workspace / "data/silver/market_prices.parquet"
        pd.testing.assert_frame_equal(pd.read_parquet(path), silver["market_prices"], check_exact=True)
        accepted = workspace / "receipts" / f"series-equities-{item['period']}.json"
        receipt = json.loads(accepted.read_text())
        validate_candidate_receipt(item, receipt, receipt_sha, digest(path))
        native_hash, accepted_hash = digest(path), digest(accepted)
        results[item["id"]] = {
            **assess(silver["market_prices"], item["period"], calendars),
            "native_prices_sha256": native_hash,
            "existing_product_receipt_sha256": accepted_hash,
            "existing_product_receipt_recertified_here": False,
        }
        # Recheck retained bytes/sidecars and receipts after native reconstruction.
        _, after_receipt_sha = originals(workspace, "equities", item["receipt_id"], item["candidate_as_of"])
        if (
            after_receipt_sha != receipt_sha
            or digest(path) != native_hash
            or digest(accepted) != accepted_hash
        ):
            raise ValueError("Retained candidate changed during session verification")
    _, after = physical_calendars(calendar_root, cutoff)
    if after != inventory:
        raise ValueError("Physical calendar inputs changed during read-only verification")
    return {
        "version": 1,
        "scope": "standalone_session_assessment_not_global_round_acceptance",
        "checker_code_files": {
            name: digest(Path(__file__).with_name(name))
            for name in (
                "equity_calendar.py",
                "series_native.py",
                "market.py",
                "retained.py",
                "retained_registry.py",
                "checks.py",
                "collection.py",
                "calendar.py",
            )
        },
        "as_of": cutoff,
        "timezone": "America/New_York",
        "calendar_sources": evidence,
        "calendar_files": inventory,
        "results": results,
        "all_five_instruments_complete": all(r["calendar_completeness_certified"] for r in results.values()),
        "network_requests": 0,
        "activation": "none",
        "publication": "not_authorized",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--calendar-root", type=Path, required=True)
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        local_time(args.as_of)
        recipe = json.loads(args.recipe.read_text())
        if args.execute:
            with block_network():
                result = run(recipe, args.calendar_root, args.as_of)
        else:
            result = {
                "mode": "dry_run",
                "calendar_urls": URLS,
                "periods": [recipe["monthly_period"], recipe["quarterly_period"]],
                "network_requests": 0,
                "activation": "none",
                "publication": "not_authorized",
            }
    except (ValueError, KeyError, OSError, TypeError, AssertionError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
