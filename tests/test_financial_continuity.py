"""Adversarial synthetic protocol tests; retained-source proof runs separately."""

import copy
import json
import shutil
from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from financial_fixtures import financial_release, git, install_authorization, put
from src.publish import financial_continuity as c
from src.publish import financial_continuity_inputs as i
from src.publish import financial_scope as f


def commit(repo):
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "synthetic local protocol")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def local(tmp_path, monkeypatch):
    r = install_authorization(financial_release(tmp_path))
    repo = r["repo"]
    put(repo / f.ANCHOR, f.encoded(r["spec"]))
    # Fixture proof is updated only in this disposable synthetic repository.
    r["proof"]["anchor_sha256"] = f.sha((repo / f.ANCHOR).read_bytes())
    put(r["site"] / f.PROOF, f.encoded(r["proof"]))
    shutil.rmtree(repo / "site")
    shutil.copytree(r["site"], repo / "site")
    published = commit(repo)
    r["site"] = repo / "site"
    snapshot = {"analysis_runs/lifecycle/head.json": "a" * 64}
    binding = {
        "published_commit": published,
        "production_commit": published,
        "runtime_sha256": "e" * 64,
        "original_anchor_sha256": f.sha((repo / f.ANCHOR).read_bytes()),
        "original_authorization_sha256": r["spec"]["authorization_sha256"],
        "original_review_sha256": r["authorization"]["independent_review_sha256"],
        "site_closure_sha256": i.fingerprint(i.site_files(r["site"])),
        "source_closure_sha256": i.fingerprint(snapshot),
    }
    report = {
        "schema_version": "financial_continuity_review_v1",
        "scope": i.SCOPE,
        "binding": binding,
        "status": "passed",
        "unresolved_findings": [],
        "reviewer_reference": "Synthetic test report, not real source review",
        "assertions": {k: True for k in i.ASSERTIONS},
    }
    policy = {
        "schema_version": "financial_continuity_local_v1",
        "scope": i.SCOPE,
        "binding": binding,
        "review_sha256": "",
        "procedure_consent": {
            "source_reference": "Synthetic fixture",
            "instruction": "Synthetic local-only consent",
            "at": "2026-10-26",
            "local_only": True,
        },
    }
    r.update(policy=policy, report=report, snapshot=snapshot)
    write_policy(r)
    monkeypatch.setattr(c, "PATHS", SimpleNamespace(root=repo))
    monkeypatch.setattr(c, "code_version", lambda: "e" * 64)
    monkeypatch.setattr(i, "runtime_at_commit", lambda *args: "e" * 64)
    monkeypatch.setattr(i, "sources", lambda *args: copy.deepcopy(r["snapshot"]))
    monkeypatch.setattr(c.flow, "writer", lambda *args: nullcontext())
    monkeypatch.setattr(c, "preserved_files", lambda *args: frozenset({"retained"}))
    monkeypatch.setattr(c, "approved_projection", lambda *args: r["projection"])
    import src.publish.verify as verify

    monkeypatch.setattr(verify, "_verify_site", lambda *args, **kwargs: [])
    return r


def write_policy(r, *, do_commit=True):
    raw = f.encoded(r["report"])
    key = f.sha(raw)
    put(r["repo"] / "analysis_runs/financial_continuity/reviews" / (key + ".json"), raw)
    r["policy"]["review_sha256"] = key
    put(r["repo"] / i.POLICY, f.encoded(r["policy"]))
    if do_commit:
        commit(r["repo"])


def refused(r):
    result = c.verify_local(r["site"], r["repo"])
    assert len(result) == 1 and result[0].startswith("Invalid local financial continuity:")
    return result[0]


def test_explicit_local_protocol_preserves_original_authority_and_has_no_writes(local):
    r = local
    before = {p: p.read_bytes() for p in r["repo"].rglob("*") if p.is_file() and ".git" not in p.parts}
    assert c.verify_local(r["site"], r["repo"]) == []
    assert all(p.read_bytes() == raw for p, raw in before.items())


@pytest.mark.parametrize(
    "kind",
    ["absent", "uncommitted", "symlink", "bad_schema", "extra", "public_scope", "consent", "consent_scope"],
)
def test_invalid_policy_refuses(local, kind):
    r = local
    path = r["repo"] / i.POLICY
    if kind == "absent":
        path.unlink()
    elif kind == "uncommitted":
        path.write_bytes(path.read_bytes() + b" ")
    elif kind == "symlink":
        other = r["repo"] / "policy-copy.json"
        other.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(other)
    else:
        if kind == "bad_schema":
            r["policy"]["schema_version"] = "unknown"
        if kind == "extra":
            r["policy"]["publish"] = True
        if kind == "public_scope":
            r["policy"]["scope"] = f.SCOPE
        if kind == "consent":
            r["policy"]["procedure_consent"]["source_reference"] = ""
        if kind == "consent_scope":
            r["policy"]["procedure_consent"]["local_only"] = False
        write_policy(r)
    refused(r)


@pytest.mark.parametrize(
    "kind",
    [
        "absent",
        "tamper",
        "symlink",
        "self_rehash_wrong_binding",
        "unresolved",
        "revoked",
        "assertion",
        "missing_assertion",
        "reviewer",
        "scope",
    ],
)
def test_review_integrity_identity_scope_and_findings(local, kind):
    r = local
    path = r["repo"] / "analysis_runs/financial_continuity/reviews" / (r["policy"]["review_sha256"] + ".json")
    if kind == "absent":
        path.unlink()
    elif kind == "tamper":
        path.write_bytes(path.read_bytes() + b" ")
    elif kind == "symlink":
        other = r["repo"] / "review-copy.json"
        other.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(other)
    else:
        r["report"] = copy.deepcopy(r["report"])
        if kind == "self_rehash_wrong_binding":
            r["report"]["binding"]["runtime_sha256"] = "f" * 64
        if kind == "unresolved":
            r["report"]["unresolved_findings"] = ["real finding"]
        if kind == "revoked":
            r["report"]["status"] = "revoked"
        if kind == "assertion":
            r["report"]["assertions"]["code_review_passed"] = 1
        if kind == "missing_assertion":
            r["report"]["assertions"].pop("original_sources_replayed")
        if kind == "reviewer":
            r["report"]["reviewer_reference"] = ""
        if kind == "scope":
            r["report"]["scope"] = f.SCOPE
        write_policy(r)
    refused(r)


@pytest.mark.parametrize("field", sorted(i.BINDING))
def test_even_committed_self_rehashed_binding_must_match_actual_inputs(local, field):
    r = local
    r["policy"]["binding"][field] = "f" * (40 if field.endswith("commit") else 64)
    write_policy(r)
    refused(r)


@pytest.mark.parametrize(
    "mutation", ["changed", "extra", "missing", "symlink", "directory_symlink", "self_rehashed_manifest"]
)
def test_entire_site_including_manifest_and_extra_files_is_frozen(local, mutation):
    r = local
    site = r["site"]
    if mutation == "changed":
        put(site / "index.html", b"new")
    if mutation == "extra":
        put(site / "extra.txt", b"new")
    if mutation == "missing":
        (site / "assets/old.js").unlink()
    if mutation == "symlink":
        (site / "index.html").unlink()
        (site / "index.html").symlink_to(site / "assets/old.js")
    if mutation == "directory_symlink":
        (site / "assets/alias").symlink_to(site / "data", target_is_directory=True)
    if mutation == "self_rehashed_manifest":
        doc = json.loads((site / "publication_manifest.json").read_bytes())
        doc["analysis_manifest"] = []
        put(site / "publication_manifest.json", f.encoded(doc))
    refused(r)


def test_working_and_committed_runtime_both_required(local, monkeypatch):
    monkeypatch.setattr(c, "code_version", lambda: "f" * 64)
    assert "runtime" in refused(local)
    monkeypatch.setattr(c, "code_version", lambda: "e" * 64)
    monkeypatch.setattr(i, "runtime_at_commit", lambda *args: "f" * 64)
    assert "runtime" in refused(local)


@pytest.mark.parametrize("change", ["source", "site", "authority", "policy", "runtime", "head"])
def test_mutations_during_slow_replay_are_rejected(local, monkeypatch, change):
    r = local

    def replay(*args):
        if change == "source":
            r["snapshot"]["analysis_runs/lifecycle/head.json"] = "b" * 64
        if change == "site":
            put(r["site"] / "index.html", b"during replay")
        if change == "authority":
            r["authorization_path"].write_bytes(b"revoked")
        if change == "policy":
            put(r["repo"] / i.POLICY, b"{}")
        if change == "runtime":
            monkeypatch.setattr(c, "code_version", lambda: "f" * 64)
        if change == "head":
            git(r["repo"], "commit", "--allow-empty", "-qm", "during replay")
        return r["projection"]

    monkeypatch.setattr(c, "approved_projection", replay)
    refused(r)


def test_source_replay_and_existing_schema_failures_cannot_be_ignored(local, monkeypatch):
    def reject(*args):
        raise ValueError("original approval revoked")

    monkeypatch.setattr(c, "approved_projection", reject)
    assert "revoked" in refused(local)
    monkeypatch.setattr(c, "approved_projection", lambda *args: {"wrong": "projection"})
    assert "projection" in refused(local)
    monkeypatch.setattr(c, "approved_projection", lambda *args: local["projection"])
    import src.publish.verify as verify

    monkeypatch.setattr(verify, "_verify_site", lambda *args, **kwargs: ["schema error"])
    assert "existing publication checks" in refused(local)


def test_default_publication_verifier_keeps_original_runtime_rule(local, monkeypatch):
    from src.analysis_agent import entity_adapter

    monkeypatch.setattr(entity_adapter, "code_version", lambda: "e" * 64)
    assert c.verify_local(local["site"], local["repo"]) == []
    assert f.verify_financial(local["site"], local["repo"]) == [
        "Invalid financial preservation proof: Financial runtime differs from reviewed producer"
    ]


def test_regular_rejects_parent_symlink_and_escape(tmp_path):
    outer = tmp_path / "outside"
    outer.mkdir()
    put(outer / "file", b"private")
    root = tmp_path / "root"
    root.mkdir()
    (root / "alias").symlink_to(outer, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        i.regular(root / "alias/file", root)
    with pytest.raises(ValueError, match="escapes"):
        i.regular(outer / "file", root)


@pytest.mark.parametrize("raw", [b"[]", b'{"scope":1,"scope":2}', b'{"binding":{"head":1,"head":2}}'])
def test_ambiguous_documents_are_rejected(raw):
    with pytest.raises(ValueError):
        i.document(raw)


@pytest.mark.parametrize(
    "mutation",
    [
        "valid",
        "absolute",
        "traversal",
        "backslash",
        "source_symlink",
        "parent_symlink",
        "sidecar_symlink",
        "ledger_symlink",
        "snapshot_escape",
    ],
)
def test_source_input_paths_and_snapshot_scope(tmp_path, monkeypatch, mutation):
    repo = tmp_path / "source-repo"
    repo.mkdir()
    source = repo / "data/bronze/issuer/source.pdf"
    put(source, b"original")
    package = repo / "analysis_runs/evidence/package.json"
    record = repo / "analysis_runs/drafts/record.json"
    put(record, b"{}")
    name = "issuer/source.pdf"
    outside = tmp_path / "outside"
    put(outside, b"private")
    if mutation == "absolute":
        name = str(outside)
    if mutation == "traversal":
        name = "../outside"
    if mutation == "backslash":
        name = "issuer\\source.pdf"
    if mutation == "source_symlink":
        source.unlink()
        source.symlink_to(outside)
    if mutation == "parent_symlink":
        alias = repo / "data/bronze/alias"
        alias.symlink_to(source.parent, target_is_directory=True)
        name = "alias/source.pdf"
    if mutation == "sidecar_symlink":
        source.with_name(source.name + ".meta.json").symlink_to(outside)
    if mutation == "ledger_symlink":
        (repo / "analysis_runs/evil").symlink_to(outside)
    put(package, f.encoded({"sources": [{"source_file": name}]}))
    import src.publish.financial_sources as fs

    path = outside if mutation == "snapshot_escape" else source
    monkeypatch.setattr(fs, "source_snapshot", lambda *args: {str(path.resolve()): f.sha(b"original")})
    if mutation == "valid":
        assert i.sources(repo, record, {"package_id": "package"}, repo / "analysis_runs/lifecycle") == {
            "data/bronze/issuer/source.pdf": f.sha(b"original")
        }
    else:
        with pytest.raises(ValueError):
            i.sources(repo, record, {"package_id": "package"}, repo / "analysis_runs/lifecycle")


def test_financial_publish_entry_point_cannot_consume_local_continuity(local, monkeypatch):
    from src.publish import financial_update as update
    from src.publish import manifest

    monkeypatch.setattr(update, "PATHS", SimpleNamespace(root=local["repo"]))
    monkeypatch.setattr(update, "code_version", lambda: "e" * 64)
    monkeypatch.setattr(manifest, "refuse_if_build_inputs_dirty", lambda: None)
    assert c.verify_local(local["site"], local["repo"]) == []
    with pytest.raises(ValueError, match="Financial build code differs from independent review"):
        update.publish_financial([], local["repo"] / "never-created")
    assert not (local["repo"] / "never-created").exists()
