"""Isolated approval replays retain evidence without trusting links or copies."""

import hashlib
import json
from pathlib import Path

import pytest

from src.publish.issuer_replay_inputs import materialize_issuer_inputs


def hashed(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def issuer_files(tmp_path):
    root, destination = tmp_path / "repo", tmp_path / "verifier"
    root.mkdir()
    destination.mkdir()
    workspace = Path("tmp/source-updates/one-issuer")
    data = {
        "data/gold/fact_values.parquet": b"PAR1-retained-fact",
        "data/bronze/issuer/report.pdf": b"primary source",
        "data/bronze/issuer/report.pdf.meta.json": b'{"downloaded_at":"2026-10-29T06:00:00Z"}',
        "receipts/retained-" + "a" * 32 + ".json": b'{"immutable":"retention"}',
    }
    for name, raw in data.items():
        path = root / workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    package_id = "VIVA_AEROBUS_2026Q3_" + "b" * 64
    package = {
        "package_id": package_id,
        "entity_key": "VIVA_AEROBUS",
        "period_id": "2026Q3",
        "workspace": workspace.as_posix(),
        "retention_id": "a" * 32,
        "retention_receipt_sha256": hashed(data["receipts/retained-" + "a" * 32 + ".json"]),
        "source_binding": {"output_sha256": {"gold/fact_values": hashed(data["data/gold/fact_values.parquet"])}},
        "sources": [{"source_file": "issuer/report.pdf", "artifact_sha256": hashed(data["data/bronze/issuer/report.pdf"])}],
    }
    package_path = root / "analysis_runs/evidence" / (package_id + ".json")
    package_path.parent.mkdir(parents=True)
    package_path.write_text(json.dumps(package))
    record = {
        "draft": {
            "source_profile": "issuer_quarter_v1",
            "package_id": package_id,
            "entity_key": "VIVA_AEROBUS",
            "period_id": "2026Q3",
        }
    }
    record_path = root / "analysis_runs/record.json"
    record_path.write_text(json.dumps(record))
    return root, destination, workspace, package_path, package, record_path, data


def test_materializes_exact_bytes_and_reuses_identical_evidence(issuer_files):
    root, destination, workspace, _, _, record, data = issuer_files
    expected = [{"workspace": workspace.as_posix(), "files": len(data)}]
    assert materialize_issuer_inputs([record], root, destination) == expected
    assert materialize_issuer_inputs([record], root, destination) == expected
    for name, raw in data.items():
        assert (destination / workspace / name).read_bytes() == raw
        assert (root / workspace / name).read_bytes() == raw
        assert not (destination / workspace / name).is_symlink()


@pytest.mark.parametrize("workspace", ["/tmp/private", "tmp/../outside", "tmp/source-updates/../source", "data/bronze", "tmp/source-updates"])
def test_rejects_workspace_escape(issuer_files, workspace):
    root, destination, _, package_path, package, record, _ = issuer_files
    package["workspace"] = workspace
    package_path.write_text(json.dumps(package))
    with pytest.raises(ValueError):
        materialize_issuer_inputs([record], root, destination)


@pytest.mark.parametrize("field", ["package_id", "entity_key", "period_id"])
def test_rejects_another_record_identity(issuer_files, field):
    root, destination, _, package_path, package, record, _ = issuer_files
    package[field] = "another"
    package_path.write_text(json.dumps(package))
    with pytest.raises(ValueError, match="differs"):
        materialize_issuer_inputs([record], root, destination)


@pytest.mark.parametrize("name", ["data/gold/fact_values.parquet", "data/bronze/issuer/report.pdf", "receipts/retained-" + "a" * 32 + ".json"])
def test_rejects_changed_bound_bytes(issuer_files, name):
    root, destination, workspace, _, _, record, _ = issuer_files
    (root / workspace / name).write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed|differs"):
        materialize_issuer_inputs([record], root, destination)


def test_rejects_active_source_writer(issuer_files):
    root, destination, workspace, _, _, record, _ = issuer_files
    (root / workspace / ".source-update.lock").write_text("owner")
    with pytest.raises(ValueError, match="writer"):
        materialize_issuer_inputs([record], root, destination)


@pytest.mark.parametrize("directory", [False, True])
def test_rejects_source_symlinks(issuer_files, directory):
    root, destination, workspace, _, _, record, _ = issuer_files
    target = root / workspace / ("linked-directory" if directory else "linked-file")
    target.symlink_to(root / workspace / "data" if directory else root / workspace / "data/bronze/issuer/report.pdf", target_is_directory=directory)
    with pytest.raises(ValueError, match="symlinks"):
        materialize_issuer_inputs([record], root, destination)


def test_preserves_conflicting_existing_destination(issuer_files):
    root, destination, workspace, _, _, record, _ = issuer_files
    target = destination / workspace / "data/gold/fact_values.parquet"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"newer evidence")
    with pytest.raises(ValueError, match="Preserve conflicting"):
        materialize_issuer_inputs([record], root, destination)
    assert target.read_bytes() == b"newer evidence"


def test_legacy_record_does_not_materialize_unrelated_private_sources(tmp_path):
    record = tmp_path / "record.json"
    record.write_text(json.dumps({"draft": {"schema_version": "analyst_v1"}}))
    destination = tmp_path / "output"
    destination.mkdir()
    assert materialize_issuer_inputs([record], tmp_path, destination) == []
    assert list(destination.iterdir()) == []


def test_rejects_output_binding_path_escape(issuer_files):
    root, destination, _, package_path, package, record, _ = issuer_files
    package["source_binding"]["output_sha256"] = {"../../outside": "c" * 64}
    package_path.write_text(json.dumps(package))
    with pytest.raises(ValueError, match="escapes"):
        materialize_issuer_inputs([record], root, destination)
