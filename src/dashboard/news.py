"""Monthly browsing projection over approved evidence, plus explicit review cut.

Candidates are preview-only. Exporting them never changes the pinned evidence
index, receipts, chat tools, theses or publication gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.config import PATHS
from src.conversational_analytics.evidence_index import EvidenceIndex
from src.conversational_analytics.news_projection import COMPANIES, project
from src.web_export.writer import write_json

CANDIDATE_HOSTS = {
    "ir.aeromexico.com",
    "investorcloud.s3.amazonaws.com",
    "filemanager-cdn.mziq.com",
    "api.mziq.com",
    "www.aeroroutes.com",
}



def build_news_payload(candidate: Path | None = None) -> dict[str, Any]:
    index = EvidenceIndex(PATHS.root / "config/chat/evidence/approved-index.json")
    records = [{**r, "review_status": "owner_approved"} for r in index.records if r.get("kind") == "news"]
    counts = {company:sum(company in ["Viva" if c=="Viva Aerobus" else c for c in row["companies"]] for row in records) for company in sorted(COMPANIES)}
    coverage = f"Archivo aprobado parcial: {len(records)} noticias. " + "; ".join(f"{company}: {count}" for company,count in counts.items()) + ". Cero fichas no demuestra ausencia de noticias."
    candidate_hash = None
    approval_package = None
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
        approval_package = {
            "schema": "monthly_news_batch_approval_proposal_v1", "status": "owner_review_required",
            "candidate_file_sha256": candidate_hash, "candidate_count": len(payload["records"]),
            "scope": "Approve the News tab and these eleven short news records for approved chat search in one decision; no thesis, metric, scheduler or publication approval is implied.",
            "decision_required": "One explicit owner decision bound to this complete candidate hash and its item content hashes; no approval is recorded by this proposal.",
            "records": payload["records"],
            "proposed_index_records": [
                {"record": normalized, "candidate_content_sha256": candidate_content_sha256(normalized)}
                for row in payload["records"]
                for normalized in [{key: row[key] for key in (
                    "id", "story_id", "kind", "published_at", "publisher", "title", "description", "companies", "topics", "source", "event_date", "event_end_date", "first_captured_at"
                )}]
            ],
        }
        approval_package["proposal_sha256"] = hashlib.sha256(json.dumps(approval_package,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    stories = project(records)
    return {
        "schema_version": "monthly_news_v1",
        "mode": "candidate_preview" if candidate else "approved_only",
        "coverage_note": coverage,
        "approved_index_sha256": index.sha256,
        "candidate_sha256": candidate_hash,
        "approval_package": approval_package,
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
