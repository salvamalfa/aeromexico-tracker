"""Entity analysis publication identities and citations, without private data."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from src.publish import gate, manifest
from src.publish.verify import _data_schema_for, verify_site
from src.web_export import analysis
from src.web_export.schemas import ANALYSIS_SCHEMA
from src.web_export.writer import write_json

FIXTURE = Path(__file__).parent / "fixtures/web/analysis_sample.json"


def _payload(entity=None):
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if entity:
        payload.update(
            entity_key=entity,
            period_label="2T26",
            cutoff_date="2026-10-13",
            selection_mode="retrospective",
            guidance_as_of="2026-10-13",
        )
    return payload


def _signed_site(tmp_path, entities=(None, "VOLARIS", "VIVA_AEROBUS", "INDUSTRY")):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<html>TEST ONLY</html>", encoding="utf-8")
    entries = []
    for entity in entities:
        payload = _payload(entity)
        write_json(site / "data/v1" / manifest.analysis_relative_path(payload), payload)
        entries.append(gate._analysis_manifest_entry(payload))
    manifest.write_manifest(site, manifest.build_manifest(site, entries, code_commit="a" * 40))
    return site


def _refresh_files(site):
    current = manifest.load_manifest(site)
    current["files"] = manifest.file_entries(site)
    manifest.write_manifest(site, current)


def test_public_verifier_accepts_all_entities_in_one_quarter(tmp_path):
    site = _signed_site(tmp_path)
    assert verify_site(site) == []
    assert json.loads((site / "data/v1/analysis/2026Q2.json").read_text()) == _payload()


def test_entity_exports_leave_legacy_analysis_bytes_exactly_unchanged(tmp_path, monkeypatch):
    legacy = {"period_id": "2026Q2", "version": "test-version"}
    entity = {**legacy, "entity_key": "VOLARIS"}
    monkeypatch.setattr(analysis, "discover_approved_manifest", lambda root: [legacy])
    monkeypatch.setattr(
        analysis, "export_period", lambda *args, **kw: copy.deepcopy(_payload(kw.get("entity_key")))
    )
    analysis.export_analysis(tmp_path)
    before = (tmp_path / "analysis/2026Q2.json").read_bytes()
    monkeypatch.setattr(analysis, "discover_approved_manifest", lambda root: [legacy, entity])
    analysis.export_analysis(tmp_path)
    assert (tmp_path / "analysis/2026Q2.json").read_bytes() == before
    assert (tmp_path / "analysis/VOLARIS/2026Q2.json").is_file()


def test_entity_paths_and_unknown_entities_are_strict():
    assert _data_schema_for("data/v1/analysis/VIVA_AEROBUS/2026Q2.json") is ANALYSIS_SCHEMA
    assert _data_schema_for("data/v1/analysis/AEROMEXICO/2026Q2.json") is ANALYSIS_SCHEMA
    assert _data_schema_for("data/v1/analysis/DELTA/2026Q2.json") is None


def test_manifest_duplicates_are_scoped_by_entity(tmp_path):
    site = _signed_site(tmp_path)
    current = manifest.load_manifest(site)
    current["analysis_manifest"].append(dict(current["analysis_manifest"][-1]))
    manifest.write_manifest(site, current)
    assert any("more than once" in problem for problem in verify_site(site))


@pytest.mark.parametrize("mutation", ["entity", "period", "version"])
def test_verifier_rejects_cross_identity_headers_even_with_updated_file_hash(tmp_path, mutation):
    site = _signed_site(tmp_path)
    path = site / "data/v1/analysis/VOLARIS/2026Q2.json"
    payload = json.loads(path.read_text())
    if mutation == "entity":
        payload["entity_key"] = "VIVA_AEROBUS"
    elif mutation == "period":
        payload["period_id"] = "2026Q1"
    else:
        payload["version"] = "different-version"
    write_json(path, payload)
    _refresh_files(site)
    assert verify_site(site)


def test_verifier_rejects_unmanifested_analysis(tmp_path):
    site = _signed_site(tmp_path, (None,))
    payload = _payload("VOLARIS")
    write_json(site / "data/v1" / manifest.analysis_relative_path(payload), payload)
    _refresh_files(site)
    assert any("no approval identity" in problem for problem in verify_site(site))


def _save_record(root, entity, version="version-a", period="2026Q2"):
    draft = {"period_id": period}
    if entity:
        draft.update(entity_key=entity, schema_version="entity_analyst_v1")
    record = {"draft": draft, "version": version}
    entry = analysis._record_manifest_entry(record)
    path = analysis._record_path(entry, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record), encoding="utf-8")
    return record, path


def test_discovery_keeps_same_quarter_for_distinct_entities(tmp_path, monkeypatch):
    root = tmp_path / "analysis_runs/lifecycle"
    for entity in (None, "VOLARIS", "VIVA_AEROBUS", "INDUSTRY"):
        _save_record(root, entity)
    monkeypatch.setattr(analysis.flow, "state", lambda r, rt: {"state": "approved"})
    entries = analysis.discover_approved_manifest(root)
    assert len(entries) == 4
    assert entries[0] == {"period_id": "2026Q2", "version": "version-a"}
    assert {entry.get("entity_key", "AEROMEXICO") for entry in entries} == manifest.ANALYSIS_ENTITIES


def test_discovery_rejects_multiple_approved_versions_within_entity(tmp_path, monkeypatch):
    root = tmp_path / "analysis_runs/lifecycle"
    _save_record(root, "VOLARIS", "v1")
    _save_record(root, "VOLARIS", "v2")
    monkeypatch.setattr(analysis.flow, "state", lambda r, rt: {"state": "approved"})
    with pytest.raises(ValueError, match="Multiple approved versions"):
        analysis.discover_approved_manifest(root)


def test_loaded_entity_record_must_match_request_and_path(tmp_path):
    root = tmp_path / "analysis_runs/lifecycle"
    record, path = _save_record(root, "VOLARIS")
    assert analysis._load_record("2026Q2", "version-a", root, entity_key="VOLARIS") == record
    record["draft"]["entity_key"] = "VIVA_AEROBUS"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="does not match"):
        analysis._load_record("2026Q2", "version-a", root, entity_key="VOLARIS")
    with pytest.raises(ValueError):
        analysis._load_record("../../secrets", "version-a", root, entity_key="VOLARIS")


def test_unapproved_entity_cannot_export_and_preserves_existing_files(tmp_path, monkeypatch):
    root = tmp_path / "analysis_runs/lifecycle"
    _save_record(root, "VOLARIS")
    monkeypatch.setattr(
        analysis.flow,
        "consumer_payload",
        lambda *args: (_ for _ in ()).throw(ValueError("No human approval")),
    )
    with pytest.raises(analysis.MissingAnalysisInput, match="No human approval"):
        analysis.export_period("2026Q2", "version-a", root=root, entity_key="VOLARIS")


def test_gate_allows_distinct_entities_and_refuses_duplicate_entity_slots(tmp_path):
    root = tmp_path / "analysis_runs/lifecycle"
    _, a = _save_record(root, None)
    _, b = _save_record(root, "VOLARIS")
    _, c = _save_record(root, "VOLARIS", "v2")
    assert len(gate.load_records([a, b])) == 2
    with pytest.raises(gate.PublicationRefused, match="Multiple approved versions"):
        gate.load_records([b, c])


def test_gate_rejects_authorization_for_another_entity(tmp_path, monkeypatch):
    record, _ = _save_record(tmp_path / "analysis_runs/lifecycle", "VOLARIS")
    authorized = _payload("VIVA_AEROBUS")
    authorized["version"] = record["version"]
    monkeypatch.setattr(gate.flow, "consumer_payload", lambda *a: authorized)
    monkeypatch.setattr(
        gate.flow, "verified_inputs", lambda r: ({"entity_key": "VOLARIS", "period_id": "2026Q2"}, {}, {})
    )
    with pytest.raises(ValueError, match="differs"):
        gate._verify_under_lock([record], tmp_path)


def _citation_inputs():
    package = {
        "schema_version": "entity_evidence_v1",
        "period_id": "2026Q2",
        "sources": [
            {"artifact_id": "a", "source_url": "https://cdn.investorcloud.net/VivaAerobus/report.pdf"}
        ],
        "excerpts": [
            {"excerpt_id": "e", "artifact_id": "a", "period_id": "2026Q2", "text": "Original source row"}
        ],
        "metrics": [{"metric_id": "m", "excerpt_id": "e", "artifact_id": "a"}],
    }
    calculations = {
        "nodes": [
            {
                "calculation_id": "c",
                "period_id": "2026Q2",
                "unit": "USD",
                "value": 609000000,
                "formatted_value": "609,0 millones de dólares",
                "input_ids": ["m"],
            }
        ]
    }
    return package, calculations


def test_entity_quantitative_citation_uses_exact_approved_format_and_public_fields():
    package, calculations = _citation_inputs()
    claim = {"text_template": "Ingresos de {{income}}.", "bindings": {"income": {"calculation_id": "c"}}}
    result = analysis._claim_citations(claim, package, calculations, {})
    assert result[0]["value"] == "609,0 millones de dólares"
    assert result[0]["value"] in "Ingresos de 609,0 millones de dólares."
    assert result[0]["href"] == "https://cdn.investorcloud.net/VivaAerobus/report.pdf"
    assert set(result[0]) == {"label", "href", "title", "value"}


def test_entity_qualitative_and_company_citations_link_exact_rendered_leads():
    package, calculations = _citation_inputs()
    claim = {
        "lead": "Los costos aumentaron.",
        "text_template": "Los costos aumentaron. Explicación atribuida.",
        "bindings": {},
        "evidence_ids": ["e"],
        "support_spans": [{"excerpt_id": "e", "text": "Original source row"}],
    }
    result = analysis._claim_citations(claim, package, calculations, {})
    assert len(result) == 1 and result[0]["value"] == claim["lead"]


def test_entity_citation_refuses_nonofficial_host():
    package, calculations = _citation_inputs()
    package["sources"][0]["source_url"] = "https://cdn.investorcloud.net.evil.example/report.pdf"
    claim = {"text_template": "{{income}}", "bindings": {"income": {"calculation_id": "c"}}}
    assert analysis._claim_citations(claim, package, calculations, {}) == []
