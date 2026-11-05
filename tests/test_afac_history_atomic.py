"""Real lock and atomic site swap around explicit synthetic replay boundaries."""

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.publish import afac_history_contract as contract
from src.publish import afac_history_update as update
from src.publish import gate, manifest, verify


@pytest.fixture
def publication(tmp_path, monkeypatch):
    """No fake production authority: all historical/native data are test-only.

    The real gate's writer lock, repeated comparisons, pre-swap callback,
    assemble_site rollback and paired receipt writer remain in execution.
    Full source/native/authority tests are separate modules, not mocked there.
    """
    ledger = tmp_path / "analysis_runs/lifecycle"
    site = tmp_path / "site"
    before = {"index.html": b"approved original frontend", "data/v1/market.json": b"old"}
    parent_raw = contract.encoded({"fixture": "unserved B", "files": contract.pins(before)})
    contract.materialize_site(site, parent_raw, before)
    approved = [
        {
            "entity_key": "AEROMEXICO",
            "period_id": "2026Q3",
            "version": "a" * 64,
            "approval_event": "b" * 64,
            "content_hash": "c" * 64,
            "evidence_fingerprint": "d" * 64,
            "audit_hash": "e" * 64,
        }
    ]
    spec = {
        "scope": {"candidate_parent": {"fixture": "B"}, "producer_code_version": "f" * 64},
        "members": [],
        "contracts": {},
        "authorization_sha256": "a" * 64,
        "source_audit_sha256": "b" * 64,
    }
    anchor_path = tmp_path / contract.ANCHOR
    anchor_path.parent.mkdir(parents=True)
    anchor_path.write_bytes(contract.encoded(spec))
    result = {
        "request": {"fixture": "synthetic decision"},
        "scope": spec["scope"],
        "members": [],
        "contracts": {},
        "outputs": {"data/v1/market.json": b"native corrected"},
        "authorized": approved,
        "state": {"native_source": "unchanged", "ledger": "unchanged"},
    }
    calls = {"evaluate": 0, "base": 0, "witness": 0, "receipts": 0, "validate": 0}
    monkeypatch.setattr(update, "PATHS", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(update.flow, "ROOT", ledger)
    monkeypatch.setattr(update, "committed_inputs", lambda _: None)
    monkeypatch.setattr(update.manifests, "current_commit", lambda *args: "1" * 40)
    monkeypatch.setattr(update.verification, "anchor", lambda _: copy.deepcopy(spec))
    monkeypatch.setattr(update.verification, "producer_version", lambda _: "f" * 64)
    monkeypatch.setattr(update, "parent_public", lambda *_: ({}, parent_raw, before, {}))
    monkeypatch.setattr(update, "authority", lambda *_: ("a" * 64, "b" * 64))

    def evaluate(*args, **kwargs):
        assert (ledger / "writer.lock").is_file()
        calls["evaluate"] += 1
        return copy.deepcopy(result)

    def baseline(*args, **kwargs):
        assert (ledger / "writer.lock").is_file()
        calls["base"] += 1

    def witness(*args):
        assert (ledger / "writer.lock").is_file()
        calls["witness"] += 1
        return {"fixture": "not a real witness"}

    def preserved(prepared, *_):
        assert (ledger / "writer.lock").is_file()
        assert (prepared / "index.html").read_bytes() == before["index.html"]
        calls["validate"] += 1
        return frozenset({"index.html"})

    monkeypatch.setattr(update, "evaluate", evaluate)
    monkeypatch.setattr(update, "require_current_base", baseline)
    monkeypatch.setattr(update.afac_history_witness, "witness_remote", witness)
    monkeypatch.setattr(update.verification, "witness", lambda *_: None)
    monkeypatch.setattr(update.verification, "preserved_files", preserved)
    monkeypatch.setattr(verify, "_verify_site", lambda *args, **kwargs: [])
    receipt_writer = gate.write_receipt

    def receipt(*args):
        calls["receipts"] += 1
        return receipt_writer(*args, root=ledger)

    monkeypatch.setattr(gate, "write_receipt", receipt)
    return SimpleNamespace(
        repo=tmp_path,
        ledger=ledger,
        site=site,
        before=before,
        raw=parent_raw,
        result=result,
        calls=calls,
        spec=spec,
    )


def assert_unswapped(value):
    assert (value.site / "index.html").read_bytes() == value.before["index.html"]
    assert (value.site / "data/v1/market.json").read_bytes() == b"old"
    assert (value.site / manifest.MANIFEST_NAME).read_bytes() == value.raw
    assert not (value.site / contract.PROOF).exists()
    assert value.calls["receipts"] == 0
    assert not (value.ledger / "writer.lock").exists()
    assert not list(value.repo.glob("site.tmp-*"))


def test_success_retains_frontend_and_writes_normal_local_receipts(publication):
    value = publication
    result = update.publish("synthetic request", value.site)
    assert result["status"] == "site_built_verified_not_served"
    assert (value.site / "data/v1/market.json").read_bytes() == b"native corrected"
    assert (value.site / "index.html").read_bytes() == value.before["index.html"]
    assert value.calls == {"evaluate": 3, "base": 2, "witness": 1, "receipts": 1, "validate": 1}
    assert result["manifest"]["analysis_manifest"] == value.result["authorized"]
    assert len(list((value.ledger / "publications").glob("*.json"))) == 2
    assert not (value.ledger / "writer.lock").exists()


@pytest.mark.parametrize(
    "race",
    [
        "native_source",
        "ledger",
        "pre_swap_source",
        "pre_swap_revocation",
        "scope",
        "members",
        "authority",
        "HEAD",
        "remote",
        "witness",
        "validation",
    ],
)
def test_any_late_source_revocation_or_code_race_aborts_without_swap(publication, monkeypatch, race):
    value = publication
    original = update.evaluate

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        if value.calls["evaluate"] >= 2:
            if race in {"native_source", "ledger"}:
                result["state"][race] = "changed"
            elif race == "scope":
                result["scope"]["unapproved_scope"] = True
            elif race == "members":
                result["members"] = ["another projection"]
        if value.calls["evaluate"] == 3 and race in {"pre_swap_source", "pre_swap_revocation"}:
            result["state"]["native_source" if race == "pre_swap_source" else "ledger"] = (
                "changed after validation"
            )
        return result

    monkeypatch.setattr(update, "evaluate", changed)
    if race == "authority":
        monkeypatch.setattr(
            update,
            "authority",
            lambda *_: ("c" * 64, "b" * 64) if value.calls["evaluate"] >= 2 else ("a" * 64, "b" * 64),
        )
    elif race == "HEAD":
        monkeypatch.setattr(
            update.manifests,
            "current_commit",
            lambda *args: "2" * 40 if value.calls["validate"] else "1" * 40,
        )
    elif race == "remote":

        def moved(*args, **kwargs):
            if value.calls["validate"]:
                raise ValueError("Actual remote moved")

        monkeypatch.setattr(update, "require_current_base", moved)
    elif race == "witness":
        monkeypatch.setattr(
            update.afac_history_witness,
            "witness_remote",
            lambda *_: (_ for _ in ()).throw(ValueError("503 exhausted")),
        )
    elif race == "validation":
        monkeypatch.setattr(verify, "_verify_site", lambda *args, **kwargs: ["wrong original file"])
    with pytest.raises(ValueError):
        update.publish("synthetic request", value.site)
    assert_unswapped(value)


def test_swap_filesystem_error_restores_original_site(publication, monkeypatch):
    value = publication
    rename = Path.rename

    def fail_candidate(path, target):
        if path.name.startswith("site.tmp-"):
            raise OSError("Synthetic failed atomic candidate rename")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", fail_candidate)
    with pytest.raises(OSError, match="atomic candidate"):
        update.publish("synthetic request", value.site)
    assert_unswapped(value)
    assert not list(value.repo.glob("site.prev-*"))


def test_existing_site_is_revalidated_but_never_claimed_as_deployed(publication, monkeypatch):
    value = publication
    update.publish("synthetic request", value.site)
    before = {p.relative_to(value.site): p.read_bytes() for p in value.site.rglob("*") if p.is_file()}
    monkeypatch.setattr(update.verification, "verify_afac_history", lambda *_: [])
    result = update.publish("synthetic request", value.site)
    assert result["status"] == "already_built_not_a_deployment_claim"
    assert {p.relative_to(value.site): p.read_bytes() for p in value.site.rglob("*") if p.is_file()} == before
    assert value.calls["witness"] == 1 and value.calls["receipts"] == 1
