import copy
import json
import pytest
from financial_fixtures import financial_release, put, resign
from src.publish import financial_scope as f


@pytest.fixture
def release(tmp_path):
    return financial_release(tmp_path)


def test_scope_requires_all_frozen_bytes_and_preserves_all_five_readings(release):
    r = release
    spec = f.anchor(r["repo"])
    frozen = f.preserved_files(r["site"], r["repo"], spec)
    assert f.EXECUTIVE not in frozen
    assert sum(p.startswith("data/v1/analysis/") for p in frozen) == 5
    assert "data/v1/news.json" in frozen and "editorial-publication.json" in frozen


@pytest.mark.parametrize(
    "path",
    [
        f.ANALYSIS,
        "data/v1/analysis/2026Q2.json",
        "data/v1/analysis/VOLARIS/2026Q2.json",
        "data/v1/analysis/VIVA_AEROBUS/2026Q2.json",
        "data/v1/analysis/INDUSTRY/2026Q2.json",
        "data/v1/news.json",
        "data/v1/flights/quarters.json",
        "data/v1/business_metrics.json",
        "data/v1/business_metrics.approval.json",
        "editorial-publication.json",
        "assets/old.js",
    ],
)
def test_self_rehashed_manifest_cannot_change_any_unrelated_file(release, path):
    r = release
    put(r["site"] / path, b"unauthorized")
    resign(r["site"])
    with pytest.raises(ValueError, match="preserved file"):
        f.preserved_files(r["site"], r["repo"], r["spec"])


@pytest.mark.parametrize(
    "mutation", ["old_record", "old_view", "peer", "default", "note", "remove_entity", "extra_quarter"]
)
def test_structural_guard_rejects_history_and_peers_independently_of_output_pin(release, mutation):
    r = release
    new = copy.deepcopy(r["projection"])
    if mutation == "old_record":
        new["records"][0]["passengers"] = 99
    if mutation == "old_view":
        new["views"]["2026Q2"]["old"] = False
    if mutation == "peer":
        new["entities"]["VOLARIS"]["records"][0]["passengers"] = 99
    if mutation == "default":
        new["metadata"]["default_period"] = "2026Q3"
    if mutation == "note":
        new["entities"]["AEROMEXICO"]["note"] = "changed old note"
    if mutation == "remove_entity":
        del new["entities"]["INDUSTRY"]
    if mutation == "extra_quarter":
        new["views"]["2026Q4"] = {}
    with pytest.raises((ValueError, KeyError)):
        f.preserved_executive(r["before"], new)


@pytest.mark.parametrize("path", ["data/v1/new.json", "new-app.html", "assets/unreviewed.js"])
def test_out_of_scope_additions_rejected(release, path):
    r = release
    put(r["site"] / path, b"new")
    resign(r["site"])
    with pytest.raises(ValueError, match="unrelated files"):
        f.preserved_files(r["site"], r["repo"], r["spec"])


def test_projection_pin_is_not_replaced_by_a_new_self_signed_inventory(release):
    r = release
    doc = copy.deepcopy(r["projection"])
    doc["records"][-1]["passengers"] = 999
    put(r["site"] / f.EXECUTIVE, f.encoded(doc))
    resign(r["site"])
    with pytest.raises(ValueError, match="reviewed output"):
        f.preserved_files(r["site"], r["repo"], r["spec"])


@pytest.mark.parametrize("part", ["contracts", "analysis_manifest"])
def test_historical_contracts_and_approval_ids_cannot_change(release, part):
    r = release
    path = r["site"] / "publication_manifest.json"
    m = json.loads(path.read_bytes())
    m[part] = {}
    put(path, f.encoded(m))
    with pytest.raises(ValueError, match="contracts or thesis"):
        f.preserved_files(r["site"], r["repo"], r["spec"])


def test_uncommitted_anchor_cannot_grant_authority(release):
    r = release
    spec = dict(r["spec"], executive_sha256="f" * 64)
    put(r["repo"] / f.ANCHOR, f.encoded(spec))
    with pytest.raises(ValueError, match="committed"):
        f.anchor(r["repo"])


@pytest.mark.parametrize(
    "field", ["baseline_commit", "manifest_sha256", "files_verified", "origin", "deployment_commit"]
)
def test_forged_witness_rejected(release, field):
    r = release
    proof = copy.deepcopy(r["proof"])
    proof["remote_witness"][field] = "forged"
    put(r["site"] / f.PROOF, f.encoded(proof))
    with pytest.raises((ValueError, f.subprocess.CalledProcessError)):
        f.preserved_files(r["site"], r["repo"], r["spec"])


def test_frontend_pin_and_symlink_rejected(release):
    r = release
    put(r["site"] / "index.html", b"changed")
    with pytest.raises(ValueError, match="frontend"):
        f.preserved_files(r["site"], r["repo"], r["spec"])
    put(r["site"] / "index.html", b"new frontend")
    path = r["site"] / "assets/old.js"
    path.unlink()
    path.symlink_to(r["repo"] / "site/assets/old.js")
    with pytest.raises(ValueError, match="symlink"):
        f.preserved_files(r["site"], r["repo"], r["spec"])
