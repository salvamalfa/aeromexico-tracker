"""Historical producer compatibility stays bound to the published anchor."""

import copy

import pytest

from src.publish import afac_history_scope as scope
from tests.test_afac_history_contract import ROOT


def test_historical_producer_replays_from_the_published_code_commit():
    anchor = scope.anchor(ROOT)
    manifest = scope.manifests.load_manifest(ROOT / "site")

    scope.verify_producer_pin(ROOT, anchor, manifest)


def test_changed_historical_fingerprint_still_fails(monkeypatch):
    anchor = copy.deepcopy(scope.anchor(ROOT))
    manifest = scope.manifests.load_manifest(ROOT / "site")
    monkeypatch.setattr(scope, "producer_version", lambda _repo: "0" * 64)
    monkeypatch.setattr(scope, "producer_version_at_commit", lambda *_args: "1" * 64)

    with pytest.raises(ValueError, match="differs from its inspected fingerprint"):
        scope.verify_producer_pin(ROOT, anchor, manifest)


def test_historical_verifier_commit_must_contain_the_committed_anchor(monkeypatch):
    anchor = scope.anchor(ROOT)
    manifest = scope.manifests.load_manifest(ROOT / "site")
    monkeypatch.setattr(scope, "producer_version", lambda _repo: "0" * 64)
    monkeypatch.setattr(
        scope.transport,
        "_git",
        lambda _repo, *args: b"different anchor" if args[0] == "show" else b"",
    )

    with pytest.raises(ValueError, match="does not contain the committed history anchor"):
        scope.verify_producer_pin(ROOT, anchor, manifest)
