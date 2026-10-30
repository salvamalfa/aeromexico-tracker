"""A revision replaces exactly one approved slot and replays both editions."""

import copy
import json

import pytest

from src.publish import approval_cohorts as cohorts
from tests.test_publish_approval_cohorts import commit, entry, expanded, payload_file
from tests.test_publish_approval_cohorts import publication as publication


@pytest.fixture
def revision(publication):
    p = publication
    trusted, baseline = expanded(p)
    previous = copy.deepcopy(p["pending"])
    (p["root"] / "code").write_text("source-replayed revision producer")
    producer = commit(p["root"])
    new_entry, raw = entry("2026Q3", "c"), b'{"thesis":"revision"}'
    row = payload_file("2026Q3", raw)
    config = {
        "schema_version": cohorts.SCHEMA,
        "cohorts": [
            {
                "implementation_commit": producer,
                "analysis_manifest": [new_entry],
                "files": [row],
            }
        ],
    }
    (p["root"] / cohorts.CONFIG).write_text(json.dumps(config))
    commit(p["root"])
    pending = {
        "entry": new_entry,
        "file": row,
        "bytes": raw,
        "replaces": {"entry": previous["entry"], "file": previous["file"]},
    }
    return {
        **p,
        "trusted": trusted,
        "baseline": baseline,
        "pending": pending,
        "previous": previous,
        "producer": producer,
        "revision_config": config,
    }


def test_revision_keeps_history_and_exact_new_approval(revision):
    p = revision
    plan, payloads = cohorts.approval_plan(p["root"], p["trusted"], p["baseline"], pending=p["pending"])
    assert plan[0]["analysis_manifest"] == p["baseline"]["analysis_manifest"][:1]
    assert plan[1]["analysis_manifest"] == [p["pending"]["entry"]]
    assert plan[1]["implementation_commit"] == p["producer"]
    assert payloads[p["pending"]["file"]["path"]] == {"thesis": "revision"}
    # Old approval metadata remains physically present in the trusted Git tree.
    assert p["previous"]["entry"] in p["baseline"]["analysis_manifest"]


def test_preparing_same_committed_pins_keeps_original_producer(revision):
    from src.publish import issuer_update

    p = revision
    spec = {"same_source_and_outputs": True}
    (p["root"] / issuer_update.ANCHOR).write_text(json.dumps(spec))
    pins_commit = commit(p["root"])
    fresh = copy.deepcopy(p["revision_config"]["cohorts"][0])
    fresh["implementation_commit"] = pins_commit
    stable = issuer_update._stable_cohort(p["root"], spec, fresh)
    assert stable["implementation_commit"] == p["producer"]
    assert issuer_update._stable_cohort(p["root"], {"same_source_and_outputs": False}, fresh) == fresh


@pytest.mark.parametrize("mutation", ["old_version", "old_quarter", "old_file", "new_entity", "same_version"])
def test_revision_cannot_guess_or_change_previous_slot(revision, mutation):
    p = revision
    pending = copy.deepcopy(p["pending"])
    if mutation == "old_version":
        pending["replaces"]["entry"]["version"] = "f" * 64
    elif mutation == "old_quarter":
        pending["replaces"]["entry"]["period_id"] = "2026Q2"
    elif mutation == "old_file":
        pending["replaces"]["file"]["sha256"] = "f" * 64
    elif mutation == "new_entity":
        pending["entry"]["entity_key"] = "VOLARIS"
    else:
        pending["entry"]["version"] = pending["replaces"]["entry"]["version"]
    with pytest.raises(ValueError):
        cohorts.approval_plan(p["root"], p["trusted"], p["baseline"], pending=pending)


def test_revision_cannot_rewrite_another_cohort(revision):
    p = revision
    config = copy.deepcopy(p["revision_config"])
    config["cohorts"].insert(
        0,
        {
            "implementation_commit": p["old_code"],
            "analysis_manifest": p["baseline"]["analysis_manifest"][:1],
            "files": p["baseline"]["files"][:1],
        },
    )
    (p["root"] / cohorts.CONFIG).write_text(json.dumps(config))
    commit(p["root"])
    with pytest.raises(ValueError, match="exactly one"):
        cohorts.approval_plan(p["root"], p["trusted"], p["baseline"], pending=p["pending"])


@pytest.mark.parametrize("bad", [None, "old_revoked", "old_payload", "new_unapproved"])
def test_revision_replays_old_and_new_without_revoking_history(revision, monkeypatch, bad):
    from src.publish import frozen_data

    p = revision
    ledger = p["root"] / "analysis_runs/lifecycle"
    paths = []
    for identity in [p["baseline"]["analysis_manifest"][0], p["pending"]["entry"]]:
        path = p["root"] / "analysis_runs/drafts" / identity["period_id"] / (identity["version"] + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"draft": {"period_id": identity["period_id"]}, "version": identity["version"]})
        )
        paths.append(path)
    calls = []

    def replay(selected, code, root, **kwargs):
        calls.append(code)
        if code == p["new_code"]:
            if bad == "old_revoked":
                raise ValueError("old approval revoked")
            return {
                "authorized": [p["previous"]["entry"]],
                "payloads": [{"thesis": "changed" if bad == "old_payload" else "new"}],
            }
        if code == p["producer"]:
            if bad == "new_unapproved":
                raise ValueError("new version has no approval")
            return {"authorized": [p["pending"]["entry"]], "payloads": [{"thesis": "revision"}]}
        return {"authorized": [p["baseline"]["analysis_manifest"][0]], "payloads": [{"thesis": "old"}]}

    monkeypatch.setattr(frozen_data, "verify_baseline_approvals", replay)
    if bad:
        with pytest.raises(ValueError):
            cohorts.verify_approval_cohorts(
                paths, p["root"], p["trusted"], p["baseline"], ledger, pending=p["pending"]
            )
    else:
        result = cohorts.verify_approval_cohorts(
            paths, p["root"], p["trusted"], p["baseline"], ledger, pending=p["pending"]
        )
        assert calls == [p["new_code"], p["old_code"], p["producer"]]
        assert result["authorized"][-1] == p["pending"]["entry"]
