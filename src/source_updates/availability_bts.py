"""FJE release history bound to actual GET/POST ZIPs, never an operator census."""

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import pandas as pd
from bs4 import BeautifulSoup

from src.ingest.bts.t100 import FORM_URL, logical_source_url
from src.source_updates import availability as physical
from src.source_updates.bts_native import archive
from src.source_updates.calendar import local_time
from src.source_updates.catalog import bronze_aliases, load_catalog, product_map
from src.source_updates.checks import period_end

HISTORY = "https://www.transtats.bts.gov/ReleaseInfo.asp"
LABEL = "T-100 International Segment (All Carriers)"


def period(month, year):
    if not 1 <= int(month) <= 12:
        raise ValueError("Invalid BTS release month")
    return f"{year}M{int(month):02d}"


def latest(index):
    soup = BeautifulSoup(index.read_bytes(), "html.parser")
    if soup.find("base", href=True):
        raise ValueError("BTS release index base changed")
    matches = []
    for link in soup.select("a[href]"):
        url = urlsplit(urljoin(HISTORY, link["href"]))
        query = parse_qs(url.query, keep_blank_values=True)
        label = " ".join(link.get_text(" ", strip=True).split())
        named = re.search(r"T[ -]*100.*International.*Segment.*All.*Carriers", label, re.I)
        if query.get("6o") != ["FJE"] and not named:
            continue
        if (
            url.scheme != "https"
            or url.netloc != "www.transtats.bts.gov"
            or url.path.lower() != "/releaseinfo.asp"
            or query != {"6o": ["FJE"], "qv52ynB": ["qn6n"]}
            or label != LABEL
        ):
            raise ValueError("Unreviewed BTS All-Carriers International Segment release identity")
        matches.append(link)
    if len(matches) != 1:
        raise ValueError("BTS requires one exact FJE release row, not Market or US-only")
    row = matches[0].find_parent("tr")
    if row is None:
        raise ValueError("BTS release identity is outside the reviewed table")
    cells = row.find_all("td", recursive=False)
    if len(cells) != 3:
        raise ValueError("BTS release table column layout changed")
    current = " ".join(cells[1].get_text(" ", strip=True).split())
    month = re.fullmatch(r"(\d{1,2})/(20\d{2}) View reporting carriers", current)
    release = " ".join(cells[2].get_text(" ", strip=True).split())
    stamp = re.fullmatch(r"(\d{1,2}/\d{1,2}/20\d{2}): (.+)", release)
    if not month or not stamp:
        raise ValueError("BTS latest month or release event grammar changed")
    latest_period = period(month[1], month[2])
    date = datetime.strptime(stamp[1], "%m/%d/%Y").date()
    events = re.findall(r"(\d{1,2})/(20\d{2}) (added|updated)", stamp[2])
    if not events or " ".join(f"{m}/{y} {kind}" for m, y, kind in events) != stamp[2]:
        raise ValueError("Unclassified BTS release/revision event")
    added = [period(m, y) for m, y, kind in events if kind == "added"]
    if added != [latest_period]:
        raise ValueError("BTS latest available month and added-month event disagree")
    if any(period_end(period(m, y)) >= date for m, y, _ in events):
        raise ValueError("BTS announced monthly events must close before their reported release date")
    return dict(
        latest_available_period=latest_period,
        reported_release_date=date.isoformat(),
        reported_release_label=stamp[1],
        events=[dict(period=period(m, y), kind=kind) for m, y, kind in events],
    )


def response_is_form(value):
    actual, expected = urlsplit(value), urlsplit(FORM_URL)
    return (
        actual.scheme == expected.scheme
        and actual.netloc == expected.netloc
        and actual.path == expected.path
        and not actual.fragment
        and parse_qs(actual.query, keep_blank_values=True) == parse_qs(expected.query)
    )


def verify(item, result, cutoff):
    binding = item["availability"]
    root = physical.preflight(binding, item["workspace"])
    if set(binding) != physical.FIELDS:
        raise ValueError("BTS binds one annual ZIP and its official release history")
    before = physical.collection_inventory(root)
    receipt_path = root / "receipts" / f"collection-{binding['run_id']}.json"
    receipt_sha = physical.sha(receipt_path)
    receipt = json.loads(receipt_path.read_text())
    expected = dict(
        run_id=binding["run_id"],
        mode="collection",
        status="collected_unvalidated",
        activation="none",
        publication="not_authorized",
    )
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError("BTS requires a complete immutable acquisition receipt")
    hosts = load_catalog()[product_map()["bts_segments"]["source_key"]]["allowed_hosts"]
    aliases = bronze_aliases("bts_segments")

    def selected(key, status):
        rows = [row for row in receipt["items"] if row["id"] == key]
        if len(rows) != 1 or rows[0].get("product") != "bts_segments" or rows[0].get("status") != status:
            raise ValueError("BTS requires exact product-specific acquisition items")
        row = rows[0]
        path, record = physical.artifact(root, row, cutoff, hosts, receipt, aliases)
        return row, path, record

    index, index_path, index_record = selected(binding["catalog_item"], "collected_catalog")
    data, data_path, data_record = selected(binding["artifact_item"], "collected_unvalidated")
    if any(index[key] != HISTORY for key in ("source_url", "response_url")):
        raise ValueError("BTS availability requires its exact official release history URL")
    release = latest(index_path)
    latest_period = release["latest_available_period"]
    year = int(latest_period[:4])
    if (
        latest_period != item["period"]
        or data["requested_period"] != str(year)
        or data.get("request_url") != FORM_URL
        or data["source_url"] != logical_source_url(year)
        or not response_is_form(data["response_url"])
        or local_time(index_record["downloaded_at"]) > local_time(data_record["downloaded_at"])
        or release["reported_release_date"] > local_time(index_record["downloaded_at"]).date().isoformat()
    ):
        raise ValueError("BTS latest month, selected year, real form POST or release chronology disagree")
    native = pd.read_parquet(Path(item["workspace"]) / "data/silver/bts_t100_segment.parquet")
    fields = {"source_file", "source_hash", "source_system", "period_id", "year"}
    if not fields <= set(native):
        raise ValueError("BTS native observations lack physical identity or year/month")
    if (
        result.get("selected_month_observations_certified") is not True
        or result.get("complete_month_certified") is not False
        or result.get("operator_coverage_verified") is not False
        or result.get("observed_max_period") != latest_period
        or max(native.period_id) != latest_period
        or set(native.year) != {year}
        or set(native.source_file) != {data["source_file"]}
        or set(native.source_hash) != {data["sha256"]}
        or not set(native.source_system) <= set(aliases)
    ):
        raise ValueError("BTS latest ZIP does not bind its completely checked selected-month observations")
    revisions = []
    for old_year in sorted(
        {
            int(e["period"][:4])
            for e in release["events"]
            if e["kind"] == "updated" and int(e["period"][:4]) != year
        }
    ):
        rows = [r for r in receipt["items"] if r.get("source_url") == logical_source_url(old_year)]
        if len(rows) != 1:
            raise ValueError("BTS announced historical revision year requires its selected archive capture")
        row, path, record = selected(rows[0]["id"], "collected_unvalidated")
        if (
            row["requested_period"] != str(old_year)
            or row.get("request_url") != FORM_URL
            or not response_is_form(row["response_url"])
            or local_time(index_record["downloaded_at"]) > local_time(record["downloaded_at"])
        ):
            raise ValueError("BTS revised-year capture does not match its real annual form request")
        records, details = archive(path.read_bytes())
        if {r["YEAR"] for r in records} != {str(old_year)}:
            raise ValueError("BTS revised-year ZIP contains a different native year")
        revisions.append(
            dict(
                year=old_year,
                source_file=row["source_file"],
                sha256=row["sha256"],
                data_member_sha256=details["data_member_sha256"],
                comparison_status="not_compared_without_explicit_baseline",
                validation_status="physical_capture_and_archive_schema_only",
                contributes_to_selected_month=False,
            )
        )
    if physical.collection_inventory(root) != before or physical.sha(receipt_path) != receipt_sha:
        raise ValueError("BTS release discovery or capture changed during verification")
    return dict(
        collection_receipt_sha256=receipt_sha,
        official_index_sha256=index["sha256"],
        source_artifact_sha256=data["sha256"],
        latest_available_period=latest_period,
        source_availability_observed_at=data_record["downloaded_at"],
        round_as_of=cutoff,
        discovery_url=HISTORY,
        discovery_contract_product="bts_segments",
        physical_collection_files=before,
        official_release_history=release,
        historical_revision_archives=revisions,
        complete_month_certified=False,
        operator_coverage_verified=False,
        first_available_at=None,
        release_lag_days=None,
        scope="latest_reported_MX_US_segment_observations_not_complete_operator_universe",
    )
