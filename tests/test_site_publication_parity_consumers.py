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
    monkeypatch.setattr(parity, "_active_module", lambda *args: "src.publish.issuer_scope")
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
    monkeypatch.setattr(parity, "verifier_for", lambda site, repo: "src.publish.issuer_scope")
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


def movement_chain(tmp_path, monkeypatch):
    from src.publish import movements_scope

    site, financial, original, docs, _ = chain(tmp_path, monkeypatch, ["VIVA_AEROBUS", "VOLARIS"])
    git = parity._git
    commit = "2" * 40
    before = {
        "files": [{"path": issuer_scope.PROOF}],
        "analysis_manifest": [{"version": str(i)} for i in range(7)],
    }
    for index in range(7):
        name = f"data/v1/analysis/entity{index}/2026Q3.json"
        body = raw({"approved": "preserved", "version": index})
        (site / name).parent.mkdir(parents=True, exist_ok=True)
        (site / name).write_bytes(body)
        before["files"].append({"path": name, "sha256": parity.sha(body), "bytes": len(body)})
    spec = {"baseline_commit": commit, "baseline_manifest_sha256": parity.sha(raw(before))}
    anchor = tmp_path / movements_scope.ANCHOR
    anchor.parent.mkdir(parents=True, exist_ok=True)
    anchor.write_bytes(raw(spec))
    current = copy.deepcopy(before)
    current["files"].append({"path": movements_scope.PROOF})
    (site / "publication_manifest.json").write_bytes(raw(current))

    def read(repo, action, obj):
        if obj == f"{commit}:site/publication_manifest.json":
            return raw(before)
        if obj == f"{commit}:{movements_scope.ANCHOR}":
            return raw(spec)
        return git(repo, action, obj)

    monkeypatch.setattr(parity, "_git", read)
    monkeypatch.setattr(
        parity,
        "_active_module",
        lambda site, repo, manifest, at: (
            "src.publish.movements_scope" if at is None else "src.publish.issuer_scope"
        ),
    )
    return site, financial, original, docs, before, current, spec, anchor


def test_movement_correction_preserves_all_seven_theses_and_full_financial_source_chain(
    tmp_path, monkeypatch
):
    site, financial, original, *_ = movement_chain(tmp_path, monkeypatch)
    assert parity.preserved_financial_projection(site, tmp_path, financial) == original


@pytest.mark.parametrize(
    "mutation",
    ["executive", "approval", "thesis", "missing_thesis", "baseline_pin", "cycle", "unknown_profile"],
)
def test_movement_parity_never_accepts_a_foreign_financial_delta(tmp_path, monkeypatch, mutation):
    site, financial, _, docs, before, current, spec, anchor = movement_chain(tmp_path, monkeypatch)
    if mutation == "executive":
        changed = copy.deepcopy(docs[-1])
        changed["records"][0]["value"] += 1
        (site / issuer_scope.EXECUTIVE).write_bytes(raw(changed))
    elif mutation == "approval":
        current["analysis_manifest"][0]["version"] = "forged"
        (site / "publication_manifest.json").write_bytes(raw(current))
    elif mutation == "thesis":
        (site / before["files"][1]["path"]).write_bytes(b"changed")
    elif mutation == "missing_thesis":
        before["files"].pop()
        spec["baseline_manifest_sha256"] = parity.sha(raw(before))
        anchor.write_bytes(raw(spec))
    elif mutation == "baseline_pin":
        spec["baseline_manifest_sha256"] = "0" * 64
        anchor.write_bytes(raw(spec))
    elif mutation == "cycle":
        monkeypatch.setattr(parity, "_active_module", lambda *args: "src.publish.movements_scope")
    else:
        monkeypatch.setattr(parity, "_active_module", lambda *args: "src.publish.unknown")
    with pytest.raises(AssertionError):
        parity.preserved_financial_projection(site, tmp_path, financial)


def test_strict_movement_verification_failure_is_not_replaced_by_generic_or_issuer(tmp_path, monkeypatch):
    from src.publish import movements_scope

    monkeypatch.setattr(parity, "verifier_for", lambda site, repo: "src.publish.movements_scope")
    called = []
    monkeypatch.setattr(
        movements_scope, "verify_movements", lambda *args: called.append(args) or ["invalid original source"]
    )
    monkeypatch.setattr(issuer_scope, "verify_issuer", lambda *args: pytest.fail("issuer fallback"))
    with pytest.raises(AssertionError, match="invalid original source"):
        parity.verify_current_publication(tmp_path, tmp_path, lambda *args: pytest.fail("financial fallback"))
    assert len(called) == 1


def test_unknown_strict_verifier_is_not_replaced_by_generic(tmp_path, monkeypatch):
    monkeypatch.setattr(parity, "verifier_for", lambda site, repo: "src.publish.future_gate")
    with pytest.raises(AssertionError, match="Unsupported strict publication verifier"):
        parity.verify_current_publication(tmp_path, tmp_path, lambda *args: pytest.fail("fallback"))


def source_data_chain(tmp_path, monkeypatch, layers=1):
    from src.publish import movements_scope, source_data_scope

    site, financial, original, docs, _, movement, movement_spec, _ = movement_chain(
        tmp_path, monkeypatch
    )
    previous_git = parity._git
    objects = {}
    previous = copy.deepcopy(movement)
    specs = []
    for index in range(layers):
        commit = str(index + 3) * 40
        objects[f"{commit}:site/publication_manifest.json"] = previous
        objects[f"{commit}:site/{issuer_scope.EXECUTIVE}"] = raw(docs[-1])
        objects[f"{commit}:{movements_scope.ANCHOR}"] = movement_spec
        for pin in previous["files"]:
            if pin["path"].startswith("data/v1/analysis/"):
                objects[f"{commit}:site/{pin['path']}"] = (site / pin["path"]).read_bytes()
        if specs:
            objects[f"{commit}:{source_data_scope.ANCHOR}"] = specs[-1]
        spec = {
            "baseline_commit": commit,
            "baseline_manifest_sha256": parity.sha(raw(previous)),
        }
        specs.append(spec)
        current = copy.deepcopy(previous)
        if not any(pin["path"] == source_data_scope.PROOF for pin in current["files"]):
            current["files"].append({"path": source_data_scope.PROOF})
        previous = current
    anchor = tmp_path / source_data_scope.ANCHOR
    anchor.write_bytes(raw(specs[-1]))
    (site / "publication_manifest.json").write_bytes(raw(current))

    def read(repo, action, obj):
        if obj in objects:
            value = objects[obj]
            return value if isinstance(value, bytes) else raw(value)
        return previous_git(repo, action, obj)

    monkeypatch.setattr(parity, "_git", read)
    def active(site, repo, manifest, at):
        if at is None or at in {str(i + 3) * 40 for i in range(1, layers)}:
            return "src.publish.source_data_scope"
        if at == "3" * 40:
            return "src.publish.movements_scope"
        return "src.publish.issuer_scope"

    monkeypatch.setattr(parity, "_active_module", active)
    return site, financial, original, docs, objects, current, specs[-1], anchor


@pytest.mark.parametrize("layers", [1, 2])
def test_source_data_replays_movement_and_issuer_history_without_changing_financials(
    tmp_path, monkeypatch, layers
):
    site, financial, original, *_ = source_data_chain(tmp_path, monkeypatch, layers)
    assert parity.preserved_financial_projection(site, tmp_path, financial) == original


@pytest.mark.parametrize(
    "mutation",
    [
        "executive",
        "approval",
        "thesis",
        "missing_thesis",
        "baseline_pin",
        "missing_receipt",
        "cycle",
        "unknown_profile",
        "historical_thesis",
    ],
)
def test_source_data_parity_never_hides_financial_or_historical_damage(
    tmp_path, monkeypatch, mutation
):
    from src.publish import source_data_scope

    site, financial, _, docs, objects, current, spec, anchor = source_data_chain(tmp_path, monkeypatch)
    before = objects["3" * 40 + ":site/publication_manifest.json"]
    thesis = next(pin for pin in before["files"] if pin["path"].startswith("data/v1/analysis/"))
    if mutation == "executive":
        changed = copy.deepcopy(docs[-1])
        changed["records"][0]["value"] += 1
        (site / issuer_scope.EXECUTIVE).write_bytes(raw(changed))
    elif mutation == "approval":
        current["analysis_manifest"][0]["version"] = "forged"
        (site / "publication_manifest.json").write_bytes(raw(current))
    elif mutation == "thesis":
        (site / thesis["path"]).write_bytes(b"changed")
    elif mutation == "historical_thesis":
        objects["3" * 40 + ":site/" + thesis["path"]] = b"changed in movement history"
    elif mutation == "missing_thesis":
        before["files"].remove(thesis)
        spec["baseline_manifest_sha256"] = parity.sha(raw(before))
        anchor.write_bytes(raw(spec))
    elif mutation == "baseline_pin":
        spec["baseline_manifest_sha256"] = "0" * 64
        anchor.write_bytes(raw(spec))
    elif mutation == "missing_receipt":
        current["files"] = [pin for pin in current["files"] if pin["path"] != source_data_scope.PROOF]
        (site / "publication_manifest.json").write_bytes(raw(current))
    elif mutation == "cycle":
        monkeypatch.setattr(parity, "_active_module", lambda *args: "src.publish.source_data_scope")
    else:
        monkeypatch.setattr(parity, "_active_module", lambda *args: "src.publish.unknown")
    with pytest.raises(AssertionError):
        parity.preserved_financial_projection(site, tmp_path, financial)


def test_source_data_receipt_still_requires_preservation_when_executive_pin_already_matches(
    tmp_path, monkeypatch
):
    site, _, _, docs, objects, _, _, _ = source_data_chain(tmp_path, monkeypatch)
    expected = {"executive_sha256": parity.sha(raw(docs[-1])), "executive_bytes": len(raw(docs[-1]))}
    thesis = next(
        pin for pin in objects["3" * 40 + ":site/publication_manifest.json"]["files"]
        if pin["path"].startswith("data/v1/analysis/")
    )
    (site / thesis["path"]).write_bytes(b"changed despite equal executive")
    with pytest.raises(AssertionError, match="entity0"):
        parity.preserved_financial_projection(site, tmp_path, expected)


@pytest.mark.parametrize("failure", [None, "source changed", "missing receipt", "baseline changed"])
def test_strict_source_data_verifier_is_required_without_generic_or_issuer_fallback(
    tmp_path, monkeypatch, failure
):
    from src.publish import source_data_scope, verify

    monkeypatch.setattr(parity, "verifier_for", lambda *args: "src.publish.source_data_scope")
    calls = []
    monkeypatch.setattr(
        source_data_scope,
        "verify_source_data",
        lambda *args: calls.append(args) or ([] if failure is None else [failure]),
    )
    monkeypatch.setattr(issuer_scope, "verify_issuer", lambda *args: pytest.fail("issuer fallback"))
    monkeypatch.setattr(verify, "verify_site", lambda *args: pytest.fail("generic fallback"))
    if failure is None:
        parity.verify_current_publication(tmp_path, tmp_path, lambda *args: pytest.fail("financial fallback"))
    else:
        with pytest.raises(AssertionError, match=failure):
            parity.verify_current_publication(
                tmp_path, tmp_path, lambda *args: pytest.fail("financial fallback")
            )
    assert calls == [(tmp_path, tmp_path)]
