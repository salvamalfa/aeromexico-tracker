"""Deterministic, approval-gated search over short public evidence excerpts.

The published index contains reviewed excerpts and citation metadata only. It
does not ingest report bodies or news articles at query time.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

INDEX_SCHEMA = "chat_evidence_index_v1"
MAX_QUERY_CHARS = 240
MAX_RESULTS = 5
MAX_EXCERPT_CHARS = 480
MAX_NEWS_DESCRIPTION_CHARS = 320
MAX_NEWS_QUOTE_CHARS = 200
ALLOWED_HOSTS = frozenset(
    {"sec.gov", "www.sec.gov", "bmv.com.mx", "www.bmv.com.mx", "aeromexico.com", "www.aeromexico.com",
     "volaris.com", "www.volaris.com", "vivaaerobus.com", "www.vivaaerobus.com", "gob.mx", "www.gob.mx"}
)
_TOKEN_RE = re.compile(r"[^\w]+", re.UNICODE)
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


class EvidenceIndexError(ValueError):
    """A malformed or unapproved evidence index or query."""


def _text(value: Any, field: str, maximum: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise EvidenceIndexError(f"{field} debe ser texto")
    value = value.strip()
    if (not value and not allow_empty) or len(value) > maximum:
        raise EvidenceIndexError(f"{field} está vacío o supera su límite")
    return value


def _approved(record: dict[str, Any]) -> bool:
    review = record.get("review")
    return (
        isinstance(review, dict)
        and review.get("decision") == "owner_approved"
        and isinstance(review.get("owner_id"), str)
        and bool(review["owner_id"].strip())
        and isinstance(review.get("receipt_id"), str)
        and bool(review["receipt_id"].strip())
        and isinstance(review.get("approved_at"), str)
        and bool(review["approved_at"].strip())
    )


def _source(record: dict[str, Any]) -> dict[str, str]:
    source = record.get("source")
    if not isinstance(source, dict):
        raise EvidenceIndexError("source debe ser un objeto")
    url = _text(source.get("url"), "source.url", 1000)
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or parsed.username or parsed.password:
        raise EvidenceIndexError("La fuente no pertenece a la lista HTTPS permitida")
    source_id = _text(source.get("id"), "source.id", 120)
    source_hash = _text(source.get("sha256"), "source.sha256", 64)
    if not _HASH_RE.fullmatch(source_hash):
        raise EvidenceIndexError("source.sha256 debe ser SHA-256 hexadecimal")
    return {"id": source_id, "url": url, "sha256": source_hash}


def _norm(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in folded if not unicodedata.combining(char))


def _tokens(value: str) -> set[str]:
    return {token for token in _TOKEN_RE.split(_norm(value)) if len(token) > 1}


def _optional_filter(value: Any, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    return _norm(_text(value, field, maximum))


def _match_score(query: set[str], fields: list[str]) -> int:
    available = set().union(*(_tokens(field) for field in fields)) if fields else set()
    return len(query & available)


def _load_approved(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceIndexError("No se pudo leer el índice de evidencia") from exc
    if not isinstance(payload, dict) or payload.get("schema") != INDEX_SCHEMA:
        raise EvidenceIndexError("La versión del índice de evidencia no es compatible")
    records = payload.get("records")
    if not isinstance(records, list):
        raise EvidenceIndexError("records debe ser una lista")
    return {"version": _text(payload.get("version"), "version", 80), "records": records}


class EvidenceIndex:
    """Search only reviewed records from one fixed JSON index."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        payload = _load_approved(self.path)
        self.version = payload["version"]
        self.records = [
            record for record in payload["records"] if isinstance(record, dict) and _approved(record)
        ]

    def search_reports(
        self, query: str, company: str | None = None, period: str | None = None, limit: int = 5
    ) -> dict[str, Any]:
        query = _text(query, "query", MAX_QUERY_CHARS)
        query_tokens = _tokens(query)
        if not query_tokens:
            raise EvidenceIndexError("query no contiene términos buscables")
        company_filter = _optional_filter(company, "company", 100)
        period_filter = _text(period, "period", 20) if period is not None else None
        limit = _limit(limit)
        matches = []
        for record in self.records:
            if record.get("kind") != "report":
                continue
            if company_filter and _norm(str(record.get("company", ""))) != company_filter:
                continue
            if period_filter and record.get("period") != period_filter:
                continue
            page = record.get("page")
            if not isinstance(page, int) or isinstance(page, bool) or page < 1:
                continue
            excerpt = _text(record.get("excerpt"), "excerpt", MAX_EXCERPT_CHARS)
            score = _match_score(
                query_tokens,
                [excerpt, str(record.get("section", "")), str(record.get("company", ""))],
            )
            if score:
                matches.append((score, record, excerpt))
        matches.sort(
            key=lambda item: (
                -item[0], str(item[1].get("company", "")), str(item[1].get("period", "")),
                item[1]["page"], str(item[1].get("id", "")),
            )
        )
        results = []
        for score, record, excerpt in matches[:limit]:
            source = _source(record)
            results.append({
                "id": _text(record.get("id"), "id", 120),
                "company": _text(record.get("company"), "company", 100),
                "period": _text(record.get("period"), "period", 20),
                "section": _text(record.get("section", ""), "section", 120, allow_empty=True),
                "page": page,
                "excerpt": excerpt,
                "citation": {
                    "label": f"Reporte {record['company']} {record['period']}, p. {page}",
                    "url": source["url"], "source_id": source["id"], "source_sha256": source["sha256"],
                },
                "_score": score,
            })
        for result in results:
            result.pop("_score", None)
        return {"index_version": self.version, "count": len(results), "results": results}

    def search_news(
        self, query: str, start_date: str | None = None, end_date: str | None = None,
        company: str | None = None, limit: int = 5,
    ) -> dict[str, Any]:
        query = _text(query, "query", MAX_QUERY_CHARS)
        query_tokens = _tokens(query)
        if not query_tokens:
            raise EvidenceIndexError("query no contiene términos buscables")
        if start_date is not None:
            start_date = _date(start_date, "start_date")
        if end_date is not None:
            end_date = _date(end_date, "end_date")
        if start_date and end_date and start_date > end_date:
            raise EvidenceIndexError("start_date no puede ser posterior a end_date")
        company_filter = _optional_filter(company, "company", 100)
        limit = _limit(limit)
        matches = []
        for record in self.records:
            if record.get("kind") != "news":
                continue
            published = _date(record.get("published_at"), "published_at")
            companies = record.get("companies", [])
            if not isinstance(companies, list) or any(not isinstance(x, str) for x in companies):
                raise EvidenceIndexError("news.companies debe ser una lista de texto")
            if company_filter and all(_norm(item) != company_filter for item in companies):
                continue
            if start_date and published < start_date or end_date and published > end_date:
                continue
            title = _text(record.get("title"), "title", 240)
            description = _text(record.get("description"), "description", MAX_NEWS_DESCRIPTION_CHARS)
            topics = record.get("topics", [])
            if not isinstance(topics, list) or any(not isinstance(x, str) for x in topics):
                raise EvidenceIndexError("news.topics debe ser una lista de texto")
            score = _match_score(query_tokens, [title, description, " ".join(companies), " ".join(topics)])
            if score:
                matches.append((score, published, record, title, description, companies, topics))
        matches.sort(key=lambda item: (-item[0], item[1], str(item[2].get("id", ""))))
        results = []
        for score, published, record, title, description, companies, topics in matches[:limit]:
            source = _source(record)
            quote = record.get("brief_quote")
            if quote is not None:
                quote = _text(quote, "brief_quote", MAX_NEWS_QUOTE_CHARS)
            results.append({
                "id": _text(record.get("id"), "id", 120), "published_at": published,
                "publisher": _text(record.get("publisher"), "publisher", 120),
                "title": title, "description": description, "companies": companies,
                "topics": topics, "brief_quote": quote,
                "citation": {
                    "label": _text(record.get("publisher"), "publisher", 120),
                    "url": source["url"], "source_id": source["id"], "source_sha256": source["sha256"],
                },
                "_score": score,
            })
        for result in results:
            result.pop("_score", None)
        return {"index_version": self.version, "count": len(results), "results": results}


def _limit(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_RESULTS:
        raise EvidenceIndexError(f"limit debe estar entre 1 y {MAX_RESULTS}")
    return value


def _date(value: Any, field: str) -> str:
    value = _text(value, field, 10)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise EvidenceIndexError(f"{field} debe usar YYYY-MM-DD")
    from datetime import date
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise EvidenceIndexError(f"{field} no es una fecha válida") from exc
    return value
