"""Exact historical inputs for a frozen campaign, separate from today's audit."""

import hashlib
import json
import os
import subprocess
import tarfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.evidence_index import (
    APPROVED_INDEX_SHA256_ENV,
    EvidenceIndex,
)
from src.publish.manifest import file_entries

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL_COMMIT = "4c8dd92a911a9797c253b47d915093f5014da20c"
HISTORICAL_MANIFEST_SHA256 = "be17ab16d78faae4cbe1fa5b2e2b18ebb8304d52eee17c4e13c880654f35ba71"
HISTORICAL_NEWS_PIN = "1cd0455ac1944849d567c96f7147c3f393d17333dac2c28b70459e4f7887334f"


@contextmanager
def historical_stage2_snapshot(destination: Path):
    """Restore the whole publication, retaining its manifest and original pin.

    These constants identify a historical release, not a new approval. The old
    news pin applies only while auditing that exact data/config tree; the
    caller's current pin is restored even if an assertion fails.
    """
    destination.mkdir(parents=True)
    archive = destination / "historical-inputs.tar"
    subprocess.run(
        ["git", "archive", "--format=tar", "--output", str(archive), HISTORICAL_COMMIT,
         "site", "contracts/web", "contracts/chat", "config/chat"],
        cwd=ROOT, check=True, capture_output=True,
    )
    with tarfile.open(archive) as source:
        source.extractall(destination, filter="data")
    site = destination / "site"
    raw = (site / "publication_manifest.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == HISTORICAL_MANIFEST_SHA256
    manifest = json.loads(raw)
    expected = {row["path"]: row for row in manifest["files"]}
    assert len(expected) == len(manifest["files"]) == 809
    assert {row["path"]: row for row in file_entries(site)} == expected
    current_pin = os.environ.get(APPROVED_INDEX_SHA256_ENV)
    try:
        with pytest.MonkeyPatch.context() as historical_pin:
            historical_pin.setenv(APPROVED_INDEX_SHA256_ENV, HISTORICAL_NEWS_PIN)
            index = EvidenceIndex(destination / "config/chat/evidence/approved-index.json")
            assert index.sha256 == HISTORICAL_NEWS_PIN
            snapshot = Snapshot(site)
            assert dict(snapshot.manifest) == manifest
            yield snapshot
            assert (site / "publication_manifest.json").read_bytes() == raw
            assert {row["path"]: row for row in file_entries(site)} == expected
    finally:
        assert os.environ.get(APPROVED_INDEX_SHA256_ENV) == current_pin
