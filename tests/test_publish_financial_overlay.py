from __future__ import annotations

import json
import shutil
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.publish import financial_overlay
from src.publish import manifest as manifest_mod
from src.publish.gate import PublicationRefused
from src.web_export.business_metrics import BusinessMetricsApprovalError


def _baseline(site: Path) -> tuple[dict[str, bytes], dict[str, str]]:
    data = site / "data/v1"
    data.mkdir(parents=True)
    (site / "index.html").write_text("baseline", encoding="utf-8")
    (data / "analysis").mkdir()
    (data / "analysis/2026Q2.json").write_text("{}", encoding="utf-8")
    for number in range(111):
        (data / f"existing-{number:03d}.json").write_text(
            json.dumps({"baseline": number}), encoding="utf-8"
        )
    files = {
        path.relative_to(site).as_posix(): path.read_bytes()
        for path in site.rglob("*")
        if path.is_file()
    }
    contracts = manifest_mod.contract_hashes()
    contracts = {
        key: value for key, value in contracts.items()
        if key not in {"business_metrics.schema.json", "business_metrics_approval.schema.json"}
    }
    analysis = [{
        "period_id": "2026Q2",
        "version": "approved-version",
        "content_hash": "content-hash",
        "evidence_fingerprint": "evidence-fingerprint",
        "approval_event": "approval-event",
        "audit_hash": "audit-hash",
    }]
    manifest = manifest_mod.build_manifest(
        site, analysis, code_commit="trusted", contracts=contracts,
        generated_at="2026-10-12T00:00:00Z",
    )
    manifest_mod.write_manifest(site, manifest)
    return files, contracts


def _wire_test_gate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, reject_receipt: bool = False):
    from src.publish import gate

    site = tmp_path / "site"
    baseline_files, baseline_contracts = _baseline(site)
    web_data = tmp_path / "web/public/data/v1"
    monkeypatch.setattr(financial_overlay, "PATHS", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(gate, "PATHS", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(gate, "WEB_DATA_V1", web_data)
    monkeypatch.setattr(gate, "WEB_DIR", tmp_path / "web")
    monkeypatch.setattr(manifest_mod, "refuse_if_build_inputs_dirty", lambda: None)
    record = {"draft": {"period_id": "2026Q2"}, "version": "approved-version"}
    authorized = {
        "period_id": "2026Q2", "version": "approved-version",
        "content_hash": "content-hash", "evidence_fingerprint": "evidence-fingerprint",
        "approval_event": "approval-event", "audit_hash": "audit-hash",
    }
    entry = (record, authorized, None, None)
    monkeypatch.setattr(gate, "load_records", lambda paths: [record])
    monkeypatch.setattr(gate, "verify_records", lambda records, root: [entry])
    monkeypatch.setattr(gate, "_trusted_site_commit", lambda root: "trusted")
    trust_checks = []

    def require_baseline(path, *, root, trusted_commit):
        trust_checks.append(trusted_commit)
        if path != site or trusted_commit != "trusted":
            raise PublicationRefused("unexpected baseline")
        for relative, content in baseline_files.items():
            if (site / relative).read_bytes() != content:
                raise PublicationRefused("trusted baseline changed")

    monkeypatch.setattr(gate, "require_trusted_site_baseline", require_baseline)
    monkeypatch.setattr(financial_overlay, "verify_site", lambda path: [])
    if reject_receipt:
        def reject_export(*args, **kwargs):
            raise BusinessMetricsApprovalError("external receipt pin missing")
        monkeypatch.setattr(financial_overlay, "export_approved_business_metrics", reject_export)
    else:
        def export_pair(proposal, definitions, receipt, out):
            payload = out / "business_metrics.json"
            approval = out / "business_metrics.approval.json"
            payload.write_text('{"approved":true}', encoding="utf-8")
            approval.write_text('{"receipt":"pinned"}', encoding="utf-8")
            return [payload, approval]
        monkeypatch.setattr(financial_overlay, "export_approved_business_metrics", export_pair)

    def build_web(web_dir):
        dist = tmp_path / "dist"
        shutil.rmtree(dist, ignore_errors=True)
        shutil.copytree(web_data, dist / "data/v1")
        dist.mkdir(exist_ok=True)
        (dist / "index.html").write_text("built", encoding="utf-8")
        return dist
    monkeypatch.setattr(gate, "build_web", build_web)
    monkeypatch.setattr(
        gate,
        "flow",
        SimpleNamespace(ROOT=tmp_path / "analysis_runs/lifecycle", writer=lambda root: nullcontext()),
    )
    rechecks = []
    monkeypatch.setattr(gate, "_verify_under_lock", lambda records, root: (rechecks.append(True) or [entry]))
    monkeypatch.setattr(manifest_mod, "current_commit", lambda root=tmp_path: "source-commit")

    def assemble(dist, analysis_manifest, out, *, contracts, validate_candidate=None):
        assert contracts == manifest_mod.contract_hashes()
        candidate = tmp_path / "candidate"
        shutil.rmtree(candidate, ignore_errors=True)
        shutil.copytree(dist, candidate)
        manifest = manifest_mod.build_manifest(
            candidate, analysis_manifest, code_commit="source-commit", contracts=contracts,
            generated_at="2026-10-12T00:00:00Z",
        )
        manifest_mod.write_manifest(candidate, manifest)
        if validate_candidate:
            validate_candidate(candidate)
        shutil.rmtree(out)
        shutil.copytree(candidate, out)
        return manifest
    monkeypatch.setattr(gate, "assemble_site", assemble)
    monkeypatch.setattr(gate, "write_receipt", lambda manifest, authorized, out: {"ok": True})
    return site, baseline_files, baseline_contracts, trust_checks, rechecks


def test_financial_overlay_preserves_112_baseline_files_and_rechecks_approval(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    site, previous_files, previous_contracts, trust_checks, rechecks = _wire_test_gate(monkeypatch, tmp_path)

    result = financial_overlay.publish_business_metrics_only([Path("approved.json")], site)

    manifest = manifest_mod.load_manifest(site)
    data_files = [item for item in manifest["files"] if item["path"].startswith("data/v1/")]
    assert len(data_files) == 114
    assert set(manifest["contracts"]) == set(manifest_mod.contract_hashes())
    assert set(previous_contracts) <= set(manifest["contracts"])
    for relative, content in previous_files.items():
        if relative.startswith("data/v1/"):
            assert (site / relative).read_bytes() == content
    assert (site / "data/v1/business_metrics.json").is_file()
    assert (site / "data/v1/business_metrics.approval.json").is_file()
    assert trust_checks == ["trusted", "trusted"]
    assert rechecks == [True]
    assert result["receipt"] == {"ok": True}


def test_financial_overlay_refuses_missing_external_receipt_pin_before_build(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    site, previous_files, _, _, _ = _wire_test_gate(monkeypatch, tmp_path, reject_receipt=True)

    with pytest.raises(PublicationRefused, match="external receipt pin missing"):
        financial_overlay.publish_business_metrics_only([Path("approved.json")], site)

    for relative, content in previous_files.items():
        assert (site / relative).read_bytes() == content
    assert not (site / "data/v1/business_metrics.json").exists()


def test_financial_overlay_refuses_a_tampered_baseline_before_export(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    site, _, _, _, _ = _wire_test_gate(monkeypatch, tmp_path)
    (site / "data/v1/existing-000.json").write_text('{"tampered":true}', encoding="utf-8")

    with pytest.raises(PublicationRefused, match="trusted baseline changed"):
        financial_overlay.publish_business_metrics_only([Path("approved.json")], site)

    assert not (site / "data/v1/business_metrics.json").exists()
