from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

SCRIPT = Path("scripts/chat/collect_news_candidates.py")
SPEC = importlib.util.spec_from_file_location("collect_news_candidates", SCRIPT)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_candidate_collection_is_metadata_only_and_week_bounded(tmp_path: Path) -> None:
    source = tmp_path / "headlines.json"
    source.write_text(json.dumps([
        {"published_at": "2026-10-06T10:00:00Z", "publisher": "FlightGlobal",
         "title": "Noticia pública", "url": "https://www.flightglobal.com/airlines/noticia"},
        {"published_at": "2026-10-12T10:00:00Z", "publisher": "FlightGlobal",
         "title": "Fuera de semana", "url": "https://www.flightglobal.com/airlines/otra"},
        {"published_at": "2026-10-07T10:00:00Z", "publisher": "FlightGlobal",
         "title": "Ignorar cuerpo", "url": "https://www.flightglobal.com/airlines/tercera",
         "body": "No copiar el artículo"},
    ]), encoding="utf-8")
    result = module.build_manifest(date(2026, 10, 5), json.loads(source.read_text()), source)
    assert len(result["records"]) == 2
    assert all(
        record["description"] is None and record["source_sha256"] is None for record in result["records"]
    )
    assert all("body" not in record for record in result["records"])


def test_weekly_candidate_write_is_idempotent_and_wont_overwrite(tmp_path: Path) -> None:
    source = tmp_path / "headlines.json"
    source.write_text("[]", encoding="utf-8")
    out = tmp_path / "out"
    week = date(2026, 10, 5)
    assert module.run(week, source, out, True) == 0
    manifest = out / "news-2026-10-05.json"
    before = manifest.read_bytes()
    assert module.run(week, source, out, True) == 0
    assert manifest.read_bytes() == before
    source.write_text("[{}]", encoding="utf-8")
    assert module.run(week, source, out, True) == 3
    assert manifest.read_bytes() == before


def test_article_metadata_is_bounded_and_source_hash_is_preserved(tmp_path: Path) -> None:
    source = tmp_path / "headlines.json"
    source.write_text("[]", encoding="utf-8")
    raw = {
        "published_at": "2026-10-06",
        "publisher": "FlightGlobal",
        "title": "Aerolínea informa sobre costos",
        "url": "https://www.flightglobal.com/airlines/2026/10/costos/",
        "source_sha256": "a" * 64,
        "description": "Resumen breve elaborado para revisión.",
        "companies": ["Volaris"],
        "topics": ["combustible"],
        "body": "El cuerpo no se acepta en la ficha.",
    }
    record = module.build_manifest(date(2026, 10, 5), [raw], source)["records"][0]
    assert record["source_sha256"] == "a" * 64
    assert record["description"] == "Resumen breve elaborado para revisión."
    assert record["companies"] == ["Volaris"]
    assert record["review"] == {"status": "owner_review_required", "receipt": None}
    assert "body" not in record
    assert module._normalize_item({**raw, "source_sha256": "not-a-hash"}) is None
    assert module._normalize_item({**raw, "description": "x" * 321}) is None
