"""Negative coverage for the hardened ``verify_site()`` checks (package R1,
task A2): each mutation below must turn the real, committed ``site/`` (copied
to ``tmp_path`` so nothing here ever writes to the real tree) from passing
into failing. See ``src/publish/verify.py`` and
``docs/arquitectura/auditoria-arquitectura-20260926.md`` §4-5.

No private data needed: this only reads the versioned ``site/`` and
``contracts/web/``, exactly like ``src.publish.verify`` itself.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.publish import manifest as manifest_mod
from src.publish.verify import verify_site

SITE_DIR = Path(__file__).resolve().parent.parent / "site"


def _copy_site(tmp_path: Path) -> Path:
    if not SITE_DIR.is_dir():
        pytest.skip(f"{SITE_DIR} does not exist in this checkout")
    dest = tmp_path / "site"
    shutil.copytree(SITE_DIR, dest)
    return dest


def _load_manifest(site_dir: Path) -> dict:
    return json.loads((site_dir / manifest_mod.MANIFEST_NAME).read_text(encoding="utf-8"))


def _write_manifest(site_dir: Path, manifest: dict) -> None:
    (site_dir / manifest_mod.MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def test_unmodified_copy_passes(tmp_path: Path) -> None:
    site_dir = _copy_site(tmp_path)
    assert verify_site(site_dir) == []


def test_zeroed_contract_hashes_are_rejected(tmp_path: Path) -> None:
    site_dir = _copy_site(tmp_path)
    manifest = _load_manifest(site_dir)
    manifest["contracts"] = {name: "0" * 64 for name in manifest["contracts"]}
    _write_manifest(site_dir, manifest)

    problems = verify_site(site_dir)
    assert problems
    assert any("contracts[" in p and "hashes to" in p for p in problems), problems


def test_empty_files_and_analysis_manifest_without_index_html_is_rejected(tmp_path: Path) -> None:
    site_dir = _copy_site(tmp_path)
    manifest = _load_manifest(site_dir)
    manifest["files"] = []
    manifest["analysis_manifest"] = []
    _write_manifest(site_dir, manifest)

    problems = verify_site(site_dir)
    assert problems
    assert any("files' is empty" in p for p in problems), problems
    assert any("analysis_manifest' is empty" in p for p in problems), problems


def test_unexpected_data_file_declared_in_the_manifest_is_rejected(tmp_path: Path) -> None:
    site_dir = _copy_site(tmp_path)
    manifest = _load_manifest(site_dir)

    unexpected_rel = "data/v1/unexpected.json"
    unexpected_path = site_dir / unexpected_rel
    unexpected_path.parent.mkdir(parents=True, exist_ok=True)
    content = b'{"api_key":"x"}\n'
    unexpected_path.write_bytes(content)

    manifest["files"].append({
        "path": unexpected_rel,
        "sha256": manifest_mod.sha256_file(unexpected_path),
        "bytes": len(content),
    })
    _write_manifest(site_dir, manifest)

    problems = verify_site(site_dir)
    assert problems
    assert any(unexpected_rel in p and "not one of the data/v1 files" in p for p in problems), problems


def test_content_hash_unrelated_to_the_payload_is_rejected(tmp_path: Path) -> None:
    site_dir = _copy_site(tmp_path)
    manifest = _load_manifest(site_dir)
    assert manifest["analysis_manifest"], "fixture site has no analysis_manifest entry to tamper with"
    manifest["analysis_manifest"][0]["content_hash"] = "f" * 64
    _write_manifest(site_dir, manifest)

    problems = verify_site(site_dir)
    assert problems
    assert any("content_hash" in p and "manifest says" in p for p in problems), problems


def test_duplicate_file_path_is_rejected(tmp_path: Path) -> None:
    site_dir = _copy_site(tmp_path)
    manifest = _load_manifest(site_dir)
    manifest["files"].append(dict(manifest["files"][0]))
    _write_manifest(site_dir, manifest)

    problems = verify_site(site_dir)
    assert problems
    assert any("more than once" in p and manifest["files"][0]["path"] in p for p in problems), problems


def test_duplicate_analysis_manifest_period_id_is_rejected(tmp_path: Path) -> None:
    site_dir = _copy_site(tmp_path)
    manifest = _load_manifest(site_dir)
    assert manifest["analysis_manifest"], "fixture site has no analysis_manifest entry to duplicate"
    manifest["analysis_manifest"].append(dict(manifest["analysis_manifest"][0]))
    _write_manifest(site_dir, manifest)

    problems = verify_site(site_dir)
    assert problems
    period_id = manifest["analysis_manifest"][0]["period_id"]
    assert any("more than once" in p and period_id in p for p in problems), problems
