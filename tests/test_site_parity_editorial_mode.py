"""Public regressions for selecting financial parity by publication mode."""

import importlib.util
import json
from pathlib import Path

import pytest

from src.publish import editorial


def parity_module():
    spec = importlib.util.spec_from_file_location(
        "editorial_parity_mode", Path(__file__).with_name("test_site_parity.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def editorial_parity_module():
    spec = importlib.util.spec_from_file_location(
        "editorial_source_availability", Path(__file__).with_name("test_editorial_site_parity.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("valid", [True, False])
def test_editorial_financial_parity_requires_verified_baseline_not_quarterly_reading(
    tmp_path, monkeypatch, valid
):
    module = parity_module()
    module.SITE_DIR = tmp_path / "site"
    module.SITE_DIR.mkdir()
    (module.SITE_DIR / editorial.PROOF).write_text("{}")
    baseline = {"records": [{"period_id": "2026Q2"}], "views": {"2026Q2": {}}}
    monkeypatch.setattr(
        editorial, "verify_editorial", lambda site, repo: [] if valid else ["Historical bytes changed"]
    )
    monkeypatch.setattr(editorial, "anchor", lambda repo: {"baseline_commit": "a" * 40})
    calls = []

    def git_read(args, **kwargs):
        calls.append(args)
        assert args == ["git", "show", "a" * 40 + ":site/data/v1/executive.json"]
        return json.dumps(baseline).encode()

    monkeypatch.setattr(module.subprocess, "check_output", git_read)
    monkeypatch.setattr(
        module,
        "_quarterly_projection",
        lambda *args: pytest.fail("Editorial mode cannot project financial Q3"),
    )
    if valid:
        assert module.published_executive.__wrapped__(baseline) == baseline
        assert len(calls) == 1
        with pytest.raises(AssertionError):
            module.published_executive.__wrapped__({"records": [{"period_id": "2026Q3"}]})
    else:
        with pytest.raises(AssertionError):
            module.published_executive.__wrapped__(baseline)
        assert calls == []


@pytest.mark.parametrize("case", ["normal", "invalid", "changed", "partial", "quarterly"])
def test_reading_only_financial_parity_survives_ui_transition(tmp_path, monkeypatch, case):
    from src.publish import records

    module = parity_module()
    module.SITE_DIR = tmp_path / "site"
    target = module.SITE_DIR / "data/v1/executive.json"
    target.parent.mkdir(parents=True)
    baseline = {"records": [{"period_id": "2026Q2"}], "views": {"2026Q2": {}}}
    published = json.loads(json.dumps(baseline))
    if case in {"partial", "quarterly"}:
        published["views"]["2026Q3"] = {}
    if case == "quarterly":
        published["records"].append({"period_id": "2026Q3"})
    if case == "changed":
        published["records"][0]["unauthorized"] = True
    target.write_bytes(json.dumps(published).encode())
    entry = {"period_id": "2026Q3", "version": "reading"}
    monkeypatch.setattr(module.manifest_mod, "load_manifest", lambda site: {"analysis_manifest": [entry]})
    verification = []

    def verify(site):
        verification.append(site)
        return ["invalid publication"] if case == "invalid" else []

    monkeypatch.setattr(module, "verify_site", verify)
    monkeypatch.setattr(editorial, "anchor", lambda repo: {"baseline_commit": "a" * 40})
    monkeypatch.setattr(module.subprocess, "check_output", lambda *a, **k: json.dumps(baseline).encode())
    replayed = []

    def replay():
        replayed.append(True)
        return {
            "authorized": [entry],
            "cohorts": [{"analysis_manifest": [entry], "implementation_commit": "b" * 40}],
        }

    monkeypatch.setattr(module, "_replay_published_cohorts", replay)
    monkeypatch.setattr(records, "_analysis_manifest_entry", lambda value: value)
    monkeypatch.setattr(module, "_baseline_json", lambda path: baseline)

    def project(*args):
        assert case == "quarterly", "Reading alone must not project financial Q3"
        return published

    monkeypatch.setattr(module, "_quarterly_projection", project)
    record = tmp_path / "analysis_runs/drafts/2026Q3/reading.json"
    record.parent.mkdir(parents=True)
    record.write_text(
        json.dumps({"draft": {"source_profile": "quarterly_release_v1", "package_id": "source"}})
    )
    if case in {"invalid", "changed", "partial"}:
        with pytest.raises(AssertionError):
            module.published_executive.__wrapped__(baseline)
    else:
        assert module.published_executive.__wrapped__(baseline) == (
            published if case == "quarterly" else baseline
        )
    assert bool(replayed) == (case == "quarterly")
    assert bool(verification) == (case not in {"partial", "quarterly"})


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("missing", ["candidate", "source_record"])
def test_editorial_evidence_unavailability_fails_in_strict_mode_without_a_warehouse(
    tmp_path, strict, missing
):
    from types import SimpleNamespace

    module = editorial_parity_module()
    module.ROOT = tmp_path
    module.SITE = tmp_path / "site"
    request = SimpleNamespace(config=SimpleNamespace(getoption=lambda name: strict))
    expected = pytest.fail.Exception if strict else pytest.skip.Exception
    with pytest.raises(expected):
        if missing == "candidate":
            module.editorial_site.__wrapped__(request)
        else:
            module._required_source_record({"version": "a" * 64}, request)
    assert not (tmp_path / "data/warehouse.duckdb").exists()


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("damage", [None, "data", "missing_receipt", "pending_reading", "unapproved_text"])
def test_editorial_fixture_recognizes_only_a_verified_later_normal_publication(tmp_path, strict, damage):
    import hashlib
    import shutil
    from types import SimpleNamespace

    module = editorial_parity_module()
    root = Path(__file__).resolve().parents[1]
    site = tmp_path / "site"
    shutil.copytree(root / "tests/fixtures/site/valid", site)
    manifest_path = site / "publication_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    entry = dict(editorial.anchor(root)["analysis_entry"])
    payload = json.loads((root / "site" / editorial.ANALYSIS).read_bytes())
    if damage == "pending_reading":
        entry["version"] = "pending"
        payload["version"] = "pending"
    new_path = site / editorial.ANALYSIS
    if damage == "unapproved_text":
        payload["thesis"] = "UNAPPROVED but schema-valid narrative"
    if damage in {"unapproved_text", "pending_reading"}:
        new_path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        new_path.write_bytes((root / "site" / editorial.ANALYSIS).read_bytes())
    manifest["analysis_manifest"].append(entry)
    manifest["contracts"][editorial.manifests.EDITORIAL_ANALYSIS_CONTRACT] = hashlib.sha256(
        (root / "contracts/web" / editorial.manifests.EDITORIAL_ANALYSIS_CONTRACT).read_bytes()
    ).hexdigest()
    manifest["files"].append(
        {
            "path": editorial.ANALYSIS,
            "bytes": new_path.stat().st_size,
            "sha256": hashlib.sha256(new_path.read_bytes()).hexdigest(),
        }
    )
    if damage == "missing_receipt":
        manifest["files"].append(
            {"path": editorial.PROOF, "bytes": 2, "sha256": hashlib.sha256(b"{}").hexdigest()}
        )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    if damage == "data":
        (site / "data/v1/executive.json").write_text("{}", encoding="utf-8")
    module.ROOT = root
    module.SITE = site
    request = SimpleNamespace(config=SimpleNamespace(getoption=lambda name: strict))
    if damage is None:
        assert module.editorial_site.__wrapped__(request)["analysis_entry"] == entry
        with pytest.raises(pytest.skip.Exception):
            module.test_editorial_site_preserves_every_historical_file({})
        # Later normal publications still require the complete new-source replay.
        module.ROOT = tmp_path
        expected = pytest.fail.Exception if strict else pytest.skip.Exception
        with pytest.raises(expected):
            module._required_source_record(entry, request)
    else:
        expected = (
            (pytest.fail.Exception if strict else pytest.skip.Exception)
            if damage == "pending_reading"
            else AssertionError
        )
        with pytest.raises(expected):
            module.editorial_site.__wrapped__(request)
