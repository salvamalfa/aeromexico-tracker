"""Portable content identity and K→L with unchanged runtime, independent of Gold."""

import subprocess

import pytest

from src.source_updates.afac_native_producer import producer_version, verify_preparation, version_at_commit
from src.source_updates.afac_native_replay import binding, resolve_workspace


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo).decode().strip()


def test_code_preparation_accepts_data_only_descendant_and_rejects_code_change(tmp_path):
    for name in (
        "src/a.py",
        "scripts/b.py",
        "contracts/a.json",
        "config/a.yaml",
        "sql/a.sql",
        "data/reference/a.csv",
        "pyproject.toml",
        "uv.lock",
    ):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"frozen\n")
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Fixture")
    git(tmp_path, "config", "user.email", "fixture@example.invalid")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "code K")
    commit = git(tmp_path, "rev-parse", "HEAD")
    fingerprint = producer_version(tmp_path)
    assert version_at_commit(commit, tmp_path) == fingerprint
    path = tmp_path / "data/gold/fact.parquet"
    path.parent.mkdir()
    path.write_bytes(b"data-only fixture\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "data L")
    verify_preparation(commit, fingerprint, tmp_path)
    (tmp_path / "src/a.py").write_bytes(b"changed code\n")
    with pytest.raises(ValueError, match="producer changed"):
        verify_preparation(commit, fingerprint, tmp_path)


def test_dataset_binding_is_portable_across_repo_roots_and_rejects_absolute_aliases(tmp_path):
    relative = "tmp/source-updates/native-series"
    bindings = []
    for name in ("linux-root", "windows-root"):
        repo = tmp_path / name
        workspace = repo / relative
        for path, raw in {
            "data/afac_native_annual_inputs.json": b"{}\n",
            "data/afac_native_update.json": b"{}\n",
            "data/bronze/_manifest.jsonl": b"",
            "data/silver/bts_t100_segment.parquet": b"fixture\n",
            "data/reference/carrier_crosswalk.csv": b"fixture\n",
        }.items():
            file = workspace / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(raw)
        bindings.append(binding(workspace, repo))
        assert resolve_workspace(relative, repo) == workspace.resolve()
    assert bindings[0] == bindings[1]
    with pytest.raises(ValueError, match="repo-relative"):
        resolve_workspace("C:/Users/private/native-series", tmp_path)
    with pytest.raises(ValueError, match="repo-relative"):
        resolve_workspace("tmp/source-updates/../other", tmp_path)


def test_native_metadata_does_not_accept_a_foreign_source_or_failed_capture(tmp_path):
    import hashlib
    import json

    from src.parse.afac.annual_series import native_metadata

    path = tmp_path / "workbook.xlsx"
    path.write_bytes(b"fixture bytes; parser is a separate test")
    metadata = dict(
        source_system="afac",
        source_url="https://example.invalid/false.xlsx",
        http_status=200,
        bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    sidecar = path.with_suffix(".xlsx.meta.json")
    sidecar.write_text(json.dumps(metadata))
    with pytest.raises(ValueError):
        native_metadata(path)
    metadata.update(source_url="https://www.gob.mx/cms/uploads/attachment/file/test.xlsx", http_status=503)
    sidecar.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="successful official capture"):
        native_metadata(path)
