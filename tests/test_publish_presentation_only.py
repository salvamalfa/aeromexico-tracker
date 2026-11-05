from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.publish import afac_history_scope
from src.publish import manifest as manifests
from src.publish import presentation_release as release


def _site(path: Path) -> dict:
    (path / "assets").mkdir(parents=True, exist_ok=True)
    (path / "data/v1").mkdir(parents=True, exist_ok=True)
    (path / "index.html").write_text("before", encoding="utf-8")
    (path / "access.html").write_text("private access page", encoding="utf-8")
    (path / "review.html").write_text("review page", encoding="utf-8")
    (path / "assets/app-old.js").write_text("old frontend", encoding="utf-8")
    (path / "data/v1/news.json").write_text('{"items":[1]}', encoding="utf-8")
    (path / "data/v1/analysis.json").write_text('{"approved":true}', encoding="utf-8")
    (path / "afac-history-publication.json").write_text('{"afac":"proof"}', encoding="utf-8")
    (path / "quarterly-story-publication.json").write_text('{"quarterly":"proof"}', encoding="utf-8")
    files = manifests.file_entries(path)
    manifest = {"analysis_manifest": [], "contracts": {"news.schema.json": "a" * 64}, "files": files}
    manifests.write_manifest(path, manifest)
    return manifest


def _run_publish(tmp_path, monkeypatch, *, build_change=None, replay_change=None, candidate_change=None):
    site = tmp_path / "site"
    site.mkdir(exist_ok=True)
    baseline = manifests.load_manifest(site) if (site / manifests.MANIFEST_NAME).exists() else _site(site)
    web_dir = tmp_path / "web"
    web_data = web_dir / "public/data/v1"
    ledger = tmp_path / "analysis_runs/lifecycle"
    web_dir.mkdir()
    state = {"replays": 0, "locked": False, "built": False, "assembled": False}

    @contextmanager
    def writer(target):
        assert target == ledger
        assert not state["locked"]
        state["locked"] = True
        try:
            yield
        finally:
            state["locked"] = False

    def replay(*args):
        assert state["locked"]
        state["replays"] += 1
        if replay_change == "revoked":
            raise ValueError("approval revoked")
        generation = 1 if state["replays"] == 1 else (2 if replay_change == "race" else 1)
        return {"afac": {"generation": generation, "authorized": []}}

    def build(_web_dir):
        assert not state["locked"]
        dist = tmp_path / "dist"
        shutil.rmtree(dist, ignore_errors=True)
        shutil.copytree(web_data, dist / "data/v1")
        (dist / "assets").mkdir()
        (dist / "assets/app-new.js").write_text("new frontend", encoding="utf-8")
        (dist / "index.html").write_text("<html><head></head><body>after</body></html>", encoding="utf-8")
        (dist / "access.html").write_text("rebuilt private access page", encoding="utf-8")
        (dist / "review.html").write_text("rebuilt review page", encoding="utf-8")
        if build_change == "data_tamper":
            (dist / "data/v1/news.json").write_text('{"items":[2]}', encoding="utf-8")
        elif build_change == "data_omission":
            (dist / "data/v1/news.json").unlink()
        elif build_change == "extra_receipt":
            (dist / "unknown-publication.json").write_text("{}", encoding="utf-8")
        state["built"] = True
        return dist

    def assemble(dist, analyses, out, *, contracts, validate_candidate):
        assert state["locked"]
        candidate = tmp_path / "candidate"
        shutil.rmtree(candidate, ignore_errors=True)
        shutil.copytree(dist, candidate)
        assert (candidate / "access.html").read_text(encoding="utf-8") == "private access page"
        assert (candidate / "review.html").read_text(encoding="utf-8") == "review page"
        assert (candidate / "assets/app-old.js").read_text(encoding="utf-8") == "old frontend"
        if candidate_change == "omit_evidence":
            (candidate / "afac-history-publication.json").unlink()
        manifest = manifests.build_manifest(
            candidate,
            analyses,
            contracts=contracts,
            code_commit="b" * 40,
            generated_at="2026-11-05T00:00:00+00:00",
        )
        manifests.write_manifest(candidate, manifest)
        validate_candidate(candidate)
        previous = tmp_path / "previous"
        out.rename(previous)
        candidate.rename(out)
        shutil.rmtree(previous)
        state["assembled"] = True
        return manifest

    monkeypatch.setattr(manifests, "refuse_if_build_inputs_dirty", lambda **_: None)
    monkeypatch.setattr(manifests, "load_manifest", lambda _site: baseline)
    monkeypatch.setattr(manifests, "file_entries", manifests.file_entries)
    monkeypatch.setattr(release, "load_records", lambda _paths: [{"record": 1}])
    monkeypatch.setattr(release, "_replay_release", replay)
    monkeypatch.setattr(
        release,
        "presentation_receipt",
        lambda *_: {
            "schema_version": release.PRESENTATION_RECEIPT_SCHEMA,
            "baseline_commit": "a" * 40,
            "baseline_manifest_sha256": "b" * 64,
            "source_producer_commit": "c" * 40,
            "source_producer_code_version": "d" * 64,
            "frontend_commit": "e" * 40,
        },
    )
    monkeypatch.setattr(release, "verify_presentation_only_site", lambda *_: None)
    monkeypatch.setattr(release, "flow", SimpleNamespace(writer=writer))

    def require_baseline(path, *, root, trusted_commit):
        assert path == site
        assert root == tmp_path
        assert trusted_commit == "trusted"

    result = release.publish_presentation_only(
        [tmp_path / "record.json"],
        site,
        repo=tmp_path,
        ledger_root=ledger,
        web_dir=web_dir,
        web_data_v1=web_data,
        build_web=build,
        require_trusted_baseline=require_baseline,
        trusted_site_commit=lambda _repo: "trusted",
        assemble_site=assemble,
        write_receipt=lambda *_args, **_kwargs: {"written": True},
    )
    return site, baseline, result, state


def test_only_frontend_paths_are_allowed_to_differ() -> None:
    before = {
        "index.html": ("1", 1),
        "assets/app.js": ("2", 1),
        "data/v1/news.json": ("3", 1),
        "afac-history-publication.json": ("4", 1),
        "contracts/news.schema.json": ("5", 1),
    }
    changed = {**before, "index.html": ("x", 1), "assets/new.js": ("y", 1)}
    assert release._preserved_map(before) == release._preserved_map(changed)
    changed["data/v1/news.json"] = ("tampered", 1)
    assert release._preserved_map(before) != release._preserved_map(changed)


def test_dashboard_index_carries_one_canonical_release_marker(tmp_path) -> None:
    receipt = {
        "schema_version": release.PRESENTATION_RECEIPT_SCHEMA,
        "baseline_commit": "a" * 40,
        "baseline_manifest_sha256": "b" * 64,
        "source_producer_commit": "c" * 40,
        "source_producer_code_version": "d" * 64,
        "frontend_commit": "e" * 40,
    }
    path = tmp_path / "index.html"
    path.write_bytes(release.embed_presentation_receipt(b"<html><head></head></html>", receipt))
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_bytes(path.read_bytes())
    assert release.read_presentation_receipt(site) == receipt
    (site / "index.html").write_bytes(path.read_bytes() + path.read_bytes())
    with pytest.raises(ValueError, match="multiple"):
        release.read_presentation_receipt(site)


def test_presentation_release_keeps_every_nonfrontend_file(tmp_path, monkeypatch) -> None:
    site, baseline, result, state = _run_publish(tmp_path, monkeypatch)
    after = {row["path"]: (row["sha256"], row["bytes"]) for row in manifests.file_entries(site)}
    before = {row["path"]: (row["sha256"], row["bytes"]) for row in baseline["files"]}
    assert release._preserved_map(before) == release._preserved_map(after)
    assert "assets/app-old.js" in after
    assert "assets/app-new.js" in after
    assert result["receipt"] == {"written": True}
    assert state["replays"] == 2 and state["assembled"]


@pytest.mark.parametrize("change", ["data_tamper", "data_omission", "extra_receipt"])
def test_build_tampering_or_omission_refuses_before_swap(tmp_path, monkeypatch, change) -> None:
    original = tmp_path / "site"
    original.mkdir()
    _site(original)
    before = {p.relative_to(original): p.read_bytes() for p in original.rglob("*") if p.is_file()}
    with pytest.raises(release.PublicationRefused):
        _run_publish(tmp_path, monkeypatch, build_change=change)
    assert {p.relative_to(original): p.read_bytes() for p in original.rglob("*") if p.is_file()} == before


def test_candidate_evidence_omission_refuses_before_swap(tmp_path, monkeypatch) -> None:
    site = tmp_path / "site"
    site.mkdir()
    _site(site)
    before = {p.relative_to(site): p.read_bytes() for p in site.rglob("*") if p.is_file()}
    with pytest.raises(release.PublicationRefused):
        _run_publish(tmp_path, monkeypatch, candidate_change="omit_evidence")
    assert {p.relative_to(site): p.read_bytes() for p in site.rglob("*") if p.is_file()} == before


@pytest.mark.parametrize("change", ["revoked", "race"])
def test_revocation_or_approval_change_during_build_refuses(tmp_path, monkeypatch, change) -> None:
    site = tmp_path / "site"
    site.mkdir()
    _site(site)
    before = {p.relative_to(site): p.read_bytes() for p in site.rglob("*") if p.is_file()}
    with pytest.raises(release.PublicationRefused):
        _run_publish(tmp_path, monkeypatch, replay_change=change)
    assert {p.relative_to(site): p.read_bytes() for p in site.rglob("*") if p.is_file()} == before


def test_strong_verifier_unknown_receipt_fails_closed(tmp_path, monkeypatch) -> None:
    site = tmp_path / "site"
    site.mkdir()
    _site(site)
    monkeypatch.setattr("scripts.check_pages_publication.verifier_for", lambda *_: "src.publish.verify")
    monkeypatch.setattr("scripts.check_pages_publication.verify_site", lambda *_: [])
    monkeypatch.setattr("src.publish.verify.verify_site", lambda *_: [])
    with pytest.raises(ValueError, match="pinned AFAC verifier"):
        release.verify_presentation_only_site(site, tmp_path)


def test_afac_authority_mismatch_refuses_even_when_sources_replay() -> None:
    anchor = {
        "scope": {"scope": 1},
        "members": [],
        "contracts": {},
        "authorization_sha256": "a" * 64,
        "source_audit_sha256": "b" * 64,
    }
    replay = {
        "scope": anchor["scope"],
        "members": [],
        "contracts": {},
        "authority": ["c" * 64, "b" * 64],
    }
    with pytest.raises(ValueError, match="authority or independent audit"):
        release.require_afac_replay_matches_anchor(replay, anchor)


def test_current_quarterly_manifest_must_match_replayed_afac_parent(tmp_path, monkeypatch) -> None:
    request = tmp_path / "tmp/source-updates/afac-history-correction-20261104/request.json"
    request.parent.mkdir(parents=True)
    request.write_bytes(b"request")
    entry = {
        "period_id": "2026Q3",
        "version": "v" * 64,
        "content_hash": "c" * 64,
        "evidence_fingerprint": "e" * 64,
        "approval_event": "a" * 64,
        "audit_hash": "b" * 64,
        "entity_key": "AEROMEXICO",
    }
    record = {
        "version": entry["version"],
        "content_hash": entry["content_hash"],
        "draft": {
            "period_id": entry["period_id"],
            "entity_key": entry["entity_key"],
            "evidence_fingerprint": entry["evidence_fingerprint"],
        },
    }
    profile = {
        "afac_request": {
            "path": "tmp/source-updates/afac-history-correction-20261104/request.json",
            "sha256": release._sha(b"request"),
        }
    }
    monkeypatch.setattr(release, "load_profile", lambda *_: profile)
    monkeypatch.setattr(afac_history_scope, "anchor", lambda *_: {"scope": {}})
    monkeypatch.setattr(release, "replay_afac_sources", lambda *_: {"authorized": [entry]})
    monkeypatch.setattr(release, "load_records", lambda *_: [record])
    result = release._replay_release([], tmp_path, "trusted", {"analysis_manifest": [entry]}, tmp_path)
    assert result["afac"]["authorized"] == [entry]

    with pytest.raises(ValueError, match="current quarterly approval chain"):
        release._replay_release(
            [], tmp_path, "trusted", {"analysis_manifest": [entry | {"approval_event": "f" * 64}]}, tmp_path
        )
