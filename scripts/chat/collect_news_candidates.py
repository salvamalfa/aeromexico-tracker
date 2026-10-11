"""Build an idempotent weekly news candidate manifest from headline metadata.

Input contains metadata collected from public RSS feeds; article text is not
accepted. The command is dry-run unless ``--write-candidate`` is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "config/chat/evidence/candidates/news"
ALLOWED_HOSTS = {"news.google.com", "www.eleconomista.com.mx", "eleconomista.com.mx"}
MAX_ITEMS = 250


def monday(value: str) -> date:
    result = date.fromisoformat(value)
    if result.weekday() != 0:
        raise argparse.ArgumentTypeError("La fecha debe ser un lunes (inicio de semana UTC)")
    return result


def _normalize_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    title, url, published_at, publisher = (
        raw.get(key) for key in ("title", "url", "published_at", "publisher")
    )
    if not all(isinstance(value, str) and value.strip() for value in (title, url, published_at, publisher)):
        return None
    try:
        published = date.fromisoformat(published_at[:10])
    except ValueError:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        return None
    if len(title) > 240 or len(url) > 1000 or len(publisher) > 120:
        return None
    # The source hash is deliberately absent until a curator pins the exact
    # source artifact. Hashing a URL or feed metadata would misstate provenance.
    item_id = hashlib.sha256(f"{published.isoformat()}\n{url}".encode()).hexdigest()[:20]
    return {
        "candidate_id": f"news-{item_id}",
        "kind": "news_candidate",
        "published_at": published.isoformat(),
        "publisher": publisher.strip(),
        "title": title.strip(),
        "url": url.strip(),
        "source_sha256": None,
        "description": None,
        "companies": [],
        "topics": [],
        "brief_quote": None,
        "review": {"status": "owner_review_required", "receipt_id": None},
    }


def build_manifest(week_start: date, items: list[Any], input_path: Path) -> dict[str, Any]:
    week_end = date.fromordinal(week_start.toordinal() + 6)
    unique: dict[str, dict[str, Any]] = {}
    for raw in items[:MAX_ITEMS]:
        item = _normalize_item(raw)
        if item and week_start.isoformat() <= item["published_at"] <= week_end.isoformat():
            unique[item["candidate_id"]] = item
    records = sorted(unique.values(), key=lambda item: (item["published_at"], item["candidate_id"]))
    return {
        "schema": "chat_news_candidates_v1",
        "status": "candidate_closed",
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
        "limits": {"max_items_read": MAX_ITEMS, "article_bodies_collected": False},
        "records": records,
    }


def run(week_start: date, input_path: Path, output_dir: Path, write_candidate: bool) -> int:
    try:
        payload = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        print("No se pudo leer el JSON de titulares de entrada", file=sys.stderr)
        return 2
    if not isinstance(payload, list):
        print("La entrada debe ser una lista de metadatos de titulares", file=sys.stderr)
        return 2
    manifest = build_manifest(week_start, payload, input_path)
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    destination = output_dir / f"news-{week_start.isoformat()}.json"
    print(json.dumps({
        "dry_run": not write_candidate,
        "week_start": week_start.isoformat(),
        "input_records": min(len(payload), MAX_ITEMS),
        "candidate_records": len(manifest["records"]),
        "destination": str(destination),
        "writes": bool(write_candidate),
    }, ensure_ascii=False))
    if not write_candidate:
        return 0
    if destination.exists():
        if destination.read_text(encoding="utf-8") == encoded:
            print("El manifiesto ya existe con el mismo contenido; sin cambios.")
            return 0
        print("El manifiesto ya existe con contenido distinto; no se sobrescribe.", file=sys.stderr)
        return 3
    output_dir.mkdir(parents=True, exist_ok=True)
    destination.write_text(encoded, encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--week-start", required=True, type=monday, help="lunes UTC, YYYY-MM-DD")
    parser.add_argument(
        "--input", required=True, type=Path, help="JSON de titulares; no incluir cuerpo de artículos"
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--write-candidate", action="store_true", help="escribe una sola vez el manifest candidate"
    )
    args = parser.parse_args()
    return run(args.week_start, args.input, args.output_dir, args.write_candidate)


if __name__ == "__main__":
    raise SystemExit(main())
