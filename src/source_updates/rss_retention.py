"""Select and retain explicit Google RSS captures; no acquisition or article access."""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from src.source_updates.calendar import local_time
from src.source_updates.collection import safe_workspace, writer
from src.source_updates.primary_review import original
from src.source_updates.retained import digest

MAX_FILES = 32
MAX_BYTES = 2_000_000


def identity(row: dict) -> dict:
    parts = row["logical_key"].split("|")
    url = urlsplit(row["source_url"])
    params = parse_qs(url.query, keep_blank_values=True)
    if (
        row["source_system"] != "rss"
        or row.get("http_status") != 200
        or len(parts) != 4
        or parts[0] != "rss"
        or parts[1] not in {"google_es", "google_en"}
        or parts[3] != "xml"
        or url.scheme != "https"
        or url.hostname != "news.google.com"
        or url.path != "/rss/search"
        or any(len(v) != 1 for v in params.values())
        or set(params) != {"q", "hl", "gl", "ceid"}
        or not params.get("q", [""])[0].strip()
        or not 0 < row["bytes"] <= MAX_BYTES
    ):
        raise ValueError("Expected bounded Google RSS capture with its exact feed/query identity")
    expected = {
        "google_es": {"hl": ["es-419"], "gl": ["MX"], "ceid": ["MX:es-419"]},
        "google_en": {"hl": ["en-US"], "gl": ["US"], "ceid": ["US:en"]},
    }[parts[1]]
    if any(params.get(k) != v for k, v in expected.items()):
        raise ValueError("RSS feed identity and its locale parameters disagree")
    return {"feed_id": parts[1], "query_term": params["q"][0], "query_url": row["source_url"]}


def selected(root: Path, paths: list[str]) -> list[dict]:
    if (
        not isinstance(paths, list)
        or not 1 <= len(paths) <= MAX_FILES
        or any(not isinstance(p, str) or not p for p in paths)
        or len(set(paths)) != len(paths)
    ):
        raise ValueError("Select1..32 unique explicit RSS paths")
    entries = {}
    for line in (root / "_manifest.jsonl").read_text().splitlines():
        row = json.loads(line)
        name = row.get("source_file")
        if name in paths:
            if name in entries and entries[name] != row:
                raise ValueError("Conflicting RSS manifest identities")
            entries[name] = row
    if set(entries) != set(paths):
        raise ValueError("Selected RSS source missing from manifest")
    rows = [entries[p] for p in sorted(paths)]
    if sum(r["bytes"] for r in rows) > 16_000_000:
        raise ValueError("RSS selection exceeds reviewed combined byte bound")
    for row in rows:
        identity(row)
        original(root, row)  # Validates paths, body/size, public host, manifest and sidecar.
    return rows


def retain(workspace: Path, root: Path, paths: list[str], *, execute=False) -> dict:
    workspace, root = safe_workspace(workspace), root.resolve()
    rows = selected(root, paths)
    result = dict(
        version=1,
        mode="rss_retention" if execute else "dry_run",
        product="rss",
        originals=rows,
        network_requests=0,
        paid_requests=0,
        new_source_capture=False,
        source_capture_dates_preserved=True,
        activation="none",
        publication="not_authorized",
    )
    if not execute:
        return result
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError("RSS retention requires a new empty workspace")
    with writer(workspace):
        if any(p.name != ".source-update.lock" for p in workspace.iterdir()):
            raise ValueError("RSS workspace changed before writer lock")
        bronze = workspace / "data/bronze"
        for row in rows:
            source = original(root, row)
            target = bronze / row["source_file"]
            if not target.resolve().is_relative_to(bronze.resolve()):
                raise ValueError("RSS retention destination escapes workspace")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            shutil.copyfile(Path(str(source) + ".meta.json"), Path(str(target) + ".meta.json"))
            if digest(target) != row["sha256"]:
                raise ValueError("RSS source changed during retention")
        manifest = bronze / "_manifest.jsonl"
        manifest.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        result.update(
            status="retained_unvalidated",
            run_id=uuid4().hex,
            retained_at=datetime.now(UTC).isoformat(),
            manifest_sha256=digest(manifest),
        )
        receipts = workspace / "receipts"
        receipts.mkdir(exist_ok=True)
        (receipts / f"rss-retained-{result['run_id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
    return result


def inputs(workspace: Path, run_id: str, cutoff: str) -> tuple[list[tuple[bytes, dict]], str]:
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("Expected RSS retention receipt ID")
    receipt_path = workspace / "receipts" / f"rss-retained-{run_id}.json"
    receipt = json.loads(receipt_path.read_text())
    expected = dict(
        version=1,
        mode="rss_retention",
        product="rss",
        status="retained_unvalidated",
        run_id=run_id,
        network_requests=0,
        paid_requests=0,
        new_source_capture=False,
        source_capture_dates_preserved=True,
        activation="none",
        publication="not_authorized",
    )
    if set(receipt) != set(expected) | {"originals", "retained_at", "manifest_sha256"} or any(
        type(receipt.get(k)) is not type(v) or receipt.get(k) != v for k, v in expected.items()
    ):
        raise ValueError("RSS retention identity/status/flags changed")
    local_time(receipt["retained_at"])
    bronze = workspace / "data/bronze"
    manifest = bronze / "_manifest.jsonl"
    if digest(manifest) != receipt.get("manifest_sha256"):
        raise ValueError("RSS retained manifest changed")
    rows = selected(bronze, [r["source_file"] for r in receipt["originals"]])
    if rows != receipt["originals"] or len(manifest.read_text().splitlines()) != len(rows):
        raise ValueError("RSS retention selected artifacts or metadata changed")
    expected_files = {"_manifest.jsonl"} | {
        r["source_file"] + suffix for r in rows for suffix in ("", ".meta.json")
    }
    if {p.relative_to(bronze).as_posix() for p in bronze.rglob("*") if p.is_file()} != expected_files:
        raise ValueError("RSS candidate contains unselected Bronze files")
    if any(local_time(r["downloaded_at"]) > local_time(cutoff) for r in rows):
        raise ValueError("RSS source capture is after requested cutoff")
    return [(original(bronze, r).read_bytes(), r) for r in rows], digest(receipt_path)
