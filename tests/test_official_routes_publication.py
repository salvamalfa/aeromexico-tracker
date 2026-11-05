"""Public verification is portable; publishing still requires original source replay."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from src.dashboard.official_routes_contract import dataset_version, encoded
from src.publish import official_routes_projection as projection
from src.publish import source_data_scope as scope
from src.source_updates.official_routes import CODE_FILES


@pytest.fixture
def published(tmp_path, monkeypatch):
    payload = json.loads((Path(__file__).parent / "fixtures/official-routes.example.json").read_bytes())
    raw = encoded(payload)
    code = projection.fingerprints()
    monkeypatch.setattr(projection, "fingerprints", lambda repo: deepcopy(code))
    profile = dict(
        schema_version="official_route_profile_v1", period="2026M09",
        selection={"path": "tmp/private-originals/selection.json", "sha256": "b" * 64},
        code_sha256=deepcopy(code), dataset_version=payload["dataset_version"],
        output_sha256=hashlib.sha256(raw).hexdigest(), activation="none", publication="not_authorized",
        retained_approvals=dict(baseline_commit="e" * 40, parent_inputs=dict(
            root="tmp/private-originals/parent", inventory={"path": "tmp/inventory.json", "sha256": "f" * 64},
            request={"path": "tmp/request.json", "sha256": "a" * 64})),
    )
    binding = dict(
        product="official_routes", period=profile["period"],
        receipt_id=hashlib.sha256(encoded(profile)).hexdigest()[:32],
        candidate_as_of=payload["metadata"]["source_as_of"],
        output_sha256={"official_routes": profile["output_sha256"]},
    )
    unit = dict(product="official_routes", period=profile["period"], source_binding=binding,
                projection=dict(profile=profile, dataset_version=profile["dataset_version"],
                                payload_sha256=profile["output_sha256"]))
    site = tmp_path / "site"
    path = site / projection.PUBLIC_PATH
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    def missing(*args):
        raise ValueError("Private originals deliberately absent")
    monkeypatch.setattr(projection, "physical", missing)
    return site, unit, payload


def test_existing_public_json_verifies_without_private_originals(published, tmp_path):
    site, unit, _ = published
    assert not (tmp_path / "tmp/private-originals").exists()
    assert projection.verify_public_outputs(site, unit, tmp_path) == {
        projection.PUBLIC_PATH: (site / projection.PUBLIC_PATH).read_bytes()
    }
    # These are the real paths used by inspect/prepare/publish, not the public reader.
    with pytest.raises(ValueError, match="Private originals deliberately absent"):
        projection.replay(unit["projection"]["profile"], site)
    with pytest.raises(ValueError, match="Private originals deliberately absent"):
        projection.public_outputs({projection.PUBLIC_PATH: b"{}\n"}, unit["projection"])


@pytest.mark.parametrize("mutation", [
    lambda u: u["projection"]["profile"]["selection"].update(sha256="c" * 64),
    lambda u: u["projection"].update(dataset_version="e" * 64),
    lambda u: u["projection"].update(payload_sha256="f" * 64),
    lambda u: u["source_binding"].update(receipt_id="a" * 32),
    lambda u: u["source_binding"].update(candidate_as_of="2026-11-04T00:00:00Z"),
    lambda u: u["source_binding"].update(output_sha256={"official_routes": "a" * 64}),
    lambda u: u.update(period="2026M10"),
])
def test_public_verifier_rejects_changed_profile_source_dataset_and_producer(published, tmp_path, mutation):
    site, unit, _ = published
    mutation(unit)
    with pytest.raises(ValueError):
        projection.verify_public_outputs(site, unit, tmp_path)


@pytest.mark.parametrize("code_file", CODE_FILES)
def test_every_numeric_producer_pin_is_still_required(published, tmp_path, code_file):
    site, unit, _ = published
    unit["projection"]["profile"]["code_sha256"][code_file] = "d" * 64
    with pytest.raises(ValueError, match="producer/reference changed"):
        projection.verify_public_outputs(site, unit, tmp_path)


@pytest.mark.parametrize("change", ["count", "source", "identity", "semantic"])
def test_changed_public_json_never_becomes_approved_by_rehashing_it(published, tmp_path, change):
    site, unit, payload = published
    if change == "count":
        payload["networks"][0]["routes"][0]["departures"] += 1
    elif change == "source":
        payload["sources"][0]["url"] = "https://www.gob.mx/afac/another-source"
    elif change == "identity":
        payload["dataset_version"] = "a" * 64
    else:
        payload["networks"][0]["grain"] = "airport_pair"
        payload["dataset_version"] = dataset_version(payload)
    (site / projection.PUBLIC_PATH).write_bytes(encoded(payload))
    with pytest.raises(ValueError):
        projection.verify_public_outputs(site, unit, tmp_path)


def test_public_semantics_still_reject_even_when_local_hashes_are_forged(published, tmp_path):
    site, unit, payload = published
    payload["networks"][0]["grain"] = "airport_pair"
    payload["dataset_version"] = dataset_version(payload)
    raw = encoded(payload)
    (site / projection.PUBLIC_PATH).write_bytes(raw)
    unit["projection"]["profile"].update(output_sha256=hashlib.sha256(raw).hexdigest(),
                                        dataset_version=payload["dataset_version"])
    unit["projection"].update(payload_sha256=hashlib.sha256(raw).hexdigest(),
                               dataset_version=payload["dataset_version"])
    with pytest.raises(ValueError):
        projection.verify_public_outputs(site, unit, tmp_path)


def public_site(published, tmp_path, monkeypatch):
    """Use the shared preservation verifier, stubbing only the old baseline/commit transport."""
    site, unit, _ = published
    legacy = "data/v1/legacy.json"
    (site / legacy).write_bytes(b'{"retained":true}\n')
    old = dict(files=scope.pins({legacy: (site / legacy).read_bytes()}),
               contracts={}, analysis_manifest=[{"synthetic": "original retained identity"}])
    spec = dict(product=unit["product"], period_id=unit["period"], projection=unit["projection"],
                source_binding=unit["source_binding"], baseline_commit="a" * 40,
                baseline_manifest_sha256="b" * 64, contract_changes={"official-routes.schema.json": "c" * 64},
                data_files=scope.pins({projection.PUBLIC_PATH: (site / projection.PUBLIC_PATH).read_bytes()}),
                frontend_files=[], producer_code_version="d" * 64)
    anchor = tmp_path / scope.ANCHOR
    anchor.parent.mkdir(parents=True)
    anchor.write_bytes(scope.encoded(spec))
    proof = dict(schema_version="source_data_publication_v1", anchor_sha256=scope.sha(anchor.read_bytes()),
                 remote_witness=dict(baseline_commit=spec["baseline_commit"],
                                     manifest_sha256=spec["baseline_manifest_sha256"], files_verified=1,
                                     origin=scope.transport.ORIGIN, deployment_run=1, deployment_commit="e" * 40))
    (site / scope.PROOF).write_bytes(scope.encoded(proof))
    current = dict(files=[*old["files"], *spec["data_files"], *scope.pins({scope.PROOF: (site / scope.PROOF).read_bytes()})],
                   contracts=spec["contract_changes"], analysis_manifest=old["analysis_manifest"])
    (site / scope.manifests.MANIFEST_NAME).write_bytes(scope.encoded(current))
    monkeypatch.setattr(scope.transport, "baseline", lambda *args: (old, b""))
    monkeypatch.setattr(scope.transport, "frontend_entries", lambda *args: [])
    monkeypatch.setattr(scope.transport, "_git", lambda repo, *args: (site / legacy).read_bytes()
                        if args[0] == "show" else b"")
    monkeypatch.setattr(scope.members, "compose", lambda *args: pytest.fail("Public verification replayed private sources"))
    return site, spec, legacy


def test_shared_public_entry_verifies_new_site_without_sources(published, tmp_path, monkeypatch):
    from src.analysis_agent import entity_adapter
    from src.publish import verify
    site, spec, legacy = public_site(published, tmp_path, monkeypatch)
    monkeypatch.setattr(scope, "anchor", lambda repo: spec)
    monkeypatch.setattr(scope, "verify_historical_baseline", lambda *args: None)
    monkeypatch.setattr(entity_adapter, "code_version", lambda: spec["producer_code_version"])
    def checked(site, *, preserved_approval_files):
        assert preserved_approval_files == frozenset({legacy})
        return []
    monkeypatch.setattr(verify, "_verify_site", checked)
    assert scope.verify_source_data(site, tmp_path) == []
    (site / legacy).write_bytes(b"changed unrelated history")
    # The pinned original baseline differs even though the old Git transport is stubbed.
    assert scope.verify_source_data(site, tmp_path)


@pytest.mark.parametrize("change", ["data_pin", "extra_file", "proof", "analysis"])
def test_public_preservation_guard_stays_closed(published, tmp_path, monkeypatch, change):
    site, spec, _ = public_site(published, tmp_path, monkeypatch)
    if change == "data_pin":
        spec["data_files"][0]["sha256"] = "f" * 64
    elif change == "extra_file":
        (site / "unexpected.json").write_bytes(b"{}")
    elif change == "proof":
        (site / scope.PROOF).write_bytes(b"{}")
    else:
        path = site / scope.manifests.MANIFEST_NAME
        value = json.loads(path.read_bytes()); value["analysis_manifest"] = []
        path.write_bytes(scope.encoded(value))
    with pytest.raises((ValueError, KeyError)):
        scope.preserved_files(site, tmp_path, spec)
