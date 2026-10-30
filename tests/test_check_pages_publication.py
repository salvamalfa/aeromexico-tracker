"""Declared receipt routing never downgrades and executes the pinned checkout."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_pages_publication import VERIFIERS, verifier_for

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/check_pages_publication.py"


def manifest(site, receipts):
    site.mkdir(exist_ok=True)
    repo = site.parent if site.name == "site" else site
    if not (repo / ".git").exists():
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        for key, value in (("user.name", "Selector Fixture"), ("user.email", "fixture@example.invalid")):
            subprocess.run(["git", "config", key, value], cwd=repo, check=True)
    commits = []
    for index, _ in enumerate(receipts):
        subprocess.run(["git", "commit", "--allow-empty", "-qm", f"release{index}"], cwd=repo, check=True)
        commits.append(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip())
    # Receipt list is oldest to newest, unlike the former static priority order.
    entries = []
    for name, commit in zip(receipts, commits, strict=True):
        raw = json.dumps({"remote_witness": {"baseline_commit": commit}}).encode()
        (site / name).write_bytes(raw)
        entries.append({"path": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
    (site / "publication_manifest.json").write_text(json.dumps({"files": entries}), encoding="utf-8")
    return repo


@pytest.mark.parametrize(
    "receipts, expected",
    [
        ([], "src.publish.verify"),
        (["editorial-publication.json"], "src.publish.editorial"),
        (["editorial-publication.json", "financial-publication.json"], "src.publish.financial_scope"),
        (["issuer-publication.json"], "src.publish.issuer_scope"),
        ([name for name, _ in reversed(VERIFIERS)], "src.publish.movements_scope"),
    ],
)
def test_declared_receipt_priority(tmp_path, receipts, expected):
    repo = manifest(tmp_path, receipts)
    assert verifier_for(tmp_path, repo) == expected


@pytest.mark.parametrize("receipt, module", VERIFIERS)
def test_missing_declared_receipt_fails_before_any_verifier(tmp_path, receipt, module):
    repo = manifest(tmp_path, [receipt])
    (tmp_path / receipt).unlink()
    with pytest.raises(ValueError, match="declared publication receipt is missing"):
        verifier_for(tmp_path, repo)


@pytest.mark.parametrize("receipt, module", [*VERIFIERS, (None, "src.publish.verify")])
@pytest.mark.parametrize("exit_code", [0, 17])
def test_real_subprocess_uses_cwd_code_and_preserves_failure(tmp_path, receipt, module, exit_code):
    # Master supplies the helper; a separate pinned checkout supplies modules.
    preview = tmp_path / "_preview"
    package = preview / "src/publish"
    package.mkdir(parents=True)
    (preview / "src/__init__.py").touch()
    (package / "__init__.py").touch()
    for _, name in [*VERIFIERS, (None, "src.publish.verify")]:
        filename = package / (name.rsplit(".", 1)[1] + ".py")
        filename.write_text(
            "from pathlib import Path\n"
            f"Path('executed.txt').open('a').write({name!r} + '\\n')\n"
            f"raise SystemExit({exit_code if name == module else 91})\n",
            encoding="utf-8",
        )
    manifest(preview / "site", [receipt] if receipt else [])
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run([sys.executable, str(HELPER), "site/"], cwd=preview, env=env)
    assert result.returncode == exit_code
    assert (preview / "executed.txt").read_text().splitlines() == [module]


def test_workflow_uses_master_helper_with_preview_cwd():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/pages.yml").read_text())
    production = next(
        s for s in workflow["jobs"]["verify"]["steps"] if "check_pages_publication" in s.get("run", "")
    )
    preview = next(
        s for s in workflow["jobs"]["preview"]["steps"] if "check_pages_publication" in s.get("run", "")
    )
    assert "python scripts/check_pages_publication.py site/" in production["run"]
    assert preview["working-directory"] == "_preview"
    assert "python ../scripts/check_pages_publication.py site/" in preview["run"]


def replace_proof(site, receipt, commit):
    raw = json.dumps({"remote_witness": {"baseline_commit": commit}}).encode()
    (site / receipt).write_bytes(raw)
    document = json.loads((site / "publication_manifest.json").read_bytes())
    for pin in document["files"]:
        if pin["path"] == receipt:
            pin.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    (site / "publication_manifest.json").write_text(json.dumps(document))


def new_commit(repo, message):
    subprocess.run(["git", "commit", "--allow-empty", "-qm", message], cwd=repo, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()


def test_movements_then_issuer_then_movements_follow_witnessed_git_order(tmp_path):
    receipts = [
        "editorial-publication.json",
        "financial-publication.json",
        "issuer-publication.json",
        "aerocivil-movements-publication.json",
    ]
    repo = manifest(tmp_path, receipts)
    assert verifier_for(tmp_path, repo) == "src.publish.movements_scope"
    replace_proof(tmp_path, "issuer-publication.json", new_commit(repo, "later issuer"))
    assert verifier_for(tmp_path, repo) == "src.publish.issuer_scope"
    replace_proof(tmp_path, "aerocivil-movements-publication.json", new_commit(repo, "later movements"))
    assert verifier_for(tmp_path, repo) == "src.publish.movements_scope"


@pytest.mark.parametrize(
    "mutation",
    [
        "modified",
        "size",
        "invalid_commit",
        "missing_commit",
        "blob",
        "tie",
        "fork",
        "duplicate",
        "unknown",
        "undeclared",
        "symlink",
    ],
)
def test_ambiguous_modified_unknown_or_unrelated_proofs_never_fall_back(tmp_path, mutation):
    receipts = [
        "financial-publication.json",
        "issuer-publication.json",
        "aerocivil-movements-publication.json",
    ]
    repo = manifest(tmp_path, receipts)
    document = json.loads((tmp_path / "publication_manifest.json").read_bytes())
    proof = tmp_path / "aerocivil-movements-publication.json"
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    if mutation == "modified":
        proof.write_text("tampered")
    elif mutation == "size":
        document["files"][-1]["bytes"] += 1
        (tmp_path / "publication_manifest.json").write_text(json.dumps(document))
    elif mutation == "invalid_commit":
        replace_proof(tmp_path, receipts[-1], "latest")
    elif mutation == "missing_commit":
        replace_proof(tmp_path, receipts[-1], "f" * 40)
    elif mutation == "blob":
        blob = (
            subprocess.check_output(["git", "hash-object", "-w", "--stdin"], cwd=repo, input=b"not a commit")
            .decode()
            .strip()
        )
        replace_proof(tmp_path, receipts[-1], blob)
    elif mutation == "tie":
        replace_proof(tmp_path, "issuer-publication.json", head)
    elif mutation == "fork":
        first = subprocess.check_output(
            ["git", "rev-list", "--max-parents=0", "HEAD"], cwd=repo, text=True
        ).strip()
        subprocess.run(["git", "checkout", "--detach", "-q", first], cwd=repo, check=True)
        replace_proof(tmp_path, "issuer-publication.json", new_commit(repo, "unrelated fork"))
    elif mutation == "duplicate":
        document["files"].append(document["files"][0])
        (tmp_path / "publication_manifest.json").write_text(json.dumps(document))
    elif mutation == "unknown":
        document["files"].append({"path": "new-publication.json"})
        (tmp_path / "publication_manifest.json").write_text(json.dumps(document))
    elif mutation == "undeclared":
        document["files"] = document["files"][:-1]
        (tmp_path / "publication_manifest.json").write_text(json.dumps(document))
    else:
        target = tmp_path / "copied-proof.json"
        proof.rename(target)
        proof.symlink_to(target)
    with pytest.raises(ValueError):
        verifier_for(tmp_path, repo)


def test_single_proof_is_manifest_bound_and_explicit_repository_is_used(tmp_path, monkeypatch):
    repo = manifest(tmp_path / "site", ["issuer-publication.json"])
    monkeypatch.chdir(tmp_path.parent)
    assert verifier_for(tmp_path / "site", repo) == "src.publish.issuer_scope"
    (tmp_path / "site/issuer-publication.json").write_text("{}")
    with pytest.raises(ValueError, match="manifest pins"):
        verifier_for(tmp_path / "site", repo)
