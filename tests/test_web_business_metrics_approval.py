from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.conversational_analytics.data.snapshot import Snapshot, SnapshotError
from src.conversational_analytics.presentation import make_displays
from src.conversational_analytics.tools.business_metrics import (
    deterministic_query,
    get_business_metric_definition,
)
from src.conversational_analytics.tools.registry import ToolRegistry
from src.publish import manifest as manifest_mod
from src.publish.verify import verify_site
from src.web_export.business_metrics import BusinessMetricsApprovalError, build_approved_payload
from src.web_export.business_metrics_approval import (
    APPROVAL_RECEIPT_SHA256_ENV,
    canonical_receipt_sha256,
)
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
        "owner_id": "salvamalfa",
        "decision_reference": "test-fixture-owner-decision",
    }


@pytest.fixture(autouse=True)
def _pin_synthetic_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    definitions = ROOT / "config/chat/metrics-candidates.json"
    proposal = ROOT / "config/chat/business-metrics-proposal.json"
    receipt = _receipt(definitions, proposal)
    monkeypatch.setenv(APPROVAL_RECEIPT_SHA256_ENV, canonical_receipt_sha256(receipt))


def _approved_snapshot(tmp_path: Path) -> Snapshot:
    project = tmp_path / "project"
    site = project / "site"
    project.mkdir()
    shutil.copytree(FIXTURE_SITE, site)
    shutil.copytree(ROOT / "contracts/web", project / "contracts/web")
    shutil.copytree(ROOT / "contracts/chat", project / "contracts/chat")
    shutil.copytree(ROOT / "config/chat", project / "config/chat")
    proposal = project / "config/chat/business-metrics-proposal.json"
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
    proposal = ROOT / "config/chat/business-metrics-proposal.json"
    definitions = ROOT / "config/chat/metrics-candidates.json"
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(_receipt(definitions, proposal)), encoding="utf-8")

    payload, receipt = build_approved_payload(proposal, definitions, receipt_path)
    assert payload["metadata"]["metric_ids"] == ["total_revenue"]
    assert payload["rows"]
    assert receipt["receipt_id"] == "test-fixture-only"
    assert all(
        row["value_kind"]
        in {"owner_approved_gold_reported", "owner_approved_gold_fx_converted"}
        for row in payload["rows"]
    )
    serialized_payload = json.dumps(payload, ensure_ascii=False)
    assert all(
        metric not in serialized_payload for metric in ("operating_costs", "fuel_expense", "operating_income")
    )
    q2_revenue = next(
        row for row in payload["rows"] if row["metric_id"] == "total_revenue" and row["period"] == "2026Q2"
    )
    q2_refs = [
        *q2_revenue["source_references"],
        *q2_revenue["quarter_sources"][0]["source_references"],
    ]
    identity_ref = next(ref for ref in q2_refs if ref["current_identity_check"])
    identity_check = identity_ref["current_identity_check"]
    assert identity_check["reported_values_usd_millions"] == {"total_revenue": 1479.0}
    assert identity_check["status"] == "byte_identity_mismatch_factual_values_match"
    assert identity_ref["sha256"] == "6207b9a113074f68e0d8196f9597ddf35f40a32b5f53ca97c5cd2c0a2f0ac781"
    assert identity_ref["captured_bytes"] == 230275

    stale_proposal = tmp_path / "stale-proposal.json"
    stale_proposal.write_bytes(proposal.read_bytes() + b" ")
    with pytest.raises(BusinessMetricsApprovalError, match="exact candidate proposal"):
        build_approved_payload(stale_proposal, definitions, receipt_path)

    stale_definitions = tmp_path / "stale-definitions.json"
    stale_definitions.write_bytes(definitions.read_bytes() + b" ")
    with pytest.raises(BusinessMetricsApprovalError, match="current metric definitions"):
        build_approved_payload(proposal, stale_definitions, receipt_path)


def test_receipt_requires_external_canonical_pin_and_trusted_owner_fields(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    proposal = ROOT / "config/chat/business-metrics-proposal.json"
    definitions = ROOT / "config/chat/metrics-candidates.json"
    receipt = _receipt(definitions, proposal)
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")

    monkeypatch.delenv(APPROVAL_RECEIPT_SHA256_ENV)
    with pytest.raises(BusinessMetricsApprovalError, match="must pin"):
        build_approved_payload(proposal, definitions, receipt_path)

    monkeypatch.setenv(APPROVAL_RECEIPT_SHA256_ENV, "0" * 64)
    with pytest.raises(BusinessMetricsApprovalError, match="externally pinned SHA-256"):
        build_approved_payload(proposal, definitions, receipt_path)

    for field, value, message in (
        ("approved_at", "not-a-date", "approved_at"),
        ("owner_id", "contributor", "owner_id"),
        ("decision_reference", "   ", "decision_reference"),
    ):
        forged = {**receipt, field: value}
        write_json(receipt_path, forged)
        monkeypatch.setenv(APPROVAL_RECEIPT_SHA256_ENV, canonical_receipt_sha256(forged))
        with pytest.raises(BusinessMetricsApprovalError, match=message):
            build_approved_payload(proposal, definitions, receipt_path)


def test_receipt_hash_and_snapshot_validation_ignore_json_formatting(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    snapshot = _approved_snapshot(tmp_path)
    receipt_path = snapshot.root / "data/v1/business_metrics.approval.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=4), encoding="utf-8")
    _resign_site(snapshot.root)

    reloaded = Snapshot(snapshot.root)
    payload = reloaded.payload("data/v1/business_metrics.json")
    assert payload["metadata"]["approval_receipt_sha256"] == canonical_receipt_sha256(receipt)
    assert reloaded.payload("data/v1/business_metrics.approval.json") == receipt


def test_site_without_financial_payload_keeps_its_existing_manifest_without_a_pin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(APPROVAL_RECEIPT_SHA256_ENV, raising=False)
    manifest_path = ROOT / "site/publication_manifest.json"
    original_manifest = manifest_path.read_bytes()
    manifest = json.loads(original_manifest)

    assert sum(item["path"].startswith("data/") for item in manifest["files"]) == 112
    assert len(manifest["contracts"]) == 6
    assert not any("business_metrics" in item["path"] for item in manifest["files"])
    assert verify_site(ROOT / "site") == []
    Snapshot(ROOT / "site")
    assert manifest_path.read_bytes() == original_manifest


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
    assert mxn["value"] == pytest.approx(213_829_404.2979688)
    assert mxn["value_kind"] == "owner_approved_calculated_fx_conversion"
    assert mxn["currency_as_reported"] == ["MXN"]
    assert mxn["quarter_sources"][0]["fx_rate_used"] > 0
    assert mxn["quarter_sources"][0]["fx_rate_type"]
    converted_half = deterministic_query(snapshot, "total_revenue", "VOLARIS", "2020H2")
    assert converted_half["value_kind"] == "owner_approved_calculated_fx_conversion_quarter_sum"
    native_usd = deterministic_query(snapshot, "total_revenue", "VOLARIS", "2021Q1")
    assert native_usd["value_kind"] == "owner_approved_reported"
    native_year = deterministic_query(snapshot, "total_revenue", "VOLARIS", "2021")
    assert native_year["value_kind"] == "owner_approved_reported_quarter_sum"
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


def test_approved_business_metric_scalar_gets_safe_cited_display(tmp_path: Path) -> None:
    snapshot = _approved_snapshot(tmp_path)
    registry = ToolRegistry(snapshot, SimpleNamespace(enable_business_metric_tools=True))
    catalog = snapshot.catalog()
    result = registry.invoke(
        "query_business_metrics",
        {"metric_id": "total_revenue", "entity_id": "AEROMEXICO", "period": "2025Q1"},
    )

    shown = make_displays(result, "query_business_metrics", "approved-call-1", catalog)
    display = shown["display"]
    expected_hash = hashlib.sha256(b"approved-call-1").hexdigest()[:12]
    assert display["display_id"] == f"tabla:consulta_{expected_hash}"
    assert display["value_kind"] == "reported"
    assert display["rows"] == [{"entity": "Aeroméxico", "period": "2025Q1", "value": result["value"]}]
    value_column = next(column for column in display["columns"] if column["key"] == "value")
    assert value_column["unit"] == "USD"
    assert display["sources"]
    assert display["sources"][0]["url"] == result["source_references"][0]["url"]
    second = make_displays(result, "query_business_metrics", "approved-call-2", catalog)["display"]
    assert second["display_id"] != display["display_id"]

    missing = {**result, "value": None, "availability": "incomplete"}
    missing_display = make_displays(missing, "query_business_metrics", "missing-call", catalog)["display"]
    assert missing_display["rows"][0]["value"] is None

    ratio_result = registry.invoke(
        "query_business_metrics",
        {"metric_id": "load_factor", "entity_id": "AEROMEXICO", "period": "2026Q2"},
    )
    ratio_display = make_displays(ratio_result, "query_business_metrics", "ratio-call", catalog)["display"]
    assert ratio_display["rows"][0]["value"] == pytest.approx(84.9)
    assert ratio_display["columns"][-1]["unit"] == "percent"
    assert ratio_display["value_kind"] == "calculated"

    candidate = {
        **result,
        "value": 123.0,
        "approval_gate": "closed",
        "availability": "approval_required",
        "value_kind": "candidate_unapproved",
    }
    assert "display" not in make_displays(candidate, "query_business_metrics", "candidate-call", catalog)


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
