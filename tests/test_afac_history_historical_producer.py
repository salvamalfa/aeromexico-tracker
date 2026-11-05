"""Historical producer compatibility stays bound to the published anchor."""

import copy
import json

import pytest

from src.publish import afac_history_scope as scope
from tests.test_afac_history_contract import PUBLISHED_HISTORY, ROOT


@pytest.fixture(scope="module")
def historical_manifest():
    raw = scope.transport._git(ROOT, "show", f"{PUBLISHED_HISTORY}:site/publication_manifest.json")
    assert scope.sha(raw) == "913a2af1d3bf0c0e792dd489bd4e7f53863954311a12b3e7ec41f1fde4b83413"
    return json.loads(raw)


def test_historical_producer_replays_from_the_published_code_commit(historical_manifest):
    anchor = scope.anchor(ROOT)

    scope.verify_producer_pin(ROOT, anchor, historical_manifest)


def test_changed_historical_fingerprint_still_fails(monkeypatch, historical_manifest):
    anchor = copy.deepcopy(scope.anchor(ROOT))
    monkeypatch.setattr(scope, "producer_version", lambda _repo: "0" * 64)
    monkeypatch.setattr(scope, "producer_version_at_commit", lambda *_args: "1" * 64)

    with pytest.raises(ValueError, match="differs from its inspected fingerprint"):
        scope.verify_producer_pin(ROOT, anchor, historical_manifest)


def test_historical_verifier_commit_must_contain_the_committed_anchor(monkeypatch, historical_manifest):
    anchor = scope.anchor(ROOT)
    monkeypatch.setattr(scope, "producer_version", lambda _repo: "0" * 64)
    monkeypatch.setattr(
        scope.transport,
        "_git",
        lambda _repo, *args: b"different anchor" if args[0] == "show" else b"",
    )

    with pytest.raises(ValueError, match="does not contain the committed history anchor"):
        scope.verify_producer_pin(ROOT, anchor, historical_manifest)
