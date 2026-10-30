"""Parity consumers accept reviewed issuer chains and reject unrelated changes."""

import copy

import pytest

from src.publish import issuer_scope
from tests import _site_publication_parity as parity


def raw(value):
    return parity.encoded(value)


def block():
    return {
        "records": [{"period_id": "2026Q2", "value": 10}],
        "views": {"2026Q2": {"period_id": "2026Q2", "value": 10}},
        "first_period": "2026Q2",
        "last_period": "2026Q2",
        "quarter_count": 1,
    }


def baseline():
    return {
        "records": [{"period_id": "2026Q3", "value": 50}],
        "views": {"2026Q3": {"value": 50}},
        "metadata": {"default_period": "2026Q2"},
        "entities": {key: block() for key in ["AEROMEXICO", "VIVA_AEROBUS", "VOLARIS", "INDUSTRY"]},
    }


def append(before, entity):
    after = copy.deepcopy(before)
    b = after["entities"][entity]
    b["records"].append({"period_id": "2026Q3", "value": 20})
    b["views"]["2026Q3"] = {"period_id": "2026Q3", "value": 20}
    b["last_period"], b["quarter_count"] = "2026Q3", 2
    return after


def chain(tmp_path, monkeypatch, entities):
    original = baseline()
    docs = [original]
    for entity in entities:
        docs.append(append(docs[-1], entity))
    manifests = [{"files": []}] + [{"files": [{"path": issuer_scope.PROOF}]} for _ in entities]
    commits = [str(i) * 40 for i in range(len(docs))]
    specs = []
    for index, entity in enumerate(entities):
        specs.append(
            {
                "entity_key": entity,
                "period_id": "2026Q3",
                "stage": "combined",
                "executive_sha256": parity.sha(raw(docs[index + 1])),
                "executive_bytes": len(raw(docs[index + 1])),
                "baseline_commit": commits[index],
                "baseline_manifest_sha256": parity.sha(raw(manifests[index])),
            }
        )
    site = tmp_path / "site"
    (site / "data/v1").mkdir(parents=True)
    (site / issuer_scope.EXECUTIVE).write_bytes(raw(docs[-1]))
    (site / "publication_manifest.json").write_bytes(raw(manifests[-1]))
    anchor = tmp_path / issuer_scope.ANCHOR
    anchor.parent.mkdir(parents=True)
    anchor.write_bytes(raw(specs[-1]))
    objects = {}
    for index, commit in enumerate(commits):
        objects[f"{commit}:site/{issuer_scope.EXECUTIVE}"] = raw(docs[index])
        objects[f"{commit}:site/publication_manifest.json"] = raw(manifests[index])
        if index:
            objects[f"{commit}:{issuer_scope.ANCHOR}"] = raw(specs[index - 1])
    monkeypatch.setattr(parity, "_git", lambda repo, action, obj: objects[obj])
    financial = {"executive_sha256": parity.sha(raw(original)), "executive_bytes": len(raw(original))}
    return site, financial, original, docs, specs


@pytest.mark.parametrize("entities", [["VIVA_AEROBUS"], ["VIVA_AEROBUS", "VOLARIS"]])
def test_exact_issuer_chain_retains_original_financial_projection(tmp_path, monkeypatch, entities):
    site, spec, original, _, _ = chain(tmp_path, monkeypatch, entities)
    assert parity.preserved_financial_projection(site, tmp_path, spec) == original


@pytest.mark.parametrize("mutation", ["AM_root", "AM_entity", "industry", "peer", "historical", "metadata"])
def test_resigned_issuer_output_cannot_change_other_slots(tmp_path, monkeypatch, mutation):
    site, spec, _, docs, specs = chain(tmp_path, monkeypatch, ["VIVA_AEROBUS"])
    changed = docs[-1]
    if mutation == "AM_root":
        changed["records"][0]["value"] += 1
    elif mutation == "AM_entity":
        changed["entities"]["AEROMEXICO"]["records"][0]["value"] += 1
    elif mutation in {"industry", "peer"}:
        key = "INDUSTRY" if mutation == "industry" else "VOLARIS"
        changed["entities"][key]["views"]["2026Q2"]["value"] += 1
    elif mutation == "historical":
        changed["entities"]["VIVA_AEROBUS"]["records"][0]["value"] += 1
    else:
        changed["metadata"]["default_period"] = "2026Q3"
    (site / issuer_scope.EXECUTIVE).write_bytes(raw(changed))
    # Even matching newly pinned bytes cannot bypass semantic preservation.
    specs[-1]["executive_sha256"] = parity.sha(raw(changed))
    specs[-1]["executive_bytes"] = len(raw(changed))
    (tmp_path / issuer_scope.ANCHOR).write_bytes(raw(specs[-1]))
    with pytest.raises(ValueError):
        parity.preserved_financial_projection(site, tmp_path, spec)


@pytest.mark.parametrize(
    "failure", ["approval changed", "source changed", "output changed", "missing receipt"]
)
def test_strict_issuer_failure_never_falls_back(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(parity, "verifier_for", lambda site: "src.publish.issuer_scope")
    called = []
    monkeypatch.setattr(issuer_scope, "verify_issuer", lambda *args: called.append(args) or [failure])
    with pytest.raises(AssertionError, match=failure):
        parity.verify_current_publication(tmp_path, tmp_path, lambda *args: pytest.fail("fallback"))
    assert len(called) == 1


def test_historical_approval_or_payload_changes_are_rejected(tmp_path, monkeypatch):
    name = "data/v1/analysis/2026Q3.json"
    entry = {"entity_key": "AEROMEXICO", "version": "approved"}
    before = {
        "analysis_manifest": [entry],
        "files": [{"path": name, "sha256": parity.sha(b"original"), "bytes": 8}],
    }
    monkeypatch.setattr(parity, "_git", lambda *args: raw(before))
    (tmp_path / "publication_manifest.json").write_bytes(raw({"analysis_manifest": []}))
    with pytest.raises(AssertionError, match="approval changed"):
        parity.preserved_readings(tmp_path, tmp_path, {"baseline_commit": "old"})
    (tmp_path / "publication_manifest.json").write_bytes(raw({"analysis_manifest": [entry]}))
    (tmp_path / name).parent.mkdir(parents=True)
    (tmp_path / name).write_bytes(b"changed!")
    with pytest.raises(AssertionError, match="2026Q3"):
        parity.preserved_readings(tmp_path, tmp_path, {"baseline_commit": "old"})
