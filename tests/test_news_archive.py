from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.config import ProjectPaths
from src.dashboard.news import project
from src.ingest.news import rss_gdelt as news


def record(id="a", **overrides):
    row = dict(
        id=id,
        story_id="story",
        kind="news",
        companies=["Viva"],
        title="Titular",
        description="Resumen original",
        publisher="Viva",
        published_at="2026-10-09",
        event_date="2026-09-01",
        first_captured_at="2026-10-15T00:00:00Z",
        topics=["tráfico"],
        source={"id": id, "url": "https://ri.vivaaerobus.com/a", "sha256": "a" * 64},
        review_status="candidate_unapproved",
    )
    return {**row, **overrides}


def test_monthly_projection_deduplicates_urls_and_stories_without_changing_dates():
    records = project(
        [
            record(),
            record("copy"),
            record("second", source={"id": "b", "url": "https://ri.vivaaerobus.com/b", "sha256": "b" * 64}),
            record(
                "undated",
                published_at=None,
                source={"id": "undated", "url": "https://ri.vivaaerobus.com/undated", "sha256": "c" * 64},
            ),
        ]
    )
    assert len(records) == 1
    assert len(records[0]["sources"]) == 2
    assert records[0]["published_at"] == "2026-10-09"
    assert records[0]["event_date"] == "2026-09-01"
    assert records[0]["review_status"] == "candidate_unapproved"


def test_gdelt_first_seen_is_not_publication(monkeypatch, tmp_path):
    monkeypatch.setattr(
        news,
        "lineage",
        lambda _: dict(
            ingested_at=pd.Timestamp("2026-10-15", tz="UTC"), source_file="a.json", source_hash="a" * 64
        ),
    )
    path = tmp_path / "a.json"
    path.write_text(
        json.dumps(
            {
                "articles": [
                    {"title": "Viva", "url": "https://example.com/news", "seendate": "20261014T120000Z"}
                ]
            }
        )
    )
    result = news._parse_gdelt(path)[0]
    assert result["published_at"] is None
    assert result["first_seen_at"] == pd.Timestamp("2026-10-14T12:00:00Z")
    assert result["first_captured_at"] == pd.Timestamp("2026-10-15T00:00:00Z")


def test_rebuild_unions_all_snapshots_and_preserves_first_capture(monkeypatch, tmp_path):
    paths = ProjectPaths(root=tmp_path)
    paths.bronze.mkdir(parents=True)
    monkeypatch.setattr(news, "PATHS", paths)
    monkeypatch.setattr(news, "RSS_FEEDS", {"test": "https://example.com/rss"})
    entries = []
    for key in ["older", "newer"]:
        file = paths.bronze / (key + ".xml")
        file.write_text("placeholder")
        entries.append(dict(logical_key="rss|test|current|xml", source_file=file.name))
    (paths.bronze / "_manifest.jsonl").write_text("\n".join(json.dumps(x) for x in entries))

    def parse(path, key):
        capture = pd.Timestamp("2026-09-01" if path.stem == "older" else "2026-10-01", tz="UTC")
        base = dict(
            published_at=pd.Timestamp("2026-08-30", tz="UTC"),
            first_captured_at=capture,
            first_seen_at=capture,
            ingested_at=capture,
            gdelt_tone=None,
            query_term="Viva",
            source_system="rss",
        )
        return [
            {**base, "url": "https://example.com/shared?utm_source=" + path.stem},
            {**base, "url": "https://example.com/" + path.stem},
        ]

    monkeypatch.setattr(news, "_parse_rss", parse)
    result = news.build_from_bronze()
    assert result["rows"] == 3
    frame = pd.read_parquet(paths.silver / "news_headlines.parquet")
    shared = frame[frame.url.eq("https://example.com/shared")].iloc[0]
    assert shared.first_captured_at == pd.Timestamp("2026-09-01T00:00:00Z")
    assert shared.ingested_at == pd.Timestamp("2026-10-01T00:00:00Z")


def test_candidate_cannot_claim_owner_approval_or_change_content(monkeypatch, tmp_path):
    import src.dashboard.news as archive

    class Index:
        records = []
        sha256 = "a" * 64

    monkeypatch.setattr(archive, "EvidenceIndex", lambda _: Index())
    candidate = tmp_path / "candidate.json"
    candidate.write_text(
        json.dumps(
            {
                "schema": "monthly_news_candidate_v1",
                "coverage": "Partial",
                "records": [record(review_status="owner_approved")],
            }
        )
    )
    with pytest.raises(ValueError, match="claim approval"):
        archive.build_news_payload(candidate)
    candidate.write_text(
        json.dumps(
            {
                "schema": "monthly_news_candidate_v1",
                "coverage": "Partial",
                "records": [record(candidate_content_sha256="f" * 64)],
            }
        )
    )
    with pytest.raises(ValueError, match="changed"):
        archive.build_news_payload(candidate)


def test_approved_index_bytes_remain_the_authoritative_original():
    import hashlib

    # Bytes from the approved base commit; works in a shallow CI checkout.
    original_sha256 = "5fba922f7b6186a5ee0c31d9f678c3222a11fb50e9cf7d5b2f26b62212516672"
    assert (
        hashlib.sha256(Path("config/chat/evidence/approved-index.json").read_bytes()).hexdigest()
        == original_sha256
    )


def test_normal_export_never_includes_candidates_without_the_existing_pin(monkeypatch, tmp_path):
    from src.web_export.news import export_news

    monkeypatch.delenv("CHAT_EVIDENCE_APPROVED_INDEX_SHA256", raising=False)
    output = export_news(tmp_path)[0]
    payload = json.loads(output.read_text())
    assert payload["mode"] == "evidence_unavailable"
    assert payload["records"] == []


def test_wrong_external_pin_blocks_news_export(monkeypatch, tmp_path):
    from src.web_export.news import export_news

    monkeypatch.setenv("CHAT_EVIDENCE_APPROVED_INDEX_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="SHA-256 externo"):
        export_news(tmp_path)
    assert not list(tmp_path.iterdir())


def test_publication_schema_rejects_candidate_preview_and_unapproved_records():
    from jsonschema import Draft202012Validator
    from src.publish.verify import _data_schema_for

    schema = _data_schema_for("data/v1/news.json")
    assert schema is not None
    payload = {
        "schema_version": "monthly_news_v1",
        "mode": "candidate_preview",
        "coverage_note": "partial",
        "months": [],
        "records": [],
        "limits": [],
    }
    assert list(Draft202012Validator(schema).iter_errors(payload))


@pytest.mark.parametrize("reverse", [False, True])
def test_mixed_story_sources_never_inherit_owner_approval(reverse):
    approved = record("approved", review_status="owner_approved")
    candidate = record(
        "candidate",
        source={"id": "candidate", "url": "https://ri.vivaaerobus.com/new-source", "sha256": "b" * 64},
    )
    rows = [candidate, approved] if reverse else [approved, candidate]
    stories = project(rows)
    assert len(stories) == 1
    assert len(stories[0]["sources"]) == 2
    assert stories[0]["review_status"] == "candidate_unapproved"


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("same_story", [False, True])
def test_changed_bytes_at_same_canonical_source_url_fail_closed(reverse, same_story):
    approved = record("approved", review_status="owner_approved")
    candidate = record(
        "candidate",
        story_id="story" if same_story else "other-story",
        source={"id": "candidate", "url": "https://ri.vivaaerobus.com/a?utm_source=rss", "sha256": "b" * 64},
    )
    rows = [candidate, approved] if reverse else [approved, candidate]
    with pytest.raises(ValueError, match="Conflicting source hashes"):
        project(rows)


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("status", ["owner_approved", "candidate_unapproved"])
@pytest.mark.parametrize(
    "revision",
    [
        {"title": "Titular revisado"},
        {"description": "Resumen original corregido"},
        {"published_at": "2026-09-01"},
        {"published_at": None},
        {"event_date": "2026-08-01"},
        {"first_captured_at": "2026-10-14T00:00:00Z"},
        {"story_id": "another-story"},
    ],
)
def test_same_bytes_cannot_hide_semantic_revisions(reverse, status, revision):
    original = record("original", review_status=status)
    revised = record("revision", review_status=status, **revision)
    rows = [revised, original] if reverse else [original, revised]
    with pytest.raises(ValueError, match="review metadata.*review both records"):
        project(rows)


@pytest.mark.parametrize("reverse", [False, True])
def test_same_bytes_cannot_hide_changed_review_status(reverse):
    approved = record("approved", review_status="owner_approved")
    candidate = record("candidate")
    rows = [candidate, approved] if reverse else [approved, candidate]
    with pytest.raises(ValueError, match="review metadata.*review both records"):
        project(rows)
