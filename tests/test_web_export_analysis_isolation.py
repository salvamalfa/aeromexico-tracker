"""R2 (A4/A5/A6): src.web_export.analysis reads an alternate ``root``'s own
drafts/ledger, never leaves stale ``analysis/<period_id>.json`` files behind
after a revocation, and refuses an ambiguous multi-version manifest instead
of guessing. src.publish.gate rejects two --record for the same period_id
before any work. No local_data needed -- everything here builds its own
isolated ledger under tmp_path, the same fixture style test_stage17_lifecycle
uses.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.analysis_agent import lifecycle as flow
from src.analysis_agent.analyst import save, validate
from src.publish.gate import PublicationRefused, load_records
from src.web_export.analysis import DRAFTS_ROOT, discover_approved_manifest, export_analysis
from test_stage16_analyst import inputs  # noqa: F401 - pytest fixture


def _approve(record, inputs_tuple, root, monkeypatch, tmp_path):
    d, p, c = inputs_tuple
    monkeypatch.setattr(flow, "verified_inputs", lambda r: (p, c, validate(r["draft"], p, c)))
    report = dict(
        version=record["version"], content_hash=record["content_hash"], reviewer="independent_codex_agent",
        reviewer_task="test-only/auditor", model=None, model_unavailable_reason="Synthetic test fixture",
        package_id=d["package_id"], calculation_fingerprint=d["calculation_fingerprint"],
        reviewed_claim_ids=[x["claim_id"] for x in d["claims"]], decision="pass", findings=[],
        checks=[dict(key=k, result="pass", detail="Synthetic test only") for k in sorted(flow.CHECKS)],
    )
    flow.record_audit(record, report, root)
    authorization = dict(
        decision="approve_analysis", version=record["version"], content_hash=record["content_hash"],
        human_name="TEST ONLY", verbatim_message="Synthetic authorization, not a real user approval.",
        conversation_reference="pytest fixture", authorized_at=datetime.now(timezone.utc).isoformat(),
    )
    flow.approve(record, authorization, root)


def _isolated_case(inputs, tmp_path, monkeypatch):
    """A fresh drafts/ledger pair under tmp_path, approved -- mirrors
    src.web_export.analysis._drafts_root_for's root.parent/"drafts" layout."""

    d, p, c = inputs
    root = tmp_path / "analysis_runs" / "lifecycle"
    drafts_root = tmp_path / "analysis_runs" / "drafts"
    record, _, _ = save(d, p, c, drafts_root)
    _approve(record, inputs, root, monkeypatch, tmp_path)
    return record, root, drafts_root


def test_alternate_root_reads_its_own_drafts_and_ledger_not_the_repos(inputs, tmp_path, monkeypatch):
    record, root, drafts_root = _isolated_case(inputs, tmp_path, monkeypatch)

    manifest = discover_approved_manifest(root)
    assert manifest == [{"period_id": "2026Q2", "version": record["version"]}]
    # Reads under tmp_path, never under the repo's real DRAFTS_ROOT.
    assert drafts_root != DRAFTS_ROOT
    assert not (DRAFTS_ROOT / "2026Q2" / f"{record['version']}.json").exists()


def test_revocation_removes_a_previously_exported_analysis_file(inputs, tmp_path, monkeypatch):
    record, root, _ = _isolated_case(inputs, tmp_path, monkeypatch)
    out_dir = tmp_path / "out"

    written = export_analysis(out_dir, root=root)
    exported = out_dir / "analysis" / "2026Q2.json"
    assert exported.is_file()
    assert exported in written

    flow.revoke(record, "test revocation", "TEST", root)

    export_analysis(out_dir, root=root)
    assert not exported.exists()
    assert (out_dir / "analysis").is_dir()
    assert list((out_dir / "analysis").glob("*.json")) == []


def test_two_approved_versions_of_one_period_raise_and_write_nothing(inputs, tmp_path, monkeypatch):
    d, p, c = inputs
    root = tmp_path / "analysis_runs" / "lifecycle"
    drafts_root = tmp_path / "analysis_runs" / "drafts"

    record_v1, _, _ = save(d, p, c, drafts_root)
    _approve(record_v1, inputs, root, monkeypatch, tmp_path)

    d2 = json.loads(json.dumps(d))
    d2["claims"][0]["text_template"] += " Cambio editorial adicional para una segunda versión."
    record_v2, _, _ = save(d2, p, c, drafts_root)
    _approve(record_v2, (d2, p, c), root, monkeypatch, tmp_path)

    assert record_v1["version"] != record_v2["version"]

    with pytest.raises(ValueError, match="Multiple approved versions for period 2026Q2"):
        discover_approved_manifest(root)

    out_dir = tmp_path / "out"
    with pytest.raises(ValueError, match="Multiple approved versions for period 2026Q2"):
        export_analysis(out_dir, root=root)
    assert not out_dir.exists()


def test_gate_rejects_duplicate_period_records(tmp_path):
    record_a = {"draft": {"period_id": "2026Q2"}, "version": "v1"}
    record_b = {"draft": {"period_id": "2026Q2"}, "version": "v2"}
    path_a = tmp_path / "a.json"
    path_b = tmp_path / "b.json"
    path_a.write_text(json.dumps(record_a), encoding="utf-8")
    path_b.write_text(json.dumps(record_b), encoding="utf-8")

    with pytest.raises(PublicationRefused, match="Multiple approved versions for period 2026Q2"):
        load_records([path_a, path_b])
