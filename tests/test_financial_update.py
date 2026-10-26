"""Orchestration races cannot reach an atomic swap; source and scope have separate real tests."""

import copy
import shutil
from types import SimpleNamespace
import pytest
from financial_fixtures import financial_release, git, put, resign
from src.publish import gate
from src.publish import financial_update as m


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "revoked",
        "source",
        "review",
        "head",
        "anchor",
        "baseline",
        "remote",
        "deployment",
        "frontend",
        "slow_candidate",
        "slow_candidate_data",
    ],
)
def test_financial_publisher_rechecks_after_build_and_after_slow_validation(tmp_path, monkeypatch, failure):
    r = financial_release(tmp_path)
    repo = r["repo"]
    spec = r["spec"]
    out = repo / "site"
    git(repo, "update-ref", "refs/remotes/origin/master", spec["baseline_commit"])
    dist = tmp_path / "dist"
    shutil.copytree(r["site"], dist)
    (dist / "publication_manifest.json").unlink()
    (dist / m.PROOF).unlink()
    record = repo / "synthetic-record.json"
    put(record, b"{}")
    monkeypatch.setattr(m, "PATHS", SimpleNamespace(root=repo))
    monkeypatch.setattr(m, "code_version", lambda: spec["producer_code_version"])
    monkeypatch.setattr(m.manifests, "refuse_if_build_inputs_dirty", lambda: None)
    monkeypatch.setattr(gate, "_trusted_site_commit", lambda root: spec["baseline_commit"])
    require = gate.require_trusted_site_baseline
    monkeypatch.setattr(
        gate,
        "require_trusted_site_baseline",
        lambda path, **kw: require(path, root=repo, trusted_commit=kw["trusted_commit"]),
    )
    monkeypatch.setattr(gate, "WEB_DATA_V1", repo / "web/public/data/v1")
    ledger = tmp_path / "ledger"
    monkeypatch.setattr(gate.flow, "ROOT", ledger)
    flags = {"built": False, "slow": False}
    calls = {"source": 0, "witness": 0, "swap": 0, "receipt": 0}
    original_git = m.transport._git

    def git_transport(root, *args):
        if args[0] == "ls-remote":
            value = "f" * 40 if flags["built"] and failure == "remote" else spec["baseline_commit"]
            return (value + "\trefs/heads/master\n").encode()
        return original_git(root, *args)

    monkeypatch.setattr(m.transport, "_git", git_transport)

    def witness(root, value):
        calls["witness"] += 1
        result = copy.deepcopy(r["witness"])
        if failure == "deployment" and calls["witness"] == 2:
            result["deployment_commit"] = "f" * 40
        return result

    monkeypatch.setattr(m.transport, "witness_remote", witness)

    def approved(*args):
        calls["source"] += 1
        if failure == "revoked" and flags["built"]:
            raise ValueError("source approval revoked")
        return r["projection"]

    monkeypatch.setattr(m, "approved_projection", approved)

    def authorization(*args):
        if failure == "review" and flags["built"]:
            raise ValueError("independent review changed")
        return {}

    monkeypatch.setattr(m, "authorization", authorization)
    monkeypatch.setattr(
        m,
        "source_snapshot",
        lambda *a: {
            "source": "changed" if (failure == "source" and flags["built"]) or flags["slow"] else "initial"
        },
    )

    def build():
        flags["built"] = True
        if failure == "head":
            git(repo, "commit", "--allow-empty", "-qm", "concurrent HEAD")
        if failure == "anchor":
            put(repo / m.ANCHOR, (repo / m.ANCHOR).read_bytes() + b" ")
        if failure == "baseline":
            put(out / "publication_manifest.json", (out / "publication_manifest.json").read_bytes() + b" ")
        if failure == "frontend":
            put(dist / "index.html", b"unreviewed build")
        return dist

    monkeypatch.setattr(gate, "build_web", build)

    def verify(candidate):
        if failure == "slow_candidate":
            flags["slow"] = True
        if failure == "slow_candidate_data":
            put(candidate / m.EXECUTIVE, b"{}")
            resign(candidate)
        return []

    monkeypatch.setattr(m, "verify_financial", verify)

    def assemble(candidate, entries, target, **kwargs):
        assert entries == r["old"]["analysis_manifest"]
        assert kwargs["contracts"] == r["old"]["contracts"]
        put(candidate / "publication_manifest.json", m.encoded(r["old"]))
        resign(candidate)
        kwargs["validate_candidate"](candidate)
        calls["swap"] += 1
        return {"local-generation-only": True}

    monkeypatch.setattr(gate, "assemble_site", assemble)

    def receipt(*args):
        calls["receipt"] += 1
        return {"local-generation-only": True}

    monkeypatch.setattr(gate, "write_receipt", receipt)
    if failure:
        with pytest.raises((ValueError, gate.PublicationRefused)):
            m.publish_financial([record], out)
        assert calls["swap"] == 0 and calls["receipt"] == 0
    else:
        assert m.publish_financial([record], out)["receipt"] == {"local-generation-only": True}
        assert calls["source"] == 2 and calls["witness"] == 2 and calls["swap"] == 1 and calls["receipt"] == 1
    assert (out / "index.html").read_bytes() == b"old frontend"
