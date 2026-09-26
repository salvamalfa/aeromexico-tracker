"""Unit tests for src/publish/manifest.py — no private data, no npm build."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from src.publish import manifest as manifest_mod


def _init_repo(root: Path) -> None:
    for args in (
        ["init", "-q"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _commit_all(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True, capture_output=True)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "a.txt"
    path.write_bytes(b"hello world")
    import hashlib

    assert manifest_mod.sha256_file(path) == hashlib.sha256(b"hello world").hexdigest()


def test_file_entries_excludes_manifest_and_sorts_by_path(tmp_path: Path) -> None:
    _write(tmp_path / "b.json", "{}")
    _write(tmp_path / "a" / "c.json", "{}")
    _write(tmp_path / manifest_mod.MANIFEST_NAME, "{}")

    entries = manifest_mod.file_entries(tmp_path)
    paths = [e["path"] for e in entries]
    assert paths == ["a/c.json", "b.json"]
    assert all(e["bytes"] == 2 for e in entries)


def test_contract_hashes_covers_every_declared_file() -> None:
    hashes = manifest_mod.contract_hashes()
    assert set(hashes) == set(manifest_mod.CONTRACT_FILES)
    assert all(len(v) == 64 for v in hashes.values())


def test_build_manifest_is_deterministic_and_hashes_of_hashes(tmp_path: Path) -> None:
    _write(tmp_path / "index.html", "<html></html>")
    analysis_manifest = [
        {
            "period_id": "2026Q2",
            "version": "v1",
            "content_hash": "h",
            "evidence_fingerprint": "e",
            "approval_event": "a",
            "audit_hash": "d",
        }
    ]
    manifest_one = manifest_mod.build_manifest(
        tmp_path, analysis_manifest, code_commit="a" * 40, generated_at="2026-09-26T00:00:00+00:00"
    )
    manifest_two = manifest_mod.build_manifest(
        tmp_path, analysis_manifest, code_commit="a" * 40, generated_at="2026-09-26T00:00:00+00:00"
    )
    assert manifest_one == manifest_two
    assert manifest_mod.manifest_hash(manifest_one) == manifest_mod.manifest_hash(manifest_two)

    manifest_mod.write_manifest(tmp_path, manifest_one)
    loaded = manifest_mod.load_manifest(tmp_path)
    assert loaded == manifest_one
    # The manifest file itself must not be one of its own listed files.
    assert manifest_mod.MANIFEST_NAME not in {e["path"] for e in loaded["files"]}


def test_manifest_hash_changes_when_a_file_entry_changes() -> None:
    base = {"schema_version": "publication_manifest_v1", "files": [{"path": "a", "sha256": "x", "bytes": 1}]}
    other = json.loads(json.dumps(base))
    other["files"][0]["sha256"] = "y"
    assert manifest_mod.manifest_hash(base) != manifest_mod.manifest_hash(other)


def test_refuse_if_build_inputs_dirty_passes_on_a_clean_tree(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write(tmp_path / "src" / "a.py", "x = 1\n")
    _commit_all(tmp_path, "initial")

    manifest_mod.refuse_if_build_inputs_dirty(tmp_path)  # must not raise


def test_refuse_if_build_inputs_dirty_raises_on_an_uncommitted_src_change(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write(tmp_path / "src" / "a.py", "x = 1\n")
    _commit_all(tmp_path, "initial")

    _write(tmp_path / "src" / "a.py", "x = 2\n")

    with pytest.raises(RuntimeError, match="uncommitted changes"):
        manifest_mod.refuse_if_build_inputs_dirty(tmp_path)


def test_refuse_if_build_inputs_dirty_raises_on_an_untracked_new_file(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write(tmp_path / "src" / "a.py", "x = 1\n")
    _commit_all(tmp_path, "initial")

    _write(tmp_path / "contracts" / "new.json", "{}")

    with pytest.raises(RuntimeError, match="uncommitted changes"):
        manifest_mod.refuse_if_build_inputs_dirty(tmp_path)


def test_refuse_if_build_inputs_dirty_ignores_excluded_generated_paths(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write(tmp_path / "src" / "a.py", "x = 1\n")
    _write(tmp_path / ".gitignore", "web/public/data/\nweb/dist/\n")
    _commit_all(tmp_path, "initial")

    _write(tmp_path / "web" / "public" / "data" / "v1" / "flights.json", "{}")
    _write(tmp_path / "web" / "dist" / "index.html", "<html></html>")

    manifest_mod.refuse_if_build_inputs_dirty(tmp_path)  # must not raise: generated/ignored


def test_refuse_if_build_inputs_dirty_ignores_paths_outside_build_inputs(tmp_path: Path) -> None:
    _init_repo(tmp_path)
    _write(tmp_path / "src" / "a.py", "x = 1\n")
    _commit_all(tmp_path, "initial")

    _write(tmp_path / "docs" / "notes.md", "scratch\n")

    manifest_mod.refuse_if_build_inputs_dirty(tmp_path)  # must not raise: docs/ isn't a build input
