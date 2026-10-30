"""The scoped correction never inherits authority for foreign bytes or a bad baseline."""

import copy
import json
import sys
from types import SimpleNamespace

import pytest

from src.publish import movements_scope as scope


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = scope.encoded(value)
    path.write_bytes(raw)
    return {"path": str(path), "sha256": scope.sha(raw), "bytes": len(raw)}


@pytest.fixture
def release(tmp_path, monkeypatch):
    repo, site = tmp_path / "repo", tmp_path / "site"
    originals = {name: scope.encoded({"routes": [], "period": name}) for name in scope.TARGETS}
    originals.update(
        {"index.html": b"old", "data/v1/executive.json": b"{}", "data/v1/analysis/old.json": b"{}"}
    )
    old = {
        "files": [{"path": p, "sha256": scope.sha(b), "bytes": len(b)} for p, b in originals.items()],
        "contracts": {"flights.schema.json": "old", "privacy.yaml": "keep"},
        "analysis_manifest": [{"version": str(i)} for i in range(7)],
    }
    networks = []
    for name, raw in originals.items():
        target = site / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw if name != "index.html" else b"new")
        if name in scope.TARGETS:
            networks.append({"path": name, "sha256": scope.sha(raw), "bytes": len(raw)})
    anchor = {"test": "committed"}
    write(repo / scope.ANCHOR, anchor)
    witness = {
        "baseline_commit": "a" * 40,
        "manifest_sha256": "b" * 64,
        "files_verified": len(old["files"]),
        "origin": scope.transport.ORIGIN,
        "deployment_run": 1,
        "deployment_commit": "a" * 40,
    }
    write(
        site / scope.PROOF,
        {
            "schema_version": "aerocivil_movements_publication_v1",
            "anchor_sha256": scope.sha((repo / scope.ANCHOR).read_bytes()),
            "remote_witness": witness,
        },
    )
    spec = {
        "baseline_commit": "a" * 40,
        "baseline_manifest_sha256": "b" * 64,
        "flights_contract_sha256": "new",
        "projection_rows": [],
        "source_evidence": {"source_binding": {"current": "bound"}},
        "source_binding": {"current": "bound"},
        "network_files": networks,
        "frontend_files": [{"path": "index.html", "sha256": scope.sha(b"new"), "bytes": 3}],
    }
    current = {
        **copy.deepcopy(old),
        "contracts": {**old["contracts"], "flights.schema.json": "new"},
        "files": [*old["files"], {"path": scope.PROOF, "sha256": "c" * 64, "bytes": 1}],
    }
    write(site / scope.manifests.MANIFEST_NAME, current)
    monkeypatch.setattr(scope.transport, "baseline", lambda *_: (old, b"baseline"))

    def git(_repo, *args):
        return originals[args[1].split(":site/", 1)[1]] if args[0] == "show" else b""

    monkeypatch.setattr(scope.transport, "_git", git)
    module = SimpleNamespace(
        projection_frame=lambda rows, evidence: rows, project_file=lambda name, before, frame: before
    )
    monkeypatch.setitem(sys.modules, "src.publish.movements_projection", module)
    return repo, site, spec, old, current


def test_exact_scoped_delta_preserves_every_financial_byte(release):
    repo, site, spec, *_ = release
    preserved = scope.preserved_files(site, repo, spec)
    assert preserved == {"data/v1/executive.json", "data/v1/analysis/old.json"}


@pytest.mark.parametrize("foreign", ["data/v1/executive.json", "data/v1/analysis/old.json"])
def test_foreign_numbers_or_thesis_never_inherit_approval(release, foreign):
    repo, site, spec, *_ = release
    (site / foreign).write_text('{"changed":true}')
    with pytest.raises(ValueError, match="historical bytes"):
        scope.preserved_files(site, repo, spec)


@pytest.mark.parametrize(
    "mutation", ["thesis", "six", "contract", "extra", "missing_target", "frontend", "source", "witness"]
)
def test_scope_rejects_authority_and_surface_drift(release, mutation):
    repo, site, spec, old, current = release
    if mutation == "thesis":
        current["analysis_manifest"][0]["version"] = "forged"
    elif mutation == "six":
        old["analysis_manifest"].pop()
        current["analysis_manifest"].pop()
    elif mutation == "contract":
        current["contracts"]["privacy.yaml"] = "forged"
    elif mutation == "extra":
        current["files"].append({"path": "data/v1/new.json"})
    elif mutation == "missing_target":
        old["files"] = [f for f in old["files"] if f["path"] != scope.TARGETS[0]]
    elif mutation == "frontend":
        (site / "index.html").write_text("unreviewed")
    elif mutation == "source":
        spec["network_files"][0]["sha256"] = "f" * 64
    else:
        proof = json.loads((site / scope.PROOF).read_bytes())
        proof["remote_witness"]["origin"] = "https://foreign.invalid"
        write(site / scope.PROOF, proof)
    write(site / scope.manifests.MANIFEST_NAME, current)
    with pytest.raises(ValueError):
        scope.preserved_files(site, repo, spec)


def test_no_unmanifested_or_symlink_payloads(release):
    repo, site, spec, *_ = release
    (site / "unlisted").write_text("secret")
    with pytest.raises(ValueError, match="unmanifested"):
        scope.preserved_files(site, repo, spec)
    (site / "unlisted").unlink()
    (site / "link").symlink_to(site / "index.html")
    with pytest.raises(ValueError, match="symlinks"):
        scope.preserved_files(site, repo, spec)


def test_target_exact_hash_does_not_allow_foreign_semantics(release, monkeypatch):
    repo, site, spec, *_ = release
    module = sys.modules["src.publish.movements_projection"]
    monkeypatch.setattr(module, "project_file", lambda name, before, frame: {**before, "forged": True})
    with pytest.raises(ValueError, match="unrelated count or field"):
        scope.preserved_files(site, repo, spec)


def test_full_served_inventory_rejects_entity_or_old_period_components(tmp_path):
    path = tmp_path / "data/v1/flights/entities/INDUSTRY/international/2025M01.json"
    write(
        path,
        {
            "routes": [
                {
                    "flight_components": [
                        {"source_label": "Colombia · Aerocivil", "kind": "observed", "departures": 1}
                    ]
                }
            ]
        },
    )
    with pytest.raises(ValueError, match="flight components"):
        scope.require_no_observed_aerocivil(tmp_path)


def test_strong_historical_verifier_failure_cannot_fall_back(tmp_path, monkeypatch):
    from src.analysis_agent import entity_adapter

    monkeypatch.setattr(scope, "anchor", lambda _: {"producer_code_version": "code"})
    monkeypatch.setattr(entity_adapter, "code_version", lambda: "code")

    def refuse(*_):
        raise ValueError("released cohort replay failed")

    monkeypatch.setattr(scope, "verify_historical_baseline", refuse)
    monkeypatch.setattr(
        scope, "preserved_files", lambda *_: pytest.fail("must never bypass historical failure")
    )
    assert "released cohort replay failed" in scope.verify_movements(tmp_path, tmp_path)[0]


@pytest.fixture
def committed_anchor(tmp_path, monkeypatch):
    from src.source_updates.aerocivil import OUTPUTS

    repo = tmp_path / "repo"
    contract = repo / "contracts/web/flights.schema.json"
    contract.parent.mkdir(parents=True)
    contract.write_bytes(b"{}")
    spec = {
        "schema_version": "aerocivil_movements_release_v1",
        "product": "aerocivil",
        "period_id": "2026Q3",
        "stage": "movements",
        "baseline_commit": "a" * 40,
        "baseline_manifest_sha256": "b" * 64,
        "producer_code_version": "c" * 64,
        "authorization_sha256": "d" * 64,
        "source_binding": {
            "product": "aerocivil",
            "period": "2026M07",
            "receipt_id": "e" * 32,
            "candidate_as_of": "2026-10-21T01:06:33.087948+00:00",
            "output_sha256": {p: "f" * 64 for p in OUTPUTS},
        },
        "source_evidence": {},
        "projection_rows": [],
        "network_files": [{"path": p, "sha256": "0" * 64, "bytes": 1} for p in scope.TARGETS],
        "frontend_files": [{"path": "index.html", "sha256": "1" * 64, "bytes": 1}],
        "flights_contract_sha256": scope.sha(b"{}"),
    }
    path = repo / scope.ANCHOR
    write(path, spec)
    monkeypatch.setattr(
        scope.transport, "_git", lambda _, *args: path.read_bytes() if args[0] == "show" else b""
    )
    return repo, spec, path


def test_anchor_is_exact_finite_scope_with_native_source_and_digest(committed_anchor):
    repo, spec, _ = committed_anchor
    assert scope.anchor(repo) == spec


@pytest.mark.parametrize(
    "mutation",
    [
        "period",
        "stage",
        "new_target",
        "duplicate_target",
        "missing_target",
        "traversal",
        "source_alias",
        "source_outputs",
        "naive_cutoff",
        "boolean_size",
        "contract",
        "auth",
    ],
)
def test_anchor_rejects_profile_widening_or_malformed_pins(committed_anchor, mutation):
    repo, spec, path = committed_anchor
    if mutation == "period":
        spec["period_id"] = "2026Q4"
    elif mutation == "stage":
        spec["stage"] = "data_only"
    elif mutation == "new_target":
        spec["network_files"][0]["path"] = "data/v1/executive.json"
    elif mutation == "duplicate_target":
        spec["network_files"].append(spec["network_files"][0])
    elif mutation == "missing_target":
        spec["network_files"].pop()
    elif mutation == "traversal":
        spec["frontend_files"].append({"path": "../secret.js", "sha256": "0" * 64, "bytes": 1})
    elif mutation == "source_alias":
        spec["source_binding"]["product"] = "am_financials"
    elif mutation == "source_outputs":
        spec["source_binding"]["output_sha256"] = {"untyped": "f" * 64}
    elif mutation == "naive_cutoff":
        spec["source_binding"]["candidate_as_of"] = "2026-10-21T01:06:33"
    elif mutation == "boolean_size":
        spec["network_files"][0]["bytes"] = True
    elif mutation == "contract":
        spec["flights_contract_sha256"] = "0" * 64
    else:
        spec["authorization_sha256"] = None
    write(path, spec)
    with pytest.raises((ValueError, TypeError)):
        scope.anchor(repo)


def test_uncommitted_anchor_is_not_release_authority(committed_anchor, monkeypatch):
    repo, _, _ = committed_anchor
    monkeypatch.setattr(scope.transport, "_git", lambda *_: b"different committed bytes")
    with pytest.raises(ValueError, match="must be committed"):
        scope.anchor(repo)


def test_source_evidence_cannot_alias_another_checked_july_version(release):
    repo, site, spec, *_ = release
    spec["source_evidence"]["source_binding"] = {"current": "another-source"}
    with pytest.raises(ValueError, match="bound to its current July source"):
        scope.preserved_files(site, repo, spec)


def test_reachable_dashboard_assets_must_match_build_closure(release):
    repo, site, spec, old, current = release
    asset = site / "assets/retained.js"
    asset.parent.mkdir()
    asset.write_text("retained approved asset")
    pin = {
        "path": "assets/retained.js",
        "sha256": scope.sha(asset.read_bytes()),
        "bytes": asset.stat().st_size,
    }
    old["files"].append(pin)
    current["files"].append(pin)
    raw = b'<script src="assets/retained.js"></script>'
    (site / "index.html").write_bytes(raw)
    spec["frontend_files"] = [{"path": "index.html", "sha256": scope.sha(raw), "bytes": len(raw)}]
    proof = json.loads((site / scope.PROOF).read_bytes())
    proof["remote_witness"]["files_verified"] = len(old["files"])
    write(site / scope.PROOF, proof)
    write(site / scope.manifests.MANIFEST_NAME, current)
    with pytest.raises(ValueError, match="reachable dashboard closure"):
        scope.preserved_files(site, repo, spec)
