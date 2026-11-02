"""Exact historical approved corpus for the historical eleven-item preview tests.

This public fixture is copied byte-for-byte from origin/master. It does not
replace the current production corpus, which has separate activation tests.
"""

import hashlib
from pathlib import Path

import pytest

from src.conversational_analytics.evidence_index import EvidenceIndex


@pytest.fixture
def legacy_news_index(monkeypatch):
    path = Path(__file__).parent / "fixtures/news/approved-index-20261012.json"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == (
        "5fba922f7b6186a5ee0c31d9f678c3222a11fb50e9cf7d5b2f26b62212516672"
    )
    monkeypatch.setenv(
        "CHAT_EVIDENCE_APPROVED_INDEX_SHA256",
        "1cd0455ac1944849d567c96f7147c3f393d17333dac2c28b70459e4f7887334f",
    )
    index = EvidenceIndex(path)  # Normal receipt and canonical-pin verification.
    monkeypatch.setattr("src.dashboard.news.EvidenceIndex", lambda _: index)
    return index
