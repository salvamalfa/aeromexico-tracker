"""Verify a bounded curator cut against public URLs. Default: dry run.

Raw publisher files stay in ignored Bronze; only hashes, citation metadata and
short original curator summaries enter the candidate. No approvals or cron.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, date
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from src.config import PATHS
from src.conversational_analytics.evidence_index import candidate_content_sha256

HOSTS = {
    "ir.aeromexico.com",
    "investorcloud.s3.amazonaws.com",
    "filemanager-cdn.mziq.com",
    "api.mziq.com",
    "www.aeroroutes.com",
}
ALLOWED = {
    "id",
    "story_id",
    "kind",
    "companies",
    "title",
    "description",
    "source_url",
    "published_at",
    "event_date",
    "event_end_date",
    "topics",
    "publisher",
    "discovery_method",
}


def validate_source_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in HOSTS or parsed.username or parsed.password:
        raise ValueError("Source outside bounded HTTPS candidate list")


def validate(raw):
    if set(raw) - ALLOWED:
        raise ValueError("Unrecognized fields: article bodies are not accepted")
    validate_source_url(raw["source_url"])
    if not raw.get("description") or len(raw["description"]) > 320 or len(raw["title"]) > 240:
        raise ValueError("Summary/title outside bounds")
    for key in ["published_at", "event_date", "event_end_date"]:
        if raw.get(key):
            date.fromisoformat(raw[key])
    if raw.get("event_end_date") and raw["event_end_date"] < raw["event_date"]:
        raise ValueError("Event interval reversed")
    return raw


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--capture", action="store_true")
    args = p.parse_args()
    items = [validate(row) for row in json.loads(args.input.read_text())]
    if len(items) > 30:
        raise ValueError("At most 30 public files per reviewed cut")
    print(
        json.dumps(
            {
                "dry_run": not args.capture,
                "calls_max": len(items),
                "paid_units": 0,
                "urls": [x["source_url"] for x in items],
                "candidate_destination": str(args.out),
                "raw_destination": "ignored data/bronze/news/review",
            }
        )
    )
    if not args.capture:
        return
    if args.out.exists():
        raise ValueError("Cut exists; create a new version instead of overwriting")
    records = []
    for raw in items:
        # No unrestricted redirects or authenticated calls. Follow only hosts
        # in this cut's public citation allowlist.
        with httpx.Client(timeout=30, follow_redirects=False) as client:
            url = raw["source_url"]
            for _ in range(4):
                response = client.get(url)
                if not response.is_redirect:
                    break
                url = str(response.url.join(response.headers["location"]))
                validate_source_url(url)
            response.raise_for_status()
        content = response.content
        if (
            not content.startswith(b"%PDF")
            and "<html" not in response.text.lower()[:1000]
            and "<!doctype html" not in response.text.lower()[:1000]
        ):
            raise ValueError("Expected a public publisher PDF/HTML")
        sha = hashlib.sha256(content).hexdigest()
        captured = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        folder = PATHS.bronze / "news" / "review"
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / (sha + (".pdf" if content.startswith(b"%PDF") else ".html"))
        if not destination.exists():
            destination.write_bytes(content)
        metadata = destination.with_suffix(destination.suffix + ".meta.json")
        if not metadata.exists():
            metadata.write_text(
                json.dumps({"url": url, "sha256": sha, "first_captured_at": captured}, indent=2) + "\n"
            )
        first_capture = json.loads(metadata.read_text())["first_captured_at"]
        row = {k: v for k, v in raw.items() if k != "source_url"}
        row.update(
            source={"id": raw["id"], "url": url, "sha256": sha},
            first_captured_at=first_capture,
            verified_at=captured,
            verification="http_200_source_hash",
            review_status="candidate_unapproved",
        )
        row["candidate_content_sha256"] = candidate_content_sha256(row)
        records.append(row)
        print(f"Verified {raw['id']}: HTTP {response.status_code}, {len(content)} bytes")
    payload = {
        "schema": "monthly_news_candidate_v1",
        "cut_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "coverage": "Selección manual parcial; no exhaustiva. Publicaciones 2026-06 a 2026-10; octubre incompleto.",
        "records": records,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
