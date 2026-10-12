from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.publish.gate import PublicationRefused, _trusted_site_commit, require_trusted_site_baseline
from src.publish.manifest import build_manifest


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def test_ui_only_baseline_requires_exact_trusted_site_tree(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    site = root / "site"
    (site / "data" / "v1").mkdir(parents=True)
    (site / "data" / "v1" / "flights.json").write_text('{"rows":[]}', encoding="utf-8")
    (site / "publication_manifest.json").write_text('{"files":[]}', encoding="utf-8")
    _git(root, "init", "-b", "master")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", "site")
    _git(root, "commit", "-m", "approved published site")
    _git(root, "update-ref", "refs/remotes/origin/master", "HEAD")

    require_trusted_site_baseline(site, root=root)

    # Rebuilding a self-consistent manifest cannot bless modified public data:
    # the entire tracked site must still equal the trusted base.
    (site / "data" / "v1" / "flights.json").write_text('{"rows":[1]}', encoding="utf-8")
    (site / "publication_manifest.json").write_text('{"files":["rebuilt"]}', encoding="utf-8")
    with pytest.raises(PublicationRefused, match="uncommitted or untracked"):
        require_trusted_site_baseline(site, root=root)


def test_ui_only_baseline_refuses_a_site_committed_after_trusted_base(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    site = root / "site"
    site.mkdir(parents=True)
    (site / "index.html").write_text("approved", encoding="utf-8")
    _git(root, "init", "-b", "master")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    _git(root, "add", "site")
    _git(root, "commit", "-m", "trusted published site")
    _git(root, "update-ref", "refs/remotes/origin/master", "HEAD")
    trusted_commit = _trusted_site_commit(root)
    (site / "index.html").write_text("untrusted but committed", encoding="utf-8")
    _git(root, "add", "site")
    _git(root, "commit", "-m", "untrusted replacement")

    with pytest.raises(PublicationRefused, match="differs from the trusted"):
        require_trusted_site_baseline(site, root=root, trusted_commit=trusted_commit)

    _git(root, "update-ref", "refs/remotes/origin/master", "HEAD")
    with pytest.raises(PublicationRefused, match="changed during publication"):
        require_trusted_site_baseline(site, root=root, trusted_commit=trusted_commit)


def test_manifest_can_preserve_trusted_contract_set_for_ui_only_release(tmp_path: Path) -> None:
    trusted_contracts = {"publication_manifest.schema.json": "a" * 64}
    manifest = build_manifest(tmp_path, [], contracts=trusted_contracts, code_commit="commit")
    assert manifest["contracts"] == trusted_contracts
