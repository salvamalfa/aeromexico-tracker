"""Pure shared news/card projection used by both the bounded chat runtime and exporter."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

COMPANIES = {"Aeroméxico", "Aeroméxico Connect", "Volaris", "Viva"}
NEWS_PUBLISHER_HOSTS = frozenset(
    {
        "ir.aeromexico.com",
        "investorcloud.s3.amazonaws.com",
        "cdn.investorcloud.net",
        "filemanager-cdn.mziq.com",
        "api.mziq.com",
        "www.aeroroutes.com",
        "www.sec.gov",
        "cms.volaris.com",
        "www.bmv.com.mx",
        "www.globenewswire.com",
        "acapulco.gob.mx",
        "www.gob.mx",
        "noticias.oma.aero",
        "www.eleconomista.com.mx",
        "aerolatinnews.com",
        "www.aviacionline.com",
    }
)


def public_sources(record: dict[str, Any]) -> list[dict[str, str]]:
    """Project citation metadata only, retaining native editorial provenance.

    The editorial hash identifies a recorded reading, not downloaded article
    bytes. Its complete semantics stay in the hash-bound approval record.
    """
    source = record["source"]
    result = [{**{key: source[key] for key in ("id", "url", "sha256")}, "publisher": record["publisher"]}]
    observations = record.get("publisher_observations", [])
    if not isinstance(observations, list):
        raise ValueError("Publisher observations must be a list")
    primary_verified = False
    for observation in observations:
        url = observation["url"]
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in NEWS_PUBLISHER_HOSTS
            or parsed.username
            or parsed.password
        ):
            raise ValueError("Editorial provenance outside bounded publisher list")
        if (
            observation.get("representation") != "reviewed_web_observation_not_original_publisher_bytes"
            or observation.get("original_page_sha256") is not None
            or observation.get("publisher_page_read") is not True
        ):
            raise ValueError("Editorial provenance must describe an actual recorded native reading")
        encoded = (
            json.dumps(observation, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n"
        ).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        if canonical_news_url(url) == canonical_news_url(source["url"]):
            primary_verified = digest == source["sha256"]
            continue
        result.append(
            {
                "id": "web_observation_" + digest[:20],
                "url": url,
                "sha256": digest,
                "publisher": observation["publisher"],
            }
        )
    if (
        source.get("sha256_semantics") == "reviewed_observation_not_original_page_bytes"
        and not primary_verified
    ):
        raise ValueError("Selected editorial observation differs from its recorded source hash")
    return result


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
        companies = ["Viva" if value == "Viva Aerobus" else value for value in record["companies"]]
        if require_known_companies and not set(companies).issubset(COMPANIES):
            raise ValueError("Unknown company")
        topics = record.get("topics", [])
        sources = public_sources(record)
        source = sources[0]
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
            if set(stories[story]["companies"]) != set(companies):
                raise ValueError("Conflicting company attribution within one story; review source grouping")
            for source in sources:
                if source not in stories[story]["sources"]:
                    stories[story]["sources"].append(source)
            # Mixed operator attribution cannot silently become a shared card.
            # Consistent company sets keep topic filters searchable per source.
            stories[story]["topics"] = sorted(set(stories[story]["topics"]) | set(topics))
            # A reviewed story does not approve a newly associated source.
            # Keep the entire mixed card closed until every source is reviewed.
            if record["review_status"] != "owner_approved":
                stories[story]["review_status"] = "candidate_unapproved"
            continue
        summary = record["description"]
        if not summary or len(summary) > 320:
            raise ValueError("Unbounded news summary")
        stories[story] = {
            "id": record["id"],
            "story_id": story,
            "title": record["title"],
            "description": summary,
            "companies": companies,
            "topics": topics,
            "publisher": record["publisher"],
            "published_at": published,
            "event_date": record.get("event_date"),
            "event_end_date": record.get("event_end_date"),
            "first_captured_at": record.get("first_captured_at"),
            "sources": sources,
            "review_status": record["review_status"],
        }
    return sorted(stories.values(), key=lambda row: (row["published_at"], row["id"]), reverse=True)
