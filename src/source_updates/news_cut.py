"""Read-only monthly RSS and upstream candidate-cut audits; no news activation."""

from __future__ import annotations

import argparse
import calendar
from datetime import date
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from lxml import etree

from src.conversational_analytics.evidence_index import candidate_content_sha256
from src.source_updates.calendar import local_time
from src.source_updates.news import canonical_url
from src.source_updates.primary_review import no_activation, original

ZONE = ZoneInfo("America/Mexico_City")


def rss_cut(root: Path, month: str, as_of: str) -> dict:
    if not re.fullmatch(r"20\d{2}-\d{2}", month):
        raise ValueError("Expected YYYY-MM")
    start = date.fromisoformat(month + "-01")
    cutoff = local_time(as_of)
    sources, rows, rejected, groups = [], [], [], {}
    manifest = root / "_manifest.jsonl"
    seen = set()
    for line in manifest.read_text().splitlines():
        source = json.loads(line)
        identity = (source.get("source_file"), source.get("sha256"))
        if source.get("source_system") != "rss" or identity in seen:
            continue
        seen.add(identity)
        path = original(root, source)
        captured = local_time(source["downloaded_at"])
        if captured > cutoff:
            continue
        # Disable external entities and network, including malicious retained XML.
        tree = etree.fromstring(path.read_bytes(), etree.XMLParser(resolve_entities=False, no_network=True))
        if tree.getroottree().docinfo.doctype:
            raise ValueError("RSS DOCTYPE is outside the reviewed feed contract")
        if tree.tag != "rss" or tree.find("channel") is None:
            raise ValueError("Expected RSS channel")
        sources.append(
            {k: source[k] for k in ("source_file", "source_url", "sha256", "downloaded_at", "logical_key")}
        )
        for index, item in enumerate(tree.findall("channel/item"), 1):
            locator = {
                "source_file": source["source_file"],
                "source_hash": source["sha256"],
                "item_1based": index,
                "captured_at": source["downloaded_at"],
            }
            try:
                title, url, raw_date = (item.findtext(k) for k in ("title", "link", "pubDate"))
                if not title or not title.strip() or not url or not raw_date:
                    raise ValueError("Missing title/link/pubDate")
                stamp = parsedate_to_datetime(raw_date)
                if stamp is None or stamp.tzinfo is None:
                    raise ValueError("RSS pubDate needs an explicit timezone")
                day = stamp.astimezone(ZONE).date()
                if stamp > captured:
                    raise ValueError("RSS publication later than capture")
                normalized = canonical_url(url.strip())
                row = {
                    **locator,
                    "title": title.strip(),
                    "url": url.strip(),
                    "canonical_url": normalized,
                    "published_at_as_declared": stamp.isoformat(),
                    "local_publication_date": day.isoformat(),
                    "event_date": None,
                    "first_available_at": None,
                    "publisher_document_verified": False,
                    "agent_eligible": False,
                }
                rows.append(row)
                if day.year == start.year and day.month == start.month:
                    key = (normalized, day.isoformat())
                    groups.setdefault(key, []).append(row)
            except (ValueError, TypeError, OverflowError) as exc:
                rejected.append({**locator, "reason": str(exc)})
    if not sources:
        raise ValueError("No retained RSS captures available by cutoff")
    observed = sorted({key[1] for key in groups})
    unobserved = [
        date(start.year, start.month, day).isoformat()
        for day in range(1, calendar.monthrange(start.year, start.month)[1] + 1)
        if date(start.year, start.month, day).isoformat() not in observed
    ]
    return {
        "mode": "offline_rss_cut_audit",
        "month": month,
        "timezone": str(ZONE),
        "as_of": cutoff.isoformat(),
        "sources": sources,
        "feed_records_valid": len(rows),
        "selected_contributions": sum(map(len, groups.values())),
        "selected_dated_urls": len(groups),
        "observed_publication_days": observed,
        "days_not_observed_in_selected_captures": unobserved,
        "records": [
            {
                "canonical_url": key[0],
                "local_publication_date": key[1],
                "contributors": groups[key],
                "agent_eligible": False,
            }
            for key in sorted(groups)
        ],
        "rejected_items": rejected,
        "coverage": "partial_metadata_in_selected_retained_feeds_not_universal_month_archive",
        "query_scope": "exact_source_urls_and_logical_keys_listed_above",
        "missing_days_mean": "not_observed_never_no_news",
        "release_lag_days": None,
        "network_requests": 0,
        "article_requests": 0,
        "writes": 0,
        "activation": "none",
        "silver_gold_certification": False,
    }


def candidate_cut(payload: dict) -> dict:
    no_activation(payload)
    if payload.get("schema") != "monthly_news_candidate_v1" or not payload.get("coverage"):
        raise ValueError("Expected explicitly scoped monthly candidate cut")
    cut = local_time(payload["cut_at"])
    records = payload["records"]
    if not isinstance(records, list) or not records:
        raise ValueError("Candidate cut is empty")
    ids, stories = set(), set()
    for row in records:
        if row.get("review_status") != "candidate_unapproved" or "review" in row:
            raise ValueError("Audit accepts only unapproved candidates, never approvals")
        if row.get("kind") != "news" or not row.get("id") or not row.get("story_id"):
            raise ValueError("Candidate identity missing")
        if row["id"] in ids or row["story_id"] in stories:
            raise ValueError("Duplicate candidate/story identity")
        ids.add(row["id"])
        stories.add(row["story_id"])
        supplied = row.get("candidate_content_sha256")
        clean = {k: v for k, v in row.items() if k != "candidate_content_sha256"}
        if supplied != candidate_content_sha256(clean):
            raise ValueError("Candidate content hash mismatch")
        source = row["source"]
        if not re.fullmatch(r"[a-f0-9]{64}", source["sha256"]):
            raise ValueError("Invalid source hash")
        canonical_url(source["url"])
        published = date.fromisoformat(row["published_at"])
        captured = local_time(row["first_captured_at"])
        verified = local_time(row["verified_at"])
        if published > captured.date() or not captured <= verified <= cut:
            raise ValueError("Candidate date order invalid")
        for name in ("event_date", "event_end_date"):
            if row.get(name) is not None:
                date.fromisoformat(row[name])
    return {
        "mode": "upstream_candidate_metadata_audit",
        "records": len(records),
        "coverage": payload["coverage"],
        "cut_at": payload["cut_at"],
        "self_hashes_valid": True,
        "source_bodies_reverified": False,
        "publisher_read_claim": "upstream_metadata_only_not_new_local_body_verification",
        "candidate_status": "candidate_unapproved",
        "agent_eligible": False,
        "network_requests": 0,
        "writes": 0,
        "activation": "none",
        "silver_gold_certification": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    rss = commands.add_parser("rss")
    rss.add_argument("--root", type=Path, required=True)
    rss.add_argument("--month", required=True)
    rss.add_argument("--as-of", required=True)
    candidate = commands.add_parser("candidate")
    candidate.add_argument("--file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = (
            rss_cut(args.root, args.month, args.as_of)
            if args.command == "rss"
            else candidate_cut(json.loads(args.file.read_text()))
        )
        if args.command == "candidate":
            result["cut_file_sha256"] = hashlib.sha256(args.file.read_bytes()).hexdigest()
    except (ValueError, KeyError, OSError, TypeError, etree.XMLSyntaxError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc), "activation": "none"}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
