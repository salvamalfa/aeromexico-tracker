"""Exact retained GAP SEC snapshot, never current availability or a new capture."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

import pandas as pd
from bs4 import BeautifulSoup

from src.source_updates.calendar import local_time
from src.source_updates.collection import safe_workspace

SCOPE = "gap_sec_submissions_snapshot_v1"
DAY = "2026-08-20"
HISTORICAL_AS_OF = "2026-08-20T18:20:00-06:00"
PERIOD = "2026M07"
CIK = "1347557"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK0001347557.json"
SELECTED = "0001171843-26-005269"
LATER = "0001171843-26-005334"
PRIMARY = {SELECTED: "f6k_080526.htm", LATER: "f6k_080626.htm"}
# This precise primary was read in full. Its title alone is not a classifier;
# acceptance additionally requires the official complete filing inventory.
NON_TRAFFIC_SHA = "db4a4003d41bf46bc8d0b3ef3291b80d49b0d33425a7b1241de1d0c92942d3e8"
FIELDS = {"source_scope", "historical", "snapshot_day", "workspace", "submissions", "filings"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative(value):
    if not isinstance(value, str) or not value or Path(value).is_absolute() or ".." in Path(value).parts:
        raise ValueError("GAP dossier requires exact relative Bronze paths")
    return Path(value)


def preflight(binding, candidate):
    if (
        not isinstance(binding, dict)
        or set(binding) != FIELDS
        or binding["source_scope"] != SCOPE
        or binding["historical"] is not True
        or binding["snapshot_day"] != DAY
    ):
        raise ValueError("GAP discovery requires its explicit historical20Aug2026 snapshot scope")
    if not isinstance(binding["workspace"], str):
        raise ValueError("GAP dossier workspace must be explicit")
    root, candidate = safe_workspace(Path(binding["workspace"])), safe_workspace(Path(candidate))
    if root == candidate or root.is_relative_to(candidate) or candidate.is_relative_to(root):
        raise ValueError("GAP discovery dossier and source candidate must be disjoint")
    relative(binding["submissions"])
    filings = binding["filings"]
    if not isinstance(filings, dict) or set(filings) != set(PRIMARY):
        raise ValueError("GAP snapshot requires the selected filing and every later6K")
    paths = [binding["submissions"]]
    for accession, filing in filings.items():
        if not isinstance(filing, dict) or set(filing) != {"index", "documents"}:
            raise ValueError("Each GAP filing requires its official directory index and document map")
        relative(filing["index"])
        documents = filing["documents"]
        if not isinstance(documents, dict) or PRIMARY[accession] not in documents:
            raise ValueError("Each GAP filing needs its exact primary document")
        for name, path in documents.items():
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                raise ValueError("Unsafe SEC filing document name")
            relative(path)
        paths.extend([filing["index"], *documents.values()])
    if len(paths) != len(set(paths)):
        raise ValueError("GAP dossier roles cannot borrow one physical artifact")
    return root


def base_url(accession):
    return f"https://www.sec.gov/Archives/edgar/data/{CIK}/{accession.replace('-', '')}/"


def physical(root, name, url, cutoff, records):
    bronze = root / "data/bronze"
    path = bronze / relative(name)
    if not path.is_file() or any(p.is_symlink() for p in [path, *path.parents] if p != bronze.parent):
        raise ValueError(f"GAP official dossier artifact missing or unsafe: {name}")
    matches = [r for r in records if r.get("source_file") == name]
    if len(matches) != 1:
        raise ValueError("GAP artifact needs one exact manifest record")
    row = matches[0]
    sidecar = Path(str(path) + ".meta.json")
    if sidecar.is_symlink() or json.loads(sidecar.read_text(encoding="utf-8")) != row:
        raise ValueError("GAP manifest/sidecar identity mismatch")
    if (
        row.get("source_system") not in {"sec", "sec_edgar", "sec_filing"}
        or row.get("source_url") != url
        or row.get("http_status") != 200
        or row.get("download_method") != "httpx"
        or type(row.get("bytes")) is not int
        or row["bytes"] != path.stat().st_size
        or not isinstance(row.get("sha256"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])
        or row["sha256"] != sha(path)
    ):
        raise ValueError("GAP physical source is not its exact successful official capture")
    stamp = local_time(row["downloaded_at"])
    if stamp.date().isoformat() != DAY or stamp > local_time(cutoff):
        raise ValueError("GAP original does not belong to the reviewed historical capture day/cutoff")
    return path, row


def filing_rows(payload, cutoff):
    if str(payload.get("cik")).lstrip("0") != CIK or payload.get("name") != "Pacific Airport Group":
        raise ValueError("GAP submissions issuer/CIK mismatch")
    filings = payload.get("filings", {})
    recent = filings.get("recent", {})
    columns = ("accessionNumber", "filingDate", "reportDate", "form", "primaryDocument")
    if filings.get("files") != [] or not all(isinstance(recent.get(k), list) for k in columns):
        raise ValueError("GAP submissions history is incomplete or has unreviewed pagination")
    size = len(recent["accessionNumber"])
    if not 1 <= size <= 5000 or any(len(recent[k]) != size for k in columns):
        raise ValueError("GAP submissions columns are incomplete")
    rows = [
        dict(zip(columns, values, strict=True)) for values in zip(*(recent[k] for k in columns), strict=True)
    ]
    for row in rows:
        if (
            any(not isinstance(row[k], str) for k in columns)
            or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", row["accessionNumber"])
            or date.fromisoformat(row["filingDate"]).isoformat() != row["filingDate"]
            or row["filingDate"] > local_time(cutoff).date().isoformat()
            or row["form"].upper().startswith("6-K")
            and row["form"] not in {"6-K", "6-K/A"}
        ):
            raise ValueError("Unreviewed GAP submissions identity/date/form")
    if len({r["accessionNumber"] for r in rows}) != size:
        raise ValueError("Duplicate SEC accession in GAP snapshot")
    selected = [r for r in rows if r["accessionNumber"] == SELECTED]
    if len(selected) != 1 or selected[0]["filingDate"] != "2026-08-06":
        raise ValueError("Selected GAP July filing is absent or changed")
    relevant = [r for r in rows if r["form"] in {"6-K", "6-K/A"} and r["filingDate"] >= "2026-08-06"]
    if {r["accessionNumber"] for r in relevant} != set(PRIMARY):
        raise ValueError("All later6K must be physically classified; unknown filings block")
    for row in relevant:
        if (
            row["form"] != "6-K"
            or row["primaryDocument"] != PRIMARY[row["accessionNumber"]]
            or row["filingDate"] > DAY
        ):
            raise ValueError("GAP primary identity or historical filing chronology changed")
    return relevant


def complete_filing(root, accession, entry, cutoff, records, discovery_stamp):
    base = base_url(accession)
    index, index_record = physical(root, entry["index"], base + "index.json", cutoff, records)
    payload = json.loads(index.read_text(encoding="utf-8"))
    directory = payload.get("directory", {})
    if (
        directory.get("name") != urlsplit(base).path.rstrip("/")
        or directory.get("parent-dir") != f"/Archives/edgar/data/{CIK}"
    ):
        raise ValueError("GAP filing directory CIK/accession mismatch")
    items = directory.get("item")
    if not isinstance(items, list) or not items or len(items) > 100:
        raise ValueError("Official complete filing directory is absent or oversized")
    names = [item.get("name") for item in items if isinstance(item, dict)]
    # SEC's structured directory view supplies the complete file-name inventory:
    # https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
    # These three accession-specific SEC-generated index/header/full-submission
    # containers are listed, not claimed as downloaded issuer documents. The
    # provider inventory contains exactly one substantive document in this scope.
    containers = {accession + suffix for suffix in ("-index-headers.html", "-index.html", ".txt")}
    if (
        len(names) != len(items)
        or len(set(names)) != len(names)
        or set(names) != containers | set(entry["documents"])
    ):
        raise ValueError(
            "Every substantive filing member needs physical evidence; unclassified annexes block"
        )
    if any(item.get("type") != "text.gif" for item in items):
        raise ValueError("Unreviewed SEC directory layout; icon type is not a document classification")
    if any(item.get("size") != "" for item in items if item["name"] in containers):
        raise ValueError("Reviewed SEC-generated container metadata changed")
    # This reviewed layout is a single inline primary report. Additional members
    # cannot be classified from their filename, extension, or management title.
    if set(names) - containers != {PRIMARY[accession]} or set(entry["documents"]) != {PRIMARY[accession]}:
        raise ValueError("Unknown filing annex/document needs source review before no-traffic classification")
    path, row = physical(
        root, entry["documents"][PRIMARY[accession]], base + PRIMARY[accession], cutoff, records
    )
    size = next(item.get("size") for item in items if item["name"] == PRIMARY[accession])
    if not isinstance(size, str) or not re.fullmatch(r"[1-9]\d*", size) or int(size) != path.stat().st_size:
        raise ValueError("Official GAP filing directory size differs from the physical primary bytes")
    if not discovery_stamp <= local_time(index_record["downloaded_at"]) <= local_time(row["downloaded_at"]):
        raise ValueError("GAP discovery/index/document chronology is not verified")
    # An exact primary hash does not excuse a missing filing directory or links.
    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    if soup.find("base", href=True) or soup.find(["iframe", "object", "embed", "script", "img", "link"]):
        raise ValueError("GAP primary contains unreviewed external document content")
    if soup.find("a", href=True):
        raise ValueError("GAP primary links to an unclassified additional document")
    return path, row, index_record


def closed_bronze(root, binding):
    """Only the five reviewed originals and their metadata may enter this dossier."""
    bronze = root / "data/bronze"
    expected = {binding["submissions"]}
    for filing in binding["filings"].values():
        expected.update([filing["index"], *filing["documents"].values()])
    manifest = bronze / "_manifest.jsonl"
    if manifest.is_symlink():
        raise ValueError("GAP dossier manifest must be physical")
    records = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    if (
        len(expected) != 5
        or len(records) != 5
        or any(not isinstance(row, dict) or not isinstance(row.get("source_file"), str) for row in records)
        or {row["source_file"] for row in records} != expected
    ):
        raise ValueError("GAP Bronze manifest must contain exactly five distinct reviewed originals")
    paths = list(bronze.rglob("*"))
    if any(p.is_symlink() or not (p.is_file() or p.is_dir()) for p in paths):
        raise ValueError("GAP Bronze cannot contain symlinks or unclassified special entries")
    physical_files = {p.relative_to(bronze).as_posix() for p in paths if p.is_file()}
    if physical_files != expected | {name + ".meta.json" for name in expected} | {"_manifest.jsonl"}:
        raise ValueError(
            "GAP Bronze physical inventory must match its five originals and five sidecars exactly"
        )
    return records


def verify(item, result, cutoff):
    binding = item["availability"]
    root = preflight(binding, item["workspace"])
    if item["product"] != "gap_traffic" or item["adapter"] != "airport_group" or item["period"] != PERIOD:
        raise ValueError("GAP historical availability only supports reviewed July2026")
    if local_time(cutoff) != local_time(HISTORICAL_AS_OF):
        raise ValueError("GAP historical snapshot cannot verify another round date or current availability")
    from src.source_updates.availability import collection_inventory

    records = closed_bronze(root, binding)
    before = collection_inventory(root)
    source, discovery = physical(root, binding["submissions"], SUBMISSIONS, cutoff, records)
    relevant = filing_rows(json.loads(source.read_text(encoding="utf-8")), cutoff)
    missing = [a for a in PRIMARY if not (root / "data/bronze" / binding["filings"][a]["index"]).is_file()]
    if missing:
        raise ValueError(f"Complete official GAP filing directory indexes missing: {sorted(missing)}")
    verified = {}
    for row in relevant:
        accession = row["accessionNumber"]
        verified[accession] = complete_filing(
            root,
            accession,
            binding["filings"][accession],
            cutoff,
            records,
            local_time(discovery["downloaded_at"]),
        )
    path, selected, _ = verified[SELECTED]
    _, later, _ = verified[LATER]
    if later["sha256"] != NON_TRAFFIC_SHA:
        raise ValueError("Later GAP6K has no reviewed complete non-traffic classification")
    native = pd.read_parquet(Path(item["workspace"]) / "data/silver/airport_group_native.parquet")
    if (
        result.get("status") != "checks_passed"
        or result.get("complete_month_certified") is not True
        or not {"source_file", "source_hash", "source_system", "operator_group"} <= set(native)
        or native.empty
        or set(native.source_file) != {selected["source_file"]}
        or set(native.source_hash) != {selected["sha256"]}
        or set(native.source_system) != {selected["source_system"]}
        or set(native.operator_group) != {"GAP"}
        or sha(path) != selected["sha256"]
        or collection_inventory(root) != before
        or closed_bronze(root, binding) != records
    ):
        raise ValueError("GAP historical discovery does not bind the exact fully certified native bytes")
    return {
        "historical": True,
        "source_scope": SCOPE,
        "snapshot_day": DAY,
        "latest_available_period": PERIOD,
        "round_as_of": cutoff,
        "current_availability_verified": False,
        "source_availability_observed_at": discovery["downloaded_at"],
        "official_index_sha256": discovery["sha256"],
        "source_artifact_sha256": selected["sha256"],
        "filing_indexes_sha256": {a: v[2]["sha256"] for a, v in verified.items()},
        "SEC_generated_containers": "index_headers_index_html_and_complete_submission_listed_not_downloaded",
        "later6K_classification": {
            LATER: {
                "sha256": later["sha256"],
                "classification": "reviewed_management_inline_primary_complete_directory",
            }
        },
        "physical_retained_dossier_files": before,
        "new_capture": False,
        "network_requests": 0,
        "activation": "none",
    }
