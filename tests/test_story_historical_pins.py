"""Prior approval pins are explicit cohort authority, never inferred from data."""

import copy
import json
from pathlib import Path

import pytest

from src.publish import story_historical_pins as pins

ROOT = Path(__file__).resolve().parents[1]
OLD = "1cd0455ac1944849d567c96f7147c3f393d17333dac2c28b70459e4f7887334f"
NEW = "9f8f12fc088cefce09f822d6647f5b46856e6ee7b600c5a1750db0c3e5f07005"


@pytest.fixture
def cohort(tmp_path, monkeypatch):
    batch = (ROOT / pins.BATCH).read_bytes()
    current = (ROOT / pins.INDEX).read_bytes()
    old = (ROOT / "tests/fixtures/news/approved-index-20261012.json").read_bytes()
    for name, raw in ((pins.BATCH, batch), (pins.INDEX, current)):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    blobs = {f"HEAD:{pins.BATCH}": batch, f"baseline:{pins.INDEX}": old, f"code:{pins.INDEX}": old}
    monkeypatch.setattr(pins.transport, "_git", lambda root, command, ref: blobs[ref])
    monkeypatch.setattr(pins.transport, "baseline", lambda *args: ({"code_commit": "code"}, b"manifest"))
    monkeypatch.setenv(pins.PIN, NEW)
    monkeypatch.setenv("CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256", "b" * 64)
    return tmp_path, {"baseline_commit": "baseline"}, blobs


def test_exact_approved_historical_cohort_gets_only_its_original_pin(cohort):
    repo, spec, _ = cohort
    before = dict(pins.os.environ)
    environment = pins.historical_environment(repo, spec)
    assert environment[pins.PIN] == OLD
    assert environment == {**before, pins.PIN: OLD}
    assert dict(pins.os.environ) == before


@pytest.mark.parametrize("value", ["", "malformed", OLD, "a" * 64])
def test_current_external_approval_is_still_required(cohort, monkeypatch, value):
    repo, spec, _ = cohort
    monkeypatch.setenv(pins.PIN, value)
    with pytest.raises(ValueError):
        pins.historical_environment(repo, spec)
    assert pins.os.environ[pins.PIN] == value


@pytest.mark.parametrize("field", ["base_index_raw_sha256", "base_index_canonical_sha256"])
def test_rewritten_prior_authority_is_not_a_new_trust_anchor(cohort, field):
    repo, spec, blobs = cohort
    batch = json.loads((repo / pins.BATCH).read_bytes())
    batch["decision"][field] = "f" * 64
    raw = json.dumps(batch).encode()
    (repo / pins.BATCH).write_bytes(raw)
    blobs[f"HEAD:{pins.BATCH}"] = raw
    with pytest.raises(ValueError, match="exact committed owner batch"):
        pins.historical_environment(repo, spec)


def test_uncommitted_approval_batch_is_rejected(cohort):
    repo, spec, blobs = cohort
    blobs[f"HEAD:{pins.BATCH}"] = b"uncommitted authority"
    with pytest.raises(ValueError, match="exact committed owner batch"):
        pins.historical_environment(repo, spec)


@pytest.mark.parametrize("mutation", ["new_33", "modified_old", "code_drift"])
def test_different_baseline_or_original_verifier_index_is_rejected(cohort, mutation):
    repo, spec, blobs = cohort
    if mutation == "new_33":
        changed = (repo / pins.INDEX).read_bytes()
    else:
        document = json.loads(blobs[f"baseline:{pins.INDEX}"])
        document["records"][0]["id"] += "-changed"
        changed = json.dumps(document).encode()
    if mutation != "code_drift":
        blobs[f"baseline:{pins.INDEX}"] = changed
    blobs[f"code:{pins.INDEX}"] = changed
    with pytest.raises(ValueError, match="different News indexes|explicitly approved prior cohort"):
        pins.historical_environment(repo, spec)


def test_changed_current_index_cannot_grant_its_own_external_approval(cohort, monkeypatch):
    repo, spec, _ = cohort
    payload = json.loads((repo / pins.INDEX).read_bytes())
    payload["records"][0]["id"] += "-changed"
    (repo / pins.INDEX).write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv(pins.PIN, pins.canonical_index_sha256(payload))
    with pytest.raises(ValueError, match="owner's approved batch"):
        pins.historical_environment(repo, spec)


def test_only_original_verifier_subprocess_receives_prior_pin(cohort, monkeypatch):
    repo, spec, _ = cohort
    calls = []
    monkeypatch.setattr(
        pins, "released_verifier",
        lambda *args, **kwargs: calls.append((args, copy.deepcopy(kwargs))) or {"verified": True},
    )
    assert pins.verify_historical_baseline(repo, spec, repo / "site") == {"verified": True}
    assert len(calls) == 1 and calls[0][1]["environment"][pins.PIN] == OLD
    assert pins.os.environ[pins.PIN] == NEW
