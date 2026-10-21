from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.publish.gate import PublicationRefused, _trusted_site_commit, require_trusted_site_baseline
from src.publish.manifest import build_manifest


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def test_ui_only_baseline_requires_exact_trusted_site_tree(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    site = root / "site"
    (site / "data" / "v1").mkdir(parents=True)
    (site / "data" / "v1" / "flights.json").write_text('{"rows":[]}', encoding="utf-8")
    (site / "publication_manifest.json").write_text('{"files":[]}', encoding="utf-8")
    _git(root, "init", "-b", "master")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", "site")
    _git(root, "commit", "-m", "approved published site")
    _git(root, "update-ref", "refs/remotes/origin/master", "HEAD")

    require_trusted_site_baseline(site, root=root)

    # Rebuilding a self-consistent manifest cannot bless modified public data:
    # the entire tracked site must still equal the trusted base.
    (site / "data" / "v1" / "flights.json").write_text('{"rows":[1]}', encoding="utf-8")
    (site / "publication_manifest.json").write_text('{"files":["rebuilt"]}', encoding="utf-8")
    with pytest.raises(PublicationRefused, match="uncommitted or untracked"):
        require_trusted_site_baseline(site, root=root)


def test_ui_only_baseline_refuses_a_site_committed_after_trusted_base(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    site = root / "site"
    site.mkdir(parents=True)
    (site / "index.html").write_text("approved", encoding="utf-8")
    _git(root, "init", "-b", "master")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", "site")
    _git(root, "commit", "-m", "trusted published site")
    _git(root, "update-ref", "refs/remotes/origin/master", "HEAD")
    trusted_commit = _trusted_site_commit(root)
    (site / "index.html").write_text("untrusted but committed", encoding="utf-8")
    _git(root, "add", "site")
    _git(root, "commit", "-m", "untrusted replacement")

    with pytest.raises(PublicationRefused, match="differs from the trusted"):
        require_trusted_site_baseline(site, root=root, trusted_commit=trusted_commit)

    _git(root, "update-ref", "refs/remotes/origin/master", "HEAD")
    with pytest.raises(PublicationRefused, match="changed during publication"):
        require_trusted_site_baseline(site, root=root, trusted_commit=trusted_commit)


def test_manifest_can_preserve_trusted_contract_set_for_ui_only_release(tmp_path: Path) -> None:
    trusted_contracts = {"publication_manifest.schema.json": "a" * 64}
    manifest = build_manifest(tmp_path, [], contracts=trusted_contracts, code_commit="commit")
    assert manifest["contracts"] == trusted_contracts


@pytest.mark.parametrize(
    "change",
    [
        None,
        "initial_revocation",
        "revocation",
        "approval",
        "payload",
        "pin",
        "build_data",
        "baseline",
        "late_data",
        "candidate_invalid",
    ],
)
def test_ui_only_replays_cohorts_and_refuses_changes_before_swap(tmp_path, monkeypatch, change):
    """Exercise the real UI controller and atomic assembly; isolate cohort internals.

    The cohort verifier's full source/ledger replay has separate adversarial
    coverage. Here a later runtime must never be asked to renew old approvals,
    and every change during the unlocked build must leave the old site intact.
    """
    import copy
    import json
    import shutil
    from contextlib import contextmanager
    from types import SimpleNamespace

    from src.publish import approval_cohorts, gate, manifest as manifests, verify

    site, dist = tmp_path / "site", tmp_path / "dist"
    web_data = tmp_path / "scratch/data/v1"
    ledger = tmp_path / "ledger"
    authorized, paths, payloads = [], [], []
    identities = [(None, "2026Q2"), (None, "2026Q3")]
    identities += [(entity, "2026Q2") for entity in ("INDUSTRY", "VIVA_AEROBUS", "VOLARIS")]
    for i, (entity, period) in enumerate(identities):
        auth = {key: str(i + 1) * 64 for key in gate.ANALYSIS_MANIFEST_FIELDS}
        auth["period_id"] = period
        draft = {"period_id": period}
        if entity:
            auth["entity_key"] = draft["entity_key"] = entity
        authorized.append(auth)
        path = tmp_path / f"record-{i}.json"
        path.write_text(json.dumps({"draft": draft, "version": auth["version"]}))
        paths.append(path)
        payload = {"thesis": f"retained-{i}"}
        payloads.append(payload)
        target = site / "data/v1" / manifests.analysis_relative_path(auth)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(payload))
    (site / "data/v1/executive.json").write_text('{"retained":true}')
    (site / "index.html").write_text("before")
    authorized.sort(key=manifests.analysis_sort_key)
    baseline = {"analysis_manifest": authorized, "contracts": {}, "files": manifests.file_entries(site)}
    (site / "publication_manifest.json").write_text(json.dumps(baseline))
    before = {p.relative_to(site): p.read_bytes() for p in site.rglob("*") if p.is_file()}
    verified = {
        "authorized": authorized,
        "payloads": payloads,
        "cohorts": [{"implementation_commit": "old"}, {"implementation_commit": "quarter"}],
    }
    state = dict(locked=False, replay=0, built=False, baseline=0, receipt=0)

    @contextmanager
    def writer(selected):
        assert selected == ledger and not state["locked"]
        state["locked"] = True
        try:
            yield
        finally:
            state["locked"] = False

    def trusted(directory, **kwargs):
        assert directory == site and kwargs == {"root": tmp_path, "trusted_commit": "trusted"}
        state["baseline"] += 1
        if change == "baseline" and state["built"]:
            raise gate.PublicationRefused("trusted baseline changed during build")

    def replay(selected, repo, commit, manifest, root):
        assert selected == paths and repo == tmp_path and commit == "trusted"
        assert manifest == baseline and root == ledger and state["locked"]
        state["replay"] += 1
        if change == "initial_revocation" or (change == "revocation" and state["replay"] == 2):
            raise ValueError("pinned approval revoked")
        answer = copy.deepcopy(verified)
        if state["replay"] == 2:
            if change == "approval":
                answer["authorized"][0]["approval_event"] = "changed"
            elif change == "payload":
                answer["payloads"][0]["thesis"] = "changed"
            elif change == "pin":
                answer["cohorts"][0]["implementation_commit"] = "changed"
            elif change == "late_data":
                (dist / "data/v1/executive.json").write_text('{"tampered":true}')
        return answer

    def build(directory):
        assert not state["locked"]
        shutil.copytree(web_data, dist / "data/v1")
        (dist / "index.html").write_text("after")
        if change == "build_data":
            (dist / "data/v1/executive.json").write_text('{"tampered":true}')
        state["built"] = True
        return dist

    def check_candidate(directory):
        if directory != site:
            assert state["locked"]
            if change == "candidate_invalid":
                return ["invalid candidate contract"]
        return []

    def receipt(*args, **kwargs):
        assert not state["locked"]
        state["receipt"] += 1
        return {"verified": True}

    def current_runtime_forbidden(*args, **kwargs):
        pytest.fail("historical approvals must replay through their pinned cohorts")

    monkeypatch.setattr(gate, "PATHS", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(gate.manifest_mod, "refuse_if_build_inputs_dirty", lambda: None)
    monkeypatch.setattr(gate, "_trusted_site_commit", lambda _: "trusted")
    monkeypatch.setattr(gate, "require_trusted_site_baseline", trusted)
    monkeypatch.setattr(gate.flow, "writer", writer)
    monkeypatch.setattr(approval_cohorts, "verify_approval_cohorts", replay)
    monkeypatch.setattr(gate, "verify_records", current_runtime_forbidden)
    monkeypatch.setattr(gate, "_verify_under_lock", current_runtime_forbidden)
    monkeypatch.setattr(gate, "build_web", build)
    monkeypatch.setattr(verify, "verify_site", check_candidate)
    monkeypatch.setattr(gate, "write_receipt", receipt)
    if change:
        with pytest.raises(gate.PublicationRefused):
            gate.publish_ui_only(paths, site, root=ledger, web_dir=tmp_path / "web", web_data_v1=web_data)
        assert {p.relative_to(site): p.read_bytes() for p in site.rglob("*") if p.is_file()} == before
        assert state["receipt"] == 0
    else:
        result = gate.publish_ui_only(
            paths, site, root=ledger, web_dir=tmp_path / "web", web_data_v1=web_data
        )
        assert state["replay"] == state["baseline"] == 2
        assert result["manifest"]["analysis_manifest"] == authorized
        assert state["receipt"] == 1
        assert (site / "index.html").read_text() == "after"
        assert {
            p.relative_to(site): p.read_bytes() for p in (site / "data/v1").rglob("*") if p.is_file()
        } == {k: v for k, v in before.items() if k.as_posix().startswith("data/v1/")}
    assert not state["locked"]
