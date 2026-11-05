"""A real immutable B proof is a typed dependency; never a competing served root."""

import copy
import json
import os
import subprocess
import sys

import pytest

from scripts import check_pages_publication as selection
from src.publish import afac_history_contract as contract
from tests.test_afac_history_contract import ROOT, public_parent  # noqa: F401


@pytest.fixture
def graph(tmp_path, public_parent):  # noqa: F811 - imported pytest fixture
    parent, old, _, original, spec = public_parent
    proof = {
        "schema_version": contract.PROOF_SCHEMA,
        "anchor_sha256": "a" * 64,
        "remote_witness": {"baseline_commit": spec["baseline_commit"]},
        "candidate_parent": copy.deepcopy(parent),
    }
    files = {name: original[name] for name, _ in selection.VERIFIERS if name in original}
    files[contract.PROOF] = contract.encoded(proof)
    manifest = {"files": contract.pins(files), "analysis_manifest": old["analysis_manifest"]}
    for name, raw in files.items():
        (tmp_path / name).write_bytes(raw)
    (tmp_path / "publication_manifest.json").write_bytes(contract.encoded(manifest))
    return tmp_path, manifest, proof


def replace(site, manifest, proof):
    raw = contract.encoded(proof)
    (site / contract.PROOF).write_bytes(raw)
    manifest["files"] = [p for p in manifest["files"] if p["path"] != contract.PROOF] + contract.pins(
        {contract.PROOF: raw}
    )
    (site / "publication_manifest.json").write_bytes(contract.encoded(manifest))


def test_real_parent_and_final_root_share_actual_A_without_a_fake_B_witness(graph):
    site, _, proof = graph
    assert proof["remote_witness"]["baseline_commit"] != proof["candidate_parent"]["site_commit"]
    assert selection.verifier_for(site, ROOT) == "src.publish.afac_history_scope"


@pytest.mark.parametrize(
    "mutation",
    [
        "served_B",
        "wrong_source",
        "wrong_producer",
        "wrong_scope",
        "parent_pin",
        "parent_missing",
        "self_parent",
        "unknown_schema",
        "extra_field",
        "tamper",
        "size",
        "undeclared",
    ],
)
def test_dag_cannot_hide_a_parent_failure_or_relabel_prepared_B_as_served(graph, mutation):
    site, manifest, proof = graph
    if mutation == "served_B":
        proof["remote_witness"]["baseline_commit"] = proof["candidate_parent"]["site_commit"]
    elif mutation == "wrong_source":
        proof["candidate_parent"]["source_implementation_commit"] = proof["candidate_parent"]["site_commit"]
    elif mutation == "wrong_producer":
        proof["candidate_parent"]["producer_code_version"] = "c" * 64
    elif mutation == "wrong_scope":
        proof["candidate_parent"]["scope_sha256"] = "c" * 64
    elif mutation == "parent_pin":
        proof["candidate_parent"]["proof"]["sha256"] = "c" * 64
    elif mutation == "parent_missing":
        (site / contract.PARENT_PROOF).unlink()
    elif mutation == "self_parent":
        proof["candidate_parent"]["proof"]["path"] = contract.PROOF
    elif mutation == "unknown_schema":
        proof["schema_version"] = "composite_anything_v1"
    elif mutation == "extra_field":
        proof["allow_unverified_upstream"] = True
    replace(site, manifest, proof)
    if mutation == "tamper":
        (site / contract.PROOF).write_bytes(b"{}")
    elif mutation == "size":
        next(p for p in manifest["files"] if p["path"] == contract.PROOF)["bytes"] += 1
        (site / "publication_manifest.json").write_bytes(contract.encoded(manifest))
    elif mutation == "undeclared":
        manifest["files"] = [p for p in manifest["files"] if p["path"] != contract.PROOF]
        (site / "publication_manifest.json").write_bytes(contract.encoded(manifest))
    with pytest.raises((ValueError, FileNotFoundError)):
        selection.verifier_for(site, ROOT)


def test_v1_equal_baseline_tie_stays_a_failure(graph):
    site, manifest, _ = graph
    (site / contract.PROOF).unlink()
    manifest["files"] = [p for p in manifest["files"] if p["path"] != contract.PROOF]
    old = json.loads((site / contract.PARENT_PROOF).read_bytes())
    name = "issuer-publication.json"
    raw = contract.encoded({"remote_witness": old["remote_witness"]})
    (site / name).write_bytes(raw)
    manifest["files"] = [p for p in manifest["files"] if p["path"] != name] + contract.pins({name: raw})
    (site / "publication_manifest.json").write_bytes(contract.encoded(manifest))
    with pytest.raises(ValueError, match="ambiguous"):
        selection.verifier_for(site, ROOT)


def test_selected_composition_executes_its_exact_verifier_and_preserves_failure(graph, monkeypatch):
    from types import SimpleNamespace

    site, _, _ = graph
    calls = []
    monkeypatch.chdir(ROOT)
    # Route first with real Git, then inspect main's final execution boundary.
    module = selection.verifier_for(site, ROOT)
    monkeypatch.setattr(selection, "verifier_for", lambda *_: module)
    monkeypatch.setattr(
        selection.subprocess,
        "run",
        lambda command, **kwargs: calls.append((command, kwargs)) or SimpleNamespace(returncode=17),
    )
    assert selection.main([str(site)]) == 17
    assert calls[0][0][1:3] == ["-m", "src.publish.afac_history_scope"]
    assert calls[0][1]["cwd"] == ROOT


@pytest.mark.parametrize("exit_code,deny", [(0, False), (17, False), (0, True)])
def test_real_cli_uses_pinned_contract_and_verifier_without_pythonpath(tmp_path, exit_code, deny):
    # This is only the execution boundary fixture. The tests above independently
    # exercise the real DAG against B's immutable public Git tree and all refusals.
    preview = tmp_path / "pinned"
    package = preview / "src/publish"
    package.mkdir(parents=True)
    (preview / "src/__init__.py").touch()
    (package / "__init__.py").touch()
    (package / "afac_history_contract.py").write_text(
        "from pathlib import Path\n"
        "def proof_parent(repo,site,manifest,proof):\n"
        "    assert repo == Path.cwd() and site.is_absolute()\n"
        "    Path('contract-selection.txt').write_text(str(Path(__file__).resolve()))\n"
        "    if proof.get('deny'): raise ValueError('synthetic pinned DAG refusal')\n"
        "    return 'quarterly-story-publication.json', {}\n",
        encoding="utf-8",
    )
    (package / "afac_history_scope.py").write_text(
        "from pathlib import Path\n"
        "Path('executed.txt').write_text(str(Path(__file__).resolve()))\n"
        f"raise SystemExit({exit_code})\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q", str(preview)], check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "pinned execution fixture",
        ],
        cwd=preview,
        check=True,
    )
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=preview, text=True).strip()
    site = preview / "site"
    site.mkdir()
    files = {
        name: contract.encoded({"remote_witness": {"baseline_commit": commit}, "deny": deny})
        for name in (contract.PARENT_PROOF, contract.PROOF)
    }
    for name, raw in files.items():
        (site / name).write_bytes(raw)
    (site / "publication_manifest.json").write_bytes(contract.encoded({"files": contract.pins(files)}))
    environment = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_pages_publication.py"), "site/"],
        cwd=preview,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert (preview / "contract-selection.txt").read_text() == str(package / "afac_history_contract.py")
    if deny:
        assert result.returncode == 1
        assert "synthetic pinned DAG refusal" in result.stderr
        assert not (preview / "executed.txt").exists()
    else:
        assert result.returncode == exit_code
        assert (preview / "executed.txt").read_text() == str(package / "afac_history_scope.py")
