"""Monthly browsing projection over approved evidence, plus explicit review cut.

Candidates are preview-only. Exporting them never changes the pinned evidence
index, receipts, chat tools, theses or publication gate.
"""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.config import PATHS
from src.conversational_analytics.evidence_index import EvidenceIndex
from src.ingest.news.rss_gdelt import canonical_news_url
from src.web_export.writer import write_json

COMPANIES = {"Aeroméxico", "Volaris", "Viva"}
CANDIDATE_HOSTS = {
    "ir.aeromexico.com",
    "investorcloud.s3.amazonaws.com",
    "filemanager-cdn.mziq.com",
    "api.mziq.com",
    "www.aeroroutes.com",
}


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


def project(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stories = {}
    seen_urls = {}
    for record in records:
        if record.get("kind") != "news":
            continue
        published = record.get("published_at")
        if not published:
            continue  # Unknown publication cannot be month-bucketed.
        date.fromisoformat(published)
        source = record["source"]
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
        if story in stories:
            stories[story]["sources"].append(source)
            # A reviewed story does not approve a newly associated source.
            # Keep the entire mixed card closed until every source is reviewed.
            if record["review_status"] != "owner_approved":
                stories[story]["review_status"] = "candidate_unapproved"
            continue
        companies = ["Viva" if value == "Viva Aerobus" else value for value in record["companies"]]
        if not set(companies).issubset(COMPANIES):
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


def build_news_payload(candidate: Path | None = None) -> dict[str, Any]:
    index = EvidenceIndex(PATHS.root / "config/chat/evidence/approved-index.json")
    records = [{**r, "review_status": "owner_approved"} for r in index.records if r.get("kind") == "news"]
    coverage = "Archivo aprobado parcial: tres noticias; dos de Aeroméxico y una de Volaris. Viva carece de noticias aprobadas."
    candidate_hash = None
    default_month = None
    if candidate:
        payload = json.loads(candidate.read_text())
        if payload.get("schema") != "monthly_news_candidate_v1":
            raise ValueError("Unknown candidate schema")
        from src.conversational_analytics.evidence_index import candidate_content_sha256

        for row in payload["records"]:
            if row.get("review_status") != "candidate_unapproved":
                raise ValueError("Candidate cannot claim approval")
            if row.get("candidate_content_sha256") != candidate_content_sha256(
                {k: v for k, v in row.items() if k != "candidate_content_sha256"}
            ):
                raise ValueError("Candidate content changed after verification")
            source = row["source"]
            parsed = urlsplit(source["url"])
            if (
                parsed.scheme != "https"
                or parsed.hostname not in CANDIDATE_HOSTS
                or parsed.username
                or parsed.password
            ):
                raise ValueError("Candidate source outside bounded list")
        records += payload["records"]
        cut_month = payload["cut_at"][:7]
        year, month = map(int, cut_month.split("-"))
        default_month = f"{year - 1}-12" if month == 1 else f"{year}-{month - 1:02d}"
        coverage = (
            payload["coverage"]
            + " Los candidatos requieren aprobación independiente y no están disponibles para búsqueda del chat."
        )
        candidate_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
    stories = project(records)
    return {
        "schema_version": "monthly_news_v1",
        "mode": "candidate_preview" if candidate else "approved_only",
        "coverage_note": coverage,
        "approved_index_sha256": index.sha256,
        "candidate_sha256": candidate_hash,
        "months": sorted({row["published_at"][:7] for row in stories}, reverse=True),
        "default_month": default_month,
        "records": stories,
        "limits": [
            "Selección parcial. Cero fichas significa ausencia de cobertura en este archivo.",
            "El volumen de noticias no mide importancia; el tono de medios no mide satisfacción.",
            "Los resúmenes son originales y breves. No se redistribuyen artículos ni imágenes.",
            "Nuevas noticias no activan ni modifican tesis aprobadas.",
        ],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--candidate", type=Path, help="Explicitly include an unapproved cut for local review only"
    )
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    payload = build_news_payload(args.candidate)
    write_json(args.out, payload)
    print(
        f"{payload['mode']}: {len(payload['records'])} stories, {len(payload['months'])} publication months"
    )


if __name__ == "__main__":
    main()
