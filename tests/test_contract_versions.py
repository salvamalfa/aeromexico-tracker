"""Strict historical schema resolution, without changing signed site artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from src.conversational_analytics.data.snapshot import Snapshot, SnapshotError
from src.publish import manifest as manifest_mod
from src.publish.verify import verify_site
from src.web_export.contract_versions import ARCHIVED_CONTRACTS, resolve_contract

ROOT = Path(__file__).resolve().parents[1]
OLD_SHA = next(iter(ARCHIVED_CONTRACTS["flights.schema.json"]))


@pytest.mark.parametrize("name", manifest_mod.CONTRACT_FILES)
def test_current_contract_matches_its_exact_hash(name: str) -> None:
    contracts = ROOT / "contracts/web"
    expected = hashlib.sha256((contracts / name).read_bytes()).hexdigest()
    assert resolve_contract(contracts, name, expected) == contracts / name


@pytest.fixture
def isolated_site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    contracts = tmp_path / "contracts/web"
    shutil.copytree(ROOT / "contracts/web", contracts)
    (tmp_path / "config/chat").mkdir(parents=True)
    (tmp_path / "contracts/chat").mkdir()
    shutil.copyfile(
        ROOT / "contracts/chat/semantic.schema.json", tmp_path / "contracts/chat/semantic.schema.json"
    )
    site = tmp_path / "site"
    shutil.copytree(ROOT / "tests/fixtures/site/valid", site)
    monkeypatch.setattr(manifest_mod, "CONTRACTS_DIR", contracts)
    return site, contracts


def _set_contract(site: Path, digest: str) -> None:
    manifest = manifest_mod.load_manifest(site)
    manifest["contracts"]["flights.schema.json"] = digest
    manifest_mod.write_manifest(site, manifest)


def _with_component(site: Path) -> str:
    path = next((site / "data/v1/flights/international").glob("*.json"))
    payload = json.loads(path.read_bytes())
    assert payload["routes"]
    payload["routes"][0]["flight_components"] = []
    path.write_text(json.dumps(payload), encoding="utf-8")
    manifest = manifest_mod.load_manifest(site)
    manifest["files"] = manifest_mod.file_entries(site)
    manifest_mod.write_manifest(site, manifest)
    return path.relative_to(site).as_posix()


@pytest.mark.parametrize("historical", [False, True])
def test_both_readers_validate_the_exact_manifest_version(isolated_site, historical: bool) -> None:
    site, contracts = isolated_site
    digest = OLD_SHA if historical else manifest_mod.sha256_file(contracts / "flights.schema.json")
    _set_contract(site, digest)
    if not historical:
        _with_component(site)
    assert verify_site(site) == []
    assert Snapshot(site).payload("data/v1/flights/quarters.json")


def test_new_component_cannot_be_validated_under_old_manifest(isolated_site) -> None:
    site, _ = isolated_site
    _set_contract(site, OLD_SHA)
    rel = _with_component(site)
    assert any(rel in problem and "flight_components" in problem for problem in verify_site(site))
    with pytest.raises(SnapshotError, match="flight_components"):
        Snapshot(site)


@pytest.mark.parametrize("historical", [False, True])
def test_tampered_selected_contract_is_rejected_by_both_readers(isolated_site, historical: bool) -> None:
    site, contracts = isolated_site
    digest = OLD_SHA if historical else manifest_mod.sha256_file(contracts / "flights.schema.json")
    _set_contract(site, digest)
    selected = resolve_contract(contracts, "flights.schema.json", digest)
    selected.write_bytes(selected.read_bytes() + b" ")
    assert any("contracts['flights.schema.json']" in problem for problem in verify_site(site))
    with pytest.raises(SnapshotError, match="Hash de contrato"):
        Snapshot(site)


def test_unselected_current_version_is_not_substituted_for_archive(isolated_site) -> None:
    site, contracts = isolated_site
    _set_contract(site, OLD_SHA)
    (contracts / "flights.schema.json").write_bytes(b"{}")
    assert verify_site(site) == []
    Snapshot(site)


def test_unknown_digest_cannot_register_itself_via_an_archive(isolated_site) -> None:
    site, contracts = isolated_site
    unknown = b"{}"
    digest = hashlib.sha256(unknown).hexdigest()
    invented = contracts / "versions" / digest / "flights.schema.json"
    invented.parent.mkdir()
    invented.write_bytes(unknown)
    _set_contract(site, digest)
    assert any("exact version unavailable" in problem for problem in verify_site(site))
    with pytest.raises(SnapshotError, match="Hash de contrato"):
        Snapshot(site)


@pytest.mark.parametrize(
    "name", ["../flights.schema.json", "/flights.schema.json", r"..\flights.schema.json"]
)
def test_contract_path_traversal_is_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="Unsafe contract name"):
        resolve_contract(ROOT / "contracts/web", name, OLD_SHA)


@pytest.mark.parametrize(
    "name", ["privacy.yaml", "business_metrics_approval.schema.json", "publication_manifest.schema.json"]
)
def test_privacy_and_approval_contracts_do_not_gain_archives(isolated_site, name: str) -> None:
    _, contracts = isolated_site
    current = contracts / name
    raw = current.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    invented = contracts / "versions" / digest / name
    invented.parent.mkdir()
    invented.write_bytes(raw)
    current.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="exact version unavailable"):
        resolve_contract(contracts, name, digest)


@pytest.mark.parametrize("digest", ["../outside", "A" * 64, "0" * 63, "", None])
def test_invalid_digest_path_is_rejected(digest) -> None:
    with pytest.raises(ValueError, match="Invalid contract SHA"):
        resolve_contract(ROOT / "contracts/web", "flights.schema.json", digest)


@pytest.mark.parametrize("link_part", ["versions", "digest", "file", "current"])
def test_symlink_contract_paths_are_rejected(isolated_site, tmp_path: Path, link_part: str) -> None:
    _, contracts = isolated_site
    archive = contracts / "versions" / OLD_SHA / "flights.schema.json"
    selected = {
        "versions": archive.parent.parent,
        "digest": archive.parent,
        "file": archive,
        "current": contracts / "flights.schema.json",
    }[link_part]
    outside = tmp_path / "outside"
    if selected.is_dir():
        shutil.move(selected, outside)
    else:
        selected.rename(outside)
    selected.symlink_to(outside, target_is_directory=outside.is_dir())
    digest = manifest_mod.sha256_file(outside) if link_part == "current" else OLD_SHA
    with pytest.raises(ValueError, match="Symlink contract path"):
        resolve_contract(contracts, "flights.schema.json", digest)


def test_future_manifest_still_uses_current_hashes(isolated_site) -> None:
    site, contracts = isolated_site
    manifest = manifest_mod.build_manifest(site, [], code_commit="0" * 40, contracts_dir=contracts)
    assert manifest["contracts"]["flights.schema.json"] == manifest_mod.sha256_file(
        contracts / "flights.schema.json"
    )
    assert manifest["contracts"]["flights.schema.json"] != OLD_SHA
