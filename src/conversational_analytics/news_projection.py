"""Pure shared news/card projection used by both the bounded chat runtime and exporter."""

from __future__ import annotations
from datetime import date
from typing import Any
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

COMPANIES = {"Aeroméxico", "Volaris", "Viva"}


def canonical_news_url(value: str) -> str:
    """Drop tracking only; keep publisher identifiers and content query args."""
    parts = urlsplit(value)
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in {"fbclid", "gclid"}
    ]
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), "")
    )


def _review_metadata(record: dict[str, Any]) -> dict[str, Any]:
    """Only exact semantic/review duplicates may share a source silently."""
    return {
        **{
            key: record.get(key)
            for key in (
                "title",
                "description",
                "publisher",
                "published_at",
                "event_date",
                "event_end_date",
                "first_captured_at",
                "review_status",
            )
        },
        "story_id": record.get("story_id", record["id"]),
        "companies": sorted("Viva" if value == "Viva Aerobus" else value for value in record["companies"]),
        "topics": sorted(record.get("topics", [])),
    }


def project(records: list[dict[str, Any]], *, require_known_companies: bool = True) -> list[dict[str, Any]]:
    stories = {}
    seen_urls = {}
    for record in records:
        if record.get("kind") != "news":
            continue
        source = {**record["source"], "publisher": record["publisher"]}
        url = canonical_news_url(source["url"])
        story = record.get("story_id", record["id"])
        metadata = _review_metadata(record)
        if url in seen_urls:
            previous_hash, previous_metadata = seen_urls[url]
            if previous_hash != source["sha256"]:
                raise ValueError("Conflicting source hashes at the same canonical URL")
            if previous_metadata != metadata:
                raise ValueError(
                    "Conflicting news review metadata at the same canonical URL; review both records"
                )
            continue
        seen_urls[url] = (source["sha256"], metadata)
        published = record.get("published_at")
        if not published:
            continue  # Unknown publication cannot be month-bucketed.
        date.fromisoformat(published)
        if story in stories:
            stories[story]["sources"].append(source)
            # A reviewed story does not approve a newly associated source.
            # Keep the entire mixed card closed until every source is reviewed.
            if record["review_status"] != "owner_approved":
                stories[story]["review_status"] = "candidate_unapproved"
            continue
        companies = ["Viva" if value == "Viva Aerobus" else value for value in record["companies"]]
        if require_known_companies and not set(companies).issubset(COMPANIES):
            raise ValueError("Unknown company")
        summary = record["description"]
        if not summary or len(summary) > 320:
            raise ValueError("Unbounded news summary")
        stories[story] = {
            "id": record["id"],
            "story_id": story,
            "title": record["title"],
            "description": summary,
            "companies": companies,
            "topics": record.get("topics", []),
            "publisher": record["publisher"],
            "published_at": published,
            "event_date": record.get("event_date"),
            "event_end_date": record.get("event_end_date"),
            "first_captured_at": record.get("first_captured_at"),
            "sources": [source],
            "review_status": record["review_status"],
        }
    return sorted(stories.values(), key=lambda row: (row["published_at"], row["id"]), reverse=True)
