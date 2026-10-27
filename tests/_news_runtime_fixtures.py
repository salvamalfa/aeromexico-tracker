"""One real immutable snapshot; independent chat state remains per case."""

from copy import deepcopy
from pathlib import Path

import pytest
from src.conversational_analytics.data.snapshot import Snapshot

ROOT = Path(__file__).resolve().parents[1]


def _pin_approved_content(monkeypatch):
    monkeypatch.setenv(
        "CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256",
        "644eb640124297fc63b306836607aea6e4b0be424b85e67b902cc9f5407153ae",
    )
    monkeypatch.setenv("CHAT_PROMPT_VERSION", "r2-proposed")
    monkeypatch.setenv(
        "CHAT_PROMPT_APPROVAL_RECEIPT_SHA256",
        "0b5b87e1381decdac4289593877a59ff9e91d763e216e78b5977fe2b5fe687f9",
    )
    monkeypatch.setenv(
        "CHAT_EVIDENCE_APPROVED_INDEX_SHA256",
        "1cd0455ac1944849d567c96f7147c3f393d17333dac2c28b70459e4f7887334f",
    )


@pytest.fixture(autouse=True)
def approved_pins(monkeypatch):
    _pin_approved_content(monkeypatch)


def _state(snapshot):
    return (
        dict(snapshot.manifest),
        dict(snapshot._payloads),
        snapshot._catalog,
        snapshot.version,
        snapshot.semantic_version,
    )


@pytest.fixture(scope="module")
def published_snapshot():
    # Only construction uses this temporary context. The original function
    # fixture still sets and restores the same pins for every individual case.
    with pytest.MonkeyPatch.context() as pins:
        _pin_approved_content(pins)
        snapshot = Snapshot(ROOT / "site")
    before = deepcopy(_state(snapshot))
    yield snapshot
    assert _state(snapshot) == before, "A consumer mutated the shared public snapshot"
