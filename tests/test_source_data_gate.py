"""Adversarial guards for the shared selective source gate, with no live writes."""

import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.publish import source_data_scope as scope
from src.publish import source_data_update as update


def reference(path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def test_physical_reference_rejects_tamper_symlink_and_escape(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    p = repo / "source.json"
    p.write_text("original")
    ref = reference(p)
    assert update.file_ref(ref, repo) == p
    p.write_text("changed")
    with pytest.raises(ValueError):
        update.file_ref(ref, repo)
    link = repo / "linked.json"
    link.symlink_to(p)
    with pytest.raises(ValueError):
        update.file_ref(reference(link), repo)
    outside = tmp_path / "outside.json"
    outside.write_text("private")
    with pytest.raises(ValueError):
        update.file_ref(reference(outside), repo)


def grant(tmp_path):
    spec = {
        k: k
        for k in (
            "product",
            "period_id",
            "source_binding",
            "baseline_commit",
            "data_files",
            "frontend_files",
            "producer_code_version",
            "contract_changes",
        )
    }
    value = {
        "schema_version": "source_data_authorization_v1",
        "status": "authorized",
        "scope": scope.scope(spec),
        "owner_consent": {
            "source_reference": "unit-test-only",
            "instruction": "Synthetic fixture, never publication authority",
            "received_at": "2026-10-01T00:00:00Z",
        },
    }
    p = tmp_path / "analysis_runs/dashboard_updates/authorizations"
    p.mkdir(parents=True)
    raw = (json.dumps(value) + "\n").encode()
    digest = hashlib.sha256(raw).hexdigest()
    file = p / (digest + ".json")
    file.write_bytes(raw)
    spec["authorization_sha256"] = digest
    return spec, {"authorization": reference(file)}, file


def test_inspection_is_not_an_exposure_authority(tmp_path):
    with pytest.raises(ValueError, match="retained owner consent"):
        update.authority({"authorization": None}, {}, tmp_path)


def test_exact_source_exposure_authority_is_bound_to_scope_and_canonical_file(tmp_path):
    spec, request, file = grant(tmp_path)
    assert update.authority(request, spec, tmp_path) == file
    other = deepcopy(spec)
    other["period_id"] = "another-period"
    with pytest.raises(ValueError, match="another exact release"):
        update.authority(request, other, tmp_path)
    renamed = file.with_name("renamed.json")
    renamed.write_bytes(file.read_bytes())
    with pytest.raises(ValueError, match="canonical"):
        update.authority({"authorization": reference(renamed)}, spec, tmp_path)


def test_unknown_source_fails_before_importing_or_publishing():
    with pytest.raises(ValueError, match="no reviewed"):
        scope.adapter("unreviewed_source")


def test_snapshot_preserves_physical_source_changes_and_library_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "input_snapshot", lambda *a, **k: {})
    p = tmp_path / "source.json"
    p.write_text("original")
    request = {"authorization": None}
    first = update.snapshot(p, request, p, [], {"input_files": [str(p)]}, tmp_path)
    p.write_text("changed")
    second = update.snapshot(p, request, p, [], {"input_files": [str(p)]}, tmp_path)
    assert first != second


def test_snapshot_without_platform_xattr_api_preserves_content(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "input_snapshot", lambda *a, **k: {})
    monkeypatch.delattr(os, "listxattr", raising=False)
    monkeypatch.delattr(os, "getxattr", raising=False)
    p = tmp_path / "source.json"
    p.write_bytes(b"original")
    first = update.snapshot(p, {"authorization": None}, p, [], {"input_files": [str(p)]}, tmp_path)
    assert first == {
        "source.json": {"sha256": hashlib.sha256(b"original").hexdigest(), "library_identity": {}}
    }
    p.write_bytes(b"changed")
    assert update.snapshot(p, {"authorization": None}, p, [], {"input_files": [str(p)]}, tmp_path) != first


def test_snapshot_still_detects_library_metadata_changes_on_supported_platform(tmp_path, monkeypatch):
    monkeypatch.setattr(update, "input_snapshot", lambda *a, **k: {})
    p = tmp_path / "source.json"
    p.write_bytes(b"original")
    attribute = b"retained-library-id"
    monkeypatch.setattr(os, "listxattr", lambda _: ["user.library-file-id", "user.unrelated"], raising=False)

    def read_attribute(path, key):
        assert path == p and key == "user.library-file-id"
        return attribute

    monkeypatch.setattr(os, "getxattr", read_attribute, raising=False)
    first = update.snapshot(p, {"authorization": None}, p, [], {"input_files": [str(p)]}, tmp_path)
    assert first["source.json"]["library_identity"] == {
        "user.library-file-id": hashlib.sha256(attribute).hexdigest()
    }
    attribute = b"another-library-id"
    second = update.snapshot(p, {"authorization": None}, p, [], {"input_files": [str(p)]}, tmp_path)
    assert first != second
    assert first["source.json"]["sha256"] == second["source.json"]["sha256"]


@pytest.mark.parametrize("api", ["listxattr", "getxattr"])
def test_snapshot_fails_closed_if_supported_xattr_api_errors(tmp_path, monkeypatch, api):
    monkeypatch.setattr(update, "input_snapshot", lambda *a, **k: {})
    p = tmp_path / "source.json"
    p.write_bytes(b"original")
    monkeypatch.setattr(os, "listxattr", lambda _: ["user.library-file-id"], raising=False)
    monkeypatch.setattr(os, "getxattr", lambda *a: b"retained", raising=False)

    def fail(*args):
        raise PermissionError("Cannot verify retained library metadata")

    monkeypatch.setattr(os, api, fail)
    with pytest.raises(PermissionError, match="Cannot verify"):
        update.snapshot(p, {"authorization": None}, p, [], {"input_files": [str(p)]}, tmp_path)


def replay_fixture(tmp_path, monkeypatch, source_inputs):
    """Exercise the real file checks while replacing only native source adapters."""
    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    baseline = repo / "site"
    target = "data/v1/market-demand.json"
    (baseline / target).parent.mkdir(parents=True)
    (baseline / target).write_text('{"retained": true}')
    profiles = [repo / "am-profile.json", repo / "afac-profile.json"]
    for profile in profiles:
        profile.write_text("{}")
    products = ["am_traffic_ir", "afac_carriers"]

    def native_adapter(product):
        return SimpleNamespace(
            TARGETS=(target,),
            replay=lambda *_: {
                "source_binding": {"product": product, "period": "2026M09"},
                "projection": {product: True},
                "input_files": source_inputs[product],
            },
            public_outputs=lambda before, projection: {
                target: scope.encoded({**json.loads(before[target]), **projection})
            },
        )

    monkeypatch.setattr(update, "adapter", native_adapter)
    units = [
        {"product": product, "period": "2026M09", "source_profile": reference(profile)}
        for product, profile in zip(products, profiles, strict=True)
    ]
    return repo, baseline, profiles, {**units[0], "additional_sources": units[1:]}


def test_replay_combines_mixed_native_paths_as_one_sorted_absolute_json_closure(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    inputs = repo / "inputs"
    inputs.mkdir(parents=True)
    shared, native = inputs / "shared.txt", inputs / "native.txt"
    shared.write_text("shared native evidence")
    native.write_text("other independently retained native evidence")
    repo, baseline, profiles, request = replay_fixture(
        tmp_path,
        monkeypatch,
        {
            "am_traffic_ir": [str(shared), Path("inputs/shared.txt")],
            "afac_carriers": [native, "inputs/native.txt", shared, str(shared)],
        },
    )
    value, outputs = update.replay(request, profiles[0], baseline, repo)
    assert value["input_files"] == sorted(str(p) for p in [shared, native, *profiles])
    assert all(isinstance(p, str) and Path(p).is_absolute() for p in value["input_files"])
    assert json.loads(json.dumps(value)) == value
    assert json.loads(outputs["data/v1/market-demand.json"]) == {
        "retained": True,
        "am_traffic_ir": True,
        "afac_carriers": True,
    }


@pytest.mark.parametrize(
    "invalid", ["outside_string", "outside_path", "parent_escape", "symlink", "ancestor_symlink"]
)
def test_replay_path_normalization_preserves_escape_and_symlink_rejections(tmp_path, monkeypatch, invalid):
    repo = tmp_path / "repo"
    inputs = repo / "inputs"
    inputs.mkdir(parents=True)
    source = inputs / "source.txt"
    source.write_text("valid native evidence")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside the declared checkout")
    link = repo / "linked.txt"
    link.symlink_to(source)
    linked_folder = repo / "linked-folder"
    linked_folder.symlink_to(inputs, target_is_directory=True)
    invalid_path = {
        "outside_string": str(outside),
        "outside_path": outside,
        "parent_escape": Path("../outside.txt"),
        "symlink": link,
        "ancestor_symlink": "linked-folder/source.txt",
    }[invalid]
    repo, baseline, profiles, request = replay_fixture(
        tmp_path,
        monkeypatch,
        {"am_traffic_ir": [str(source)], "afac_carriers": [invalid_path]},
    )
    with pytest.raises(ValueError, match="outside its checkout or a symlink"):
        update.replay(request, profiles[0], baseline, repo)
