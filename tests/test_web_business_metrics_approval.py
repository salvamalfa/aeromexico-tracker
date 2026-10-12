from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from src.conversational_analytics.data.snapshot import Snapshot, SnapshotError
from src.conversational_analytics.tools.business_metrics import (
    deterministic_query,
    get_business_metric_definition,
)
from src.publish import manifest as manifest_mod
from src.publish.verify import verify_site
from src.web_export.business_metrics import BusinessMetricsApprovalError, build_approved_payload
from src.web_export.writer import write_json

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SITE = ROOT / "tests/fixtures/chat/site"


def _receipt(definitions: Path, proposal: Path, metrics: list[str] | None = None) -> dict:
    return {
        "schema_version": "business_metrics_approval_v1",
        "status": "owner_approved",
        "receipt_id": "test-fixture-only",
        "approved_at": "2026-01-01T00:00:00Z",
        "approved_metric_ids": metrics or ["total_revenue"],
        "definitions_sha256": hashlib.sha256(definitions.read_bytes()).hexdigest(),
        "proposal_sha256": hashlib.sha256(proposal.read_bytes()).hexdigest(),
    }


def _approved_snapshot(tmp_path: Path) -> Snapshot:
    project = tmp_path / "project"
    site = project / "site"
    project.mkdir()
    shutil.copytree(FIXTURE_SITE, site)
    shutil.copytree(ROOT / "contracts/web", project / "contracts/web")
    shutil.copytree(ROOT / "contracts/chat", project / "contracts/chat")
    shutil.copytree(ROOT / "config/chat", project / "config/chat")
    (project / "docs/chat").mkdir(parents=True)
    shutil.copy2(
        ROOT / "docs/chat/f23-metrics-candidate-dry-run.json",
        project / "docs/chat/f23-metrics-candidate-dry-run.json",
    )
    proposal = project / "docs/chat/f23-metrics-candidate-dry-run.json"
    definitions = project / "config/chat/metrics-candidates.json"
    receipt = _receipt(definitions, proposal)
    receipt_path = project / "config/chat/business-metrics-approval-receipt.json"
    write_json(receipt_path, receipt)
    payload, _ = build_approved_payload(proposal, definitions, receipt_path)
    write_json(site / "data/v1/business_metrics.json", payload)
    write_json(site / "data/v1/business_metrics.approval.json", receipt)

    manifest_path = site / "publication_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["contracts"] = manifest_mod.contract_hashes(project / "contracts/web")
    manifest["files"] = manifest_mod.file_entries(site)
    manifest_mod.write_manifest(site, manifest)
    return Snapshot(site)


def test_receipt_must_match_exact_definition_and_proposal_bytes(tmp_path: Path) -> None:
    proposal = ROOT / "docs/chat/f23-metrics-candidate-dry-run.json"
    definitions = ROOT / "config/chat/metrics-candidates.json"
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_receipt(definitions, proposal)), encoding="utf-8")

    payload, receipt = build_approved_payload(proposal, definitions, receipt_path)
    assert payload["metadata"]["metric_ids"] == ["total_revenue"]
    assert payload["rows"]
    assert receipt["receipt_id"] == "test-fixture-only"
    assert all(row["value_kind"] == "owner_approved_gold_reported" for row in payload["rows"])

    stale_proposal = tmp_path / "stale-proposal.json"
    stale_proposal.write_bytes(proposal.read_bytes() + b" ")
    with pytest.raises(BusinessMetricsApprovalError, match="exact candidate proposal"):
        build_approved_payload(stale_proposal, definitions, receipt_path)

    stale_definitions = tmp_path / "stale-definitions.json"
    stale_definitions.write_bytes(definitions.read_bytes() + b" ")
    with pytest.raises(BusinessMetricsApprovalError, match="current metric definitions"):
        build_approved_payload(proposal, stale_definitions, receipt_path)


def test_approved_snapshot_query_sums_full_year_and_keeps_source_currency_and_units(tmp_path: Path) -> None:
    snapshot = _approved_snapshot(tmp_path)
    q1 = deterministic_query(snapshot, "total_revenue", "AEROMEXICO", "2025Q1")
    h1 = deterministic_query(snapshot, "total_revenue", "AEROMEXICO", "2025H1")
    year = deterministic_query(snapshot, "total_revenue", "AEROMEXICO", "2025")
    definition = get_business_metric_definition("total_revenue", snapshot)

    assert q1["approval_gate"] == "open"
    assert q1["value"] is not None
    assert q1["currency_as_reported"] == ["USD"]
    assert q1["quarter_sources"][0]["unit_as_reported"] == "USD millions"
    assert q1["quarter_sources"][0]["fx_rate_used"] == 1.0
    mxn = deterministic_query(snapshot, "total_revenue", "VOLARIS", "2020Q3")
    assert mxn["currency_as_reported"] == ["MXN"]
    assert mxn["quarter_sources"][0]["fx_rate_used"] > 0
    assert mxn["quarter_sources"][0]["fx_rate_type"]
    assert mxn["source_references"][0]["url"].startswith("https://www.bmv.com.mx/docs-pub/ifrsxbrl/")
    assert "#" not in mxn["source_references"][0]["url"]
    assert mxn["source_references"][0]["citation_url"].endswith("#member=ifrsxbrl_1135999_2021-03_1.json")
    assert mxn["source_references"][0]["member"] in mxn["source_references"][0]["label"]
    assert definition["approval_gate"] == "open"
    assert definition["production_enabled"] is True
    assert h1["value"] == pytest.approx(
        q1["value"] + deterministic_query(snapshot, "total_revenue", "AEROMEXICO", "2025Q2")["value"]
    )
    assert year["availability"] == "available"
    assert year["value"] == pytest.approx(
        sum(
            deterministic_query(snapshot, "total_revenue", "AEROMEXICO", f"2025Q{i}")["value"]
            for i in range(1, 5)
        )
    )

    q2_2026 = deterministic_query(snapshot, "total_revenue", "AEROMEXICO", "2026Q2")
    assert q2_2026["any_preliminary"] is True
    capture = q2_2026["source_references"][0]
    assert capture["captured_bytes"] == 230275
    assert capture["current_identity_check"]["current_bytes"] == 230386


def test_snapshot_rejects_receipt_or_payload_not_hash_bound_to_proposal(tmp_path: Path) -> None:
    snapshot = _approved_snapshot(tmp_path)
    approval_file = snapshot.root / "data/v1/business_metrics.approval.json"
    receipt = json.loads(approval_file.read_text(encoding="utf-8"))
    receipt["proposal_sha256"] = "0" * 64
    write_json(approval_file, receipt)
    manifest = dict(snapshot.manifest)
    manifest["files"] = manifest_mod.file_entries(snapshot.root)
    manifest_mod.write_manifest(snapshot.root, manifest)

    with pytest.raises(SnapshotError, match="business metrics approval could not be revalidated"):
        Snapshot(snapshot.root)


def _resign_site(site: Path) -> None:
    manifest = dict(json.loads((site / "publication_manifest.json").read_text(encoding="utf-8")))
    manifest["files"] = manifest_mod.file_entries(site)
    manifest_mod.write_manifest(site, manifest)


def test_publish_verify_requires_the_business_metrics_receipt_pair(tmp_path: Path) -> None:
    snapshot = _approved_snapshot(tmp_path)
    (snapshot.root / "data/v1/business_metrics.approval.json").unlink()
    _resign_site(snapshot.root)

    problems = verify_site(snapshot.root)

    assert any("payload and approval receipt must be published together" in problem for problem in problems)


def test_publish_verify_revalidates_business_metrics_payload_and_receipt_pins(tmp_path: Path) -> None:
    snapshot = _approved_snapshot(tmp_path)
    receipt_path = snapshot.root / "data/v1/business_metrics.approval.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt["definitions_sha256"] = "0" * 64
    write_json(receipt_path, receipt)
    _resign_site(snapshot.root)

    problems = verify_site(snapshot.root)

    assert any("business metrics approval could not be revalidated" in problem for problem in problems)


def test_publish_verify_rejects_rebuilt_manifest_with_tampered_business_metrics(tmp_path: Path) -> None:
    snapshot = _approved_snapshot(tmp_path)
    payload_path = snapshot.root / "data/v1/business_metrics.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    next(row for row in payload["rows"] if row["value"] is not None)["value"] += 1
    write_json(payload_path, payload)
    _resign_site(snapshot.root)

    problems = verify_site(snapshot.root)

    assert any("do not match the current approved proposal and receipt" in problem for problem in problems)


def test_year_is_incomplete_when_source_has_only_two_quarters(tmp_path: Path) -> None:
    snapshot = _approved_snapshot(tmp_path)
    result = deterministic_query(snapshot, "total_revenue", "AEROMEXICO", "2026")
    assert result["availability"] == "incomplete"
    assert result["value"] is None
    assert result["missing_periods"] == ["2026Q3", "2026Q4"]
