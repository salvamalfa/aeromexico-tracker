"""Independent path and Git-object counterexamples; synthetic inputs only."""

import hashlib
import json
import os
import subprocess

import pytest

from src.publish import financial_continuity as continuity
from src.publish import financial_continuity_inputs as inputs


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


@pytest.fixture
def git_tree(tmp_path):
    root = tmp_path / "repository"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Independent synthetic fixture")
    git(root, "config", "user.email", "independent@example.invalid")
    (root / "site").mkdir()
    return root


def commit(root):
    git(root, "add", ".")
    git(root, "commit", "-qm", "Independent synthetic fixture")
    return git(root, "rev-parse", "HEAD").decode().strip()


@pytest.mark.parametrize("name", ["plain", "nested/file", "unicode/café"])
def test_regular_valid_file_bytes(tmp_path, name):
    root = tmp_path / "root"
    file = root / name
    file.parent.mkdir(parents=True)
    file.write_bytes(b"synthetic retained bytes")
    assert inputs.regular(file, root) == b"synthetic retained bytes"


@pytest.mark.parametrize("name", ["../outside", "nested/../../outside"])
def test_regular_rejects_lexical_parent_escape_before_read(tmp_path, name):
    root = tmp_path / "root"
    (root / "nested").mkdir(parents=True)
    (tmp_path / "outside").write_bytes(b"synthetic outside root")
    with pytest.raises(ValueError):
        inputs.regular(root / name, root)


@pytest.mark.parametrize("kind", ["leaf", "parent", "root", "broken"])
def test_regular_rejects_symlink_components(tmp_path, kind):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file").write_bytes(b"synthetic outside root")
    if kind in {"leaf", "broken"}:
        path = root / "alias"
        path.symlink_to(outside / ("file" if kind == "leaf" else "missing"))
    elif kind == "parent":
        (root / "alias").symlink_to(outside, target_is_directory=True)
        path = root / "alias/file"
    else:
        alias = tmp_path / "root-alias"
        alias.symlink_to(root, target_is_directory=True)
        (root / "file").write_bytes(b"synthetic inside root")
        root, path = alias, alias / "file"
    with pytest.raises(ValueError, match="symlink|regular file"):
        inputs.regular(path, root)


def test_regular_rejects_fifo_without_opening_it(tmp_path):
    path = tmp_path / "fifo"
    os.mkfifo(path)
    with pytest.raises(ValueError, match="regular file"):
        inputs.regular(path, tmp_path)


@pytest.mark.parametrize("name", ["ordinary", "space file", "line\nbreak", "café"])
def test_git_inventory_preserves_exact_blob_bytes_and_names(git_tree, name):
    raw = b"exact synthetic bytes\x00\xff"
    (git_tree / "site" / name).write_bytes(raw)
    head = commit(git_tree)
    assert inputs.tree_files(git_tree, head, "site") == {
        name: {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    }


@pytest.mark.parametrize("pattern", ["site/omitted", "site/*", "site/"])
def test_git_export_ignore_cannot_silently_omit_committed_site_blobs(git_tree, pattern):
    raw = b"synthetic committed object which archive would omit"
    (git_tree / "site/omitted").write_bytes(raw)
    (git_tree / ".gitattributes").write_text(pattern + " export-ignore\n")
    head = commit(git_tree)
    assert inputs.tree_files(git_tree, head, "site") == {
        "omitted": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    }


def test_git_export_subst_cannot_replace_committed_blob_bytes(git_tree):
    raw = b"synthetic $Format:%H$\n"
    (git_tree / "site/proof").write_bytes(raw)
    (git_tree / ".gitattributes").write_text("site/proof export-subst\n")
    head = commit(git_tree)
    assert inputs.tree_files(git_tree, head, "site") == {
        "proof": {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    }


def test_git_site_symlink_is_rejected(git_tree):
    (git_tree / "site/link").symlink_to("synthetic-target")
    head = commit(git_tree)
    with pytest.raises(ValueError, match="non-regular|regular"):
        inputs.tree_files(git_tree, head, "site")


def test_cli_requires_explicit_local_only_before_verifying(monkeypatch):
    def unexpected(*args):
        pytest.fail("Missing opt-in must not invoke any source validation")

    monkeypatch.setattr(continuity, "verify_local", unexpected)
    with pytest.raises(SystemExit) as error:
        continuity.main(["synthetic-site"])
    assert error.value.code == 2


@pytest.mark.parametrize("problems", [[], ["synthetic rejected receipt"]])
def test_cli_never_claims_publication_authority(monkeypatch, capsys, problems):
    monkeypatch.setattr(continuity, "verify_local", lambda *args: problems)
    assert continuity.main(["synthetic-site", "--local-only"]) == bool(problems)
    doc = json.loads(capsys.readouterr().out)
    assert doc["publication_authorized"] is False
    assert doc["valid"] is (not problems)
    assert doc["problems"] == problems
