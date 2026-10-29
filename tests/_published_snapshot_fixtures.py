"""Share a real verified snapshot within a module, checking each consumer."""

from copy import deepcopy
from pathlib import Path

import pytest

from src.conversational_analytics.data.snapshot import Snapshot

ROOT = Path(__file__).resolve().parents[1]


def _state(snapshot):
    return (
        snapshot.root,
        snapshot.project_root,
        dict(snapshot.manifest),
        dict(snapshot._payloads),
        snapshot._catalog,
        snapshot.version,
        snapshot.semantic_version,
    )


@pytest.fixture(scope="module")
def _verified_published_snapshot():
    # Keep real construction and all verification. Never reuse this fixture in
    # tests that alter files, contracts, approval pins or Snapshot validation.
    snapshot = Snapshot(ROOT / "site")
    return snapshot, deepcopy(_state(snapshot))


@pytest.fixture
def published_snapshot(_verified_published_snapshot):
    snapshot, before = _verified_published_snapshot
    yield snapshot
    assert _state(snapshot) == before, "A consumer mutated the shared public snapshot"
