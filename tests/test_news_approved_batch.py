"""The actual 23-item owner decision reaches the current approved corpus.

Historical ten/eleven-item fixtures are tested separately; these tests read
the real current index and its exact public owner-decision bindings.
"""

import hashlib
import json
from pathlib import Path

import pytest

from src.conversational_analytics.evidence_index import (
    EvidenceIndex,
    _approved,
    candidate_content_sha256,
    canonical_index_sha256,
)
from src.dashboard.news import build_news_payload

PIN = "9f8f12fc088cefce09f822d6647f5b46856e6ee7b600c5a1750db0c3e5f07005"


@pytest.fixture
def current_index(monkeypatch):
    monkeypatch.setenv("CHAT_EVIDENCE_APPROVED_INDEX_SHA256", PIN)
    return EvidenceIndex("config/chat/evidence/approved-index.json")


def test_only_the_exact_twenty_three_news_items_were_added(current_index):
    raw = Path("config/chat/evidence/approved-index.json").read_bytes()
    payload = json.loads(raw)
    proof = json.loads(Path("config/news/approved-batch-20261102.json").read_bytes())
    assert proof["proposal_sha256"] == "907971ca7e811a914f4fdb44920e146882d5b0b74db50b53f0d54bcbcb866df4"
    assert hashlib.sha256(raw).hexdigest() == proof["approved_index_raw_sha256"]
    assert canonical_index_sha256(payload) == PIN
    assert len(payload["records"]) == 33 and len(current_index.records) == 33
    added = payload["records"][10:]
    expected = {r["id"]: r["candidate_content_sha256"] for r in proof["approved_items"]}
    assert len(added) == len(expected) == 23
    assert {r["id"]: candidate_content_sha256(r) for r in added} == expected
    assert all(r["kind"] == "news" and _approved(r) for r in added)
    assert sum(r["kind"] == "report" for r in payload["records"]) == 7
    assert all(
        r["source"]["sha256_semantics"] == "reviewed_observation_not_original_page_bytes" for r in added
    )


def test_normal_consumer_has_twenty_six_approved_cards_and_all_provenance(current_index):
    payload = build_news_payload()
    assert payload["mode"] == "approved_only"
    assert len(payload["records"]) == 26
    assert sum(len(row["sources"]) for row in payload["records"]) == 27
    assert all(row["review_status"] == "owner_approved" for row in payload["records"])


def test_current_queries_use_new_approved_content_without_inventing_terminal_details(current_index):
    latest = current_index.search_news("¿Cuál es la última noticia de Aeroméxico?")
    assert latest["results"][0]["id"] == "editorial_c893377485071c9743ca850a"
    traffic = current_index.search_news("noticias de tráfico de Viva en septiembre de 2026")
    assert [row["id"] for row in traffic["results"]] == ["editorial_064e3505206a45920defc8ae"]
    assert current_index.search_news("noticias del AICM")["count"] > 0
    assert current_index.search_news("noticias de T2 del AICM")["count"] == 0
