"""Historical producer compatibility stays bound to the published anchor."""

import copy
import json

import pytest

from src.publish import afac_history_scope as scope
from tests.test_afac_history_contract import PUBLISHED_HISTORY, ROOT


@pytest.fixture(scope="module")
def historical_publication(tmp_path_factory):
    raw = scope.transport._git(ROOT, "show", f"{PUBLISHED_HISTORY}:site/publication_manifest.json")
    assert scope.sha(raw) == "913a2af1d3bf0c0e792dd489bd4e7f53863954311a12b3e7ec41f1fde4b83413"
    site = tmp_path_factory.mktemp("afac-published-producer")
    index = scope.transport._git(ROOT, "show", f"{PUBLISHED_HISTORY}:site/index.html")
    manifest = json.loads(raw)
    pin = next(row for row in manifest["files"] if row["path"] == "index.html")
    assert len(index) == pin["bytes"] and scope.sha(index) == pin["sha256"]
    (site / "index.html").write_bytes(index)
    return manifest, site


def test_historical_producer_replays_from_the_published_code_commit(historical_publication):
    anchor = scope.anchor(ROOT)
    manifest, site = historical_publication

    scope.verify_producer_pin(ROOT, anchor, manifest, site)


def test_changed_historical_fingerprint_still_fails(monkeypatch, historical_publication):
    anchor = copy.deepcopy(scope.anchor(ROOT))
    manifest, site = historical_publication
    monkeypatch.setattr(scope, "producer_version", lambda _repo: "0" * 64)
    monkeypatch.setattr(scope, "producer_version_at_commit", lambda *_args: "1" * 64)

    with pytest.raises(ValueError, match="differs from its inspected fingerprint"):
        scope.verify_producer_pin(ROOT, anchor, manifest, site)


def test_historical_verifier_commit_must_contain_the_committed_anchor(monkeypatch, historical_publication):
    anchor = scope.anchor(ROOT)
    manifest, site = historical_publication
    monkeypatch.setattr(scope, "producer_version", lambda _repo: "0" * 64)
    monkeypatch.setattr(
        scope.transport,
        "_git",
        lambda _repo, *args: b"different anchor" if args[0] == "show" else b"",
    )

    with pytest.raises(ValueError, match="does not contain the committed history anchor"):
        scope.verify_producer_pin(ROOT, anchor, manifest, site)
