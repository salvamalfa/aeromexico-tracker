"""Exact selectors use synthetic ledgers only, with the real consumer gate."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from src.analysis_agent import lifecycle as flow
from src.analysis_agent.analyst import validate
from src.publish import manifest as publication
from src.web_export import analysis
from src.web_export.writer import write_json
from test_stage16_analyst import inputs  # noqa: F401 -- synthetic fixture
from test_web_export_analysis_isolation import _approve, _isolated_case


@pytest.fixture
def selected_case(inputs, tmp_path, monkeypatch):  # noqa: F811
    legacy, root, _ = _isolated_case(inputs, tmp_path, monkeypatch)
    _, package, calculations = inputs
    checks = validate(legacy["draft"], package, calculations)
    monkeypatch.setattr(flow, "verified_inputs", lambda r: (package, calculations, checks))
    real_presentation = flow.require_current_presentation
    monkeypatch.setattr(
        flow, "require_current_presentation",
        lambda r: None if flow.is_entity_record(r) else real_presentation(r),
    )
    records = [legacy]
    for entity in ("VOLARIS", "VIVA_AEROBUS", "INDUSTRY"):
        record = deepcopy(legacy)
        draft = record["draft"]
        draft.update(
            schema_version="entity_analyst_v1", entity_key=entity,
            period_label="2T26 (abril–junio de 2026)", cutoff_date="2026-10-13",
            selection_mode="retrospective", guidance_as_of="report_date",
            package_id=entity + "_" + draft["package_id"],
        )
        record["content_hash"] = flow.digest(draft)
        record["version"] = flow.digest({k: record[k] for k in ("draft", "prompt_version", "code_version")})
        record["analysis_id"] = entity + "_2026Q2_" + record["version"]
        entry = analysis._record_manifest_entry(record)
        write_json(analysis._record_path(entry, root), record)
        audit = dict(
            entity_key=entity, period_id="2026Q2", version=record["version"],
            content_hash=record["content_hash"], reviewer="independent_codex_agent",
            reviewer_task="TEST ONLY / selector", model=None,
            model_unavailable_reason="Synthetic fixture only", package_id=draft["package_id"],
            calculation_fingerprint=draft["calculation_fingerprint"],
            reviewed_claim_ids=[x["claim_id"] for x in draft["claims"]], decision="pass", findings=[],
            checks=[dict(key=k, result="pass", detail="Synthetic test only") for k in sorted(flow.CHECKS)],
        )
        authorization = dict(
            entity_key=entity, period_id="2026Q2", decision="approve_analysis",
            version=record["version"], content_hash=record["content_hash"], human_name="TEST ONLY",
            verbatim_message="Synthetic consent; not a user approval.", conversation_reference="pytest selector",
            authorized_at=datetime.now(timezone.utc).isoformat(),
        )
        flow.record_audit(record, audit, root)
        authorization["authorized_at"] = datetime.now(timezone.utc).isoformat()
        flow.approve(record, authorization, root)
        records.append(record)
    entries = [analysis._record_manifest_entry(r) for r in records]
    return records, entries, root


@pytest.mark.parametrize("full_manifest", [False, True])
def test_selector_reproduces_exact_four_with_real_gate_and_no_discovery(
    selected_case, tmp_path, monkeypatch, full_manifest
):
    records, entries, root = selected_case
    out = tmp_path / "out"
    original_consumer = flow.consumer_payload
    consumed = []

    def consume(record, ledger):
        consumed.append(flow.record_identity(record))
        return original_consumer(record, ledger)

    monkeypatch.setattr(flow, "consumer_payload", consume)
    monkeypatch.setattr(
        analysis, "discover_approved_manifest",
        lambda *a: (_ for _ in ()).throw(AssertionError("explicit selector must not discover")),
    )
    receipt_entries = []
    for record, entry in zip(records, entries):
        payload = original_consumer(record, root)
        receipt_entries.append({**entry, **{
            k: payload[k] for k in ("content_hash", "evidence_fingerprint", "approval_event", "audit_hash")
        }})
    selection = publication.build_manifest(tmp_path, receipt_entries, code_commit="a" * 40) if full_manifest else entries
    written = analysis.export_analysis(out, root=root, manifest=selection)
    expected = {
        "analysis/2026Q2.json", "analysis/VOLARIS/2026Q2.json",
        "analysis/VIVA_AEROBUS/2026Q2.json", "analysis/INDUSTRY/2026Q2.json",
    }
    assert {p.relative_to(out).as_posix() for p in written} == expected
    assert len(consumed) == 4
    first = {p.relative_to(out): p.read_bytes() for p in written}
    analysis.export_analysis(out, root=root, manifest=selection)
    assert first == {p.relative_to(out): p.read_bytes() for p in written}
    for record, entry in zip(records, entries):
        payload = json.loads((out / publication.analysis_relative_path(entry)).read_bytes())
        assert payload["version"] == record["version"]
        assert payload.get("entity_key", "AEROMEXICO") == entry.get("entity_key", "AEROMEXICO")


def test_explicit_version_avoids_ambiguous_discovery_without_revoking_either(
    inputs, tmp_path, monkeypatch
):
    record, root, drafts = _isolated_case(inputs, tmp_path, monkeypatch)
    from src.analysis_agent.analyst import save

    d, p, c = inputs
    another = deepcopy(d)
    another["claims"][0]["text_template"] += " Otra versión sintética."
    newer, _, _ = save(another, p, c, drafts)
    _approve(newer, (another, p, c), root, monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="Multiple approved versions"):
        analysis.export_analysis(tmp_path / "default", root=root)
    selected = analysis._record_manifest_entry(record)
    written = analysis.export_analysis(tmp_path / "selected", root=root, manifest=[selected])
    assert json.loads(written[0].read_bytes())["version"] == record["version"]
    assert flow.state(record, root)["state"] == flow.state(newer, root)["state"] == "approved"


def test_explicit_unapproved_record_fails_even_dev_and_preserves_prior_output(
    selected_case, tmp_path
):
    records, entries, root = selected_case
    out = tmp_path / "out"
    analysis.export_analysis(out, root=root, manifest=entries)
    before = {p.relative_to(out): p.read_bytes() for p in out.rglob("*.json")}
    flow.revoke(records[1], "Synthetic test withdrawal", "TEST ONLY", root)
    with pytest.raises(analysis.MissingAnalysisInput, match="no human approval"):
        analysis.export_analysis(out, root=root, manifest=entries, allow_missing=True)
    assert before == {p.relative_to(out): p.read_bytes() for p in out.rglob("*.json")}


def test_explicit_historical_approval_cannot_bypass_current_presentation(
    selected_case, tmp_path, monkeypatch
):
    records, entries, root = selected_case
    assert flow.state(records[0], root)["state"] == "approved"
    monkeypatch.setattr(
        flow, "require_current_presentation",
        lambda *a: (_ for _ in ()).throw(ValueError("Presentation or instructions changed")),
    )
    with pytest.raises(analysis.MissingAnalysisInput, match="Presentation or instructions changed"):
        analysis.export_analysis(tmp_path / "out", root=root, manifest=entries)


@pytest.mark.parametrize("mutation", ["wrong_entity", "wrong_period", "wrong_version", "wrong_receipt"])
def test_explicit_selection_rejects_mismatched_record_or_receipt(selected_case, tmp_path, mutation):
    records, entries, root = selected_case
    entry = deepcopy(entries[1])
    if mutation == "wrong_receipt":
        entry["content_hash"] = "wrong"
    else:
        record = deepcopy(records[1])
        if mutation == "wrong_entity":
            record["draft"]["entity_key"] = "VIVA_AEROBUS"
        elif mutation == "wrong_period":
            record["draft"]["period_id"] = "2026Q1"
        else:
            record["version"] = "different-version"
        write_json(analysis._record_path(entries[1], root), record)
    with pytest.raises(ValueError, match="does not match"):
        analysis.export_analysis(tmp_path / "out", root=root, manifest=[entry])


@pytest.mark.parametrize("value", [
    {}, "not a manifest", [{"period_id": "2026Q2"}],
    [{"period_id": "2026Q2", "version": "../private"}],
    [{"period_id": "2026Q2", "version": "v", "entity_key": "DELTA"}],
    [{"period_id": "2026Q2", "version": "v", "unexpected": "x"}],
    [{"period_id": "2026Q2", "version": "v"}, {"period_id": "2026Q2", "version": "v2", "entity_key": "AEROMEXICO"}],
])
def test_malformed_selector_fails_before_output(value, tmp_path):
    out = tmp_path / "absent"
    with pytest.raises(ValueError):
        analysis.export_analysis(out, manifest=value)
    assert not out.exists()


def test_both_cli_entry_points_load_explicit_manifest_and_skip_discovery(selected_case, tmp_path, monkeypatch):
    _, entries, root = selected_case
    selector = write_json(tmp_path / "selection.json", entries)
    monkeypatch.setattr(
        analysis, "discover_approved_manifest",
        lambda *a: (_ for _ in ()).throw(AssertionError("CLI selector must not discover")),
    )
    real_export = analysis.export_analysis
    monkeypatch.setattr(analysis, "export_analysis", lambda out, **kw: real_export(out, root=root, **kw))
    assert analysis.main(["--out", str(tmp_path / "analysis-cli"), "--analysis-manifest", str(selector)]) == 0
    from src.web_export import __main__ as cli

    for name in ("build_flight_payload", "build_executive_payload", "build_market_payload"):
        monkeypatch.setattr(cli, name, lambda: {})
    for name in ("export_flights", "export_executive", "export_market"):
        monkeypatch.setattr(cli, name, lambda *a, **k: [])
    assert cli.main(["--out", str(tmp_path / "full-cli"), "--analysis-manifest", str(selector)]) == 0
    assert len(list((tmp_path / "full-cli/analysis").rglob("*.json"))) == 4
