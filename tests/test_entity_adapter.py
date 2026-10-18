"""Boundary checks for source-replayed capsules; no production approvals."""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import pytest

from src.analysis_agent import entity_adapter as adapter


@pytest.mark.parametrize(
    "field,value",
    [
        ("package_id", "../../other"),
        ("calculation_fingerprint", "../other"),
        ("entity_key", "../VOLARIS"),
        ("period_id", "2026H1"),
    ],
)
def test_invalid_input_identity_rejected_before_read(monkeypatch, field, value):
    draft = {
        "entity_key": "VOLARIS",
        "period_id": "2026Q2",
        "package_id": "VOLARIS_2026Q2_" + "a" * 64,
        "calculation_fingerprint": "b" * 64,
    }
    draft[field] = value
    monkeypatch.setattr(adapter, "read", lambda path: pytest.fail("Untrusted path read"))
    with pytest.raises(ValueError):
        adapter.verified_inputs({"draft": draft})


def test_unreviewed_extractor_cannot_execute(tmp_path, monkeypatch):
    (tmp_path / "prepare.py").write_text("raise RuntimeError('unexpected execution')")
    monkeypatch.setattr(adapter.subprocess, "run", lambda *a, **k: pytest.fail("Unreviewed code executed"))
    with pytest.raises(ValueError, match="Unreviewed extractor"):
        adapter._replay({"entity_key": "VOLARIS"}, tmp_path)


@pytest.mark.parametrize(
    "change", ["original", "capture_hash", "capture_url", "late_capture", "http_failure"]
)
def test_original_and_capture_proof_fail_closed(tmp_path, monkeypatch, change):
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    original = bronze / "source.pdf"
    raw = b"synthetic source bytes for a boundary test"
    original.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    source = {
        "artifact_id": "test_artifact",
        "source_file": "source.pdf",
        "source_url": "https://www.sec.gov/Archives/test.pdf",
        "artifact_sha256": digest,
    }
    meta = {
        "sha256": digest,
        "source_url": source["source_url"],
        "http_status": 200,
        "downloaded_at": "2026-08-24T03:15:17+00:00",
    }
    if change == "original":
        original.write_bytes(b"changed")
    elif change == "capture_hash":
        meta["sha256"] = "a" * 64
    elif change == "capture_url":
        meta["source_url"] = "https://example.com/different"
    elif change == "late_capture":
        meta["downloaded_at"] = "2026-10-14T00:00:00+00:00"
    else:
        meta["http_status"] = 404
    (bronze / "source.pdf.meta.json").write_text(json.dumps(meta))
    monkeypatch.setattr(adapter, "PATHS", SimpleNamespace(root=tmp_path, bronze=bronze))
    with pytest.raises(ValueError):
        adapter._sources({"artifacts": [source]})


@pytest.mark.parametrize(
    "filename", ["analyst.py", "evidence.py", "lifecycle_identity.py", "entities.py", "uv.lock"]
)
def test_shared_validation_change_invalidates_entity_presentation(monkeypatch, filename):
    from src.analysis_agent.analyst import SKILL

    baseline = adapter.code_version()
    original_sha = adapter.sha
    record = {"code_version": baseline, "prompt_version": original_sha(SKILL)}
    monkeypatch.setattr(
        adapter, "sha", lambda path: "0" * 64 if path.name == filename else original_sha(path)
    )
    with pytest.raises(ValueError, match="implementation changed"):
        adapter.require_current_presentation(record)


@pytest.mark.parametrize(
    "module",
    [
        "src/web_export/analysis.py",
        "src/web_export/privacy.py",
        "src/web_export/schemas.py",
        "src/web_export/writer.py",
        "src/publish/manifest.py",
        "src/publish/gate.py",
        "src/publish/records.py",
        "src/publish/receipts.py",
        "src/publish/verify.py",
        "contracts/web/analysis.schema.json",
        "contracts/web/publication_manifest.schema.json",
        "contracts/web/privacy.yaml",
        "web/src/views/executive/narrative.ts",
        "web/src/views/shell/carriers.ts",
        "web/src/views/executive/bootstrap.ts",
        "web/src/views/executive/state.ts",
        "web/src/views/executive/entities.ts",
        "web/src/views/flights/dom.ts",
        "web/package-lock.json",
    ],
)
def test_publication_provenance_dependency_changes_entity_code_version(monkeypatch, module):
    from src.analysis_agent.analyst import SKILL

    baseline = adapter.code_version()
    original_sha = adapter.sha
    record = {"code_version": baseline, "prompt_version": original_sha(SKILL)}
    dependency = adapter.PATHS.root / module
    assert dependency.is_file()
    monkeypatch.setattr(adapter, "sha", lambda path: "0" * 64 if path == dependency else original_sha(path))
    assert adapter.code_version() != baseline
    with pytest.raises(ValueError, match="implementation changed"):
        adapter.require_current_presentation(record)


def _temporary_code_tree(tmp_path, monkeypatch):
    for name in ("src/dashboard/entities.py", "src/config.py", "uv.lock"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic baseline")
    monkeypatch.setattr(adapter, "PATHS", SimpleNamespace(root=tmp_path))


def test_code_version_is_deterministic_and_uses_sorted_relative_paths(tmp_path, monkeypatch):
    _temporary_code_tree(tmp_path, monkeypatch)
    for name in ("web/src/z.ts", "src/publish/b.py", "contracts/web/a.json", "web/src/a.css"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic runtime dependency")
    actual_digest = adapter.digest
    keys = []

    def capture(value):
        keys.append(list(value))
        return actual_digest(value)

    monkeypatch.setattr(adapter, "digest", capture)
    assert adapter.code_version() == adapter.code_version()
    assert keys[0] == sorted(keys[0]) == keys[1]
    assert all(not path.startswith("/") for path in keys[0])


@pytest.mark.parametrize(
    "name",
    [
        "src/dashboard/market_demand.py",
        "src/dashboard/flights.py",
        "src/dashboard/flight_cells.py",
        "src/dashboard/domestic_routes.py",
        "src/dashboard/international_routes.py",
        "src/dashboard/entity_routes.py",
        "src/dashboard/route_capacity.py",
        "src/dashboard/executive_summary.py",
        "src/dashboard/new_package/new_builder.py",
        "src/dashboard/news.py",
        "src/conversational_analytics/news_projection.py",
        "src/analysis_agent/new.py",
        "src/publish/new.py",
        "src/web_export/new.py",
        "contracts/web/new.schema.json",
        "web/src/new.ts",
        "web/src/new.tsx",
        "web/src/new.js",
        "web/src/new.jsx",
        "web/src/new.json",
        "web/src/new.css",
        "web/index.html",
        "web/package.json",
        "web/package-lock.json",
        "web/vite.config.ts",
        "web/tsconfig.json",
        "web/tsconfig.app.json",
    ],
)
def test_runtime_file_addition_and_deletion_change_code_version(tmp_path, monkeypatch, name):
    _temporary_code_tree(tmp_path, monkeypatch)
    baseline = adapter.code_version()
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("synthetic new runtime dependency")
    assert adapter.code_version() != baseline
    path.unlink()
    assert adapter.code_version() == baseline


@pytest.mark.parametrize(
    "name",
    [
        "web/src/new.test.ts",
        "web/src/new.spec.tsx",
        "web/src/new.spec.js",
        "web/src/__tests__/helper.ts",
        "web/src/tests/helper.json",
        "web/src/spec/helper.css",
    ],
)
def test_web_test_and_spec_files_do_not_change_code_version(tmp_path, monkeypatch, name):
    _temporary_code_tree(tmp_path, monkeypatch)
    baseline = adapter.code_version()
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("synthetic test-only dependency")
    assert adapter.code_version() == baseline


@pytest.mark.parametrize("format_fields", [{"formatted": "1,0"}, {"formatted_value": "1,0"}])
def test_normalization_accepts_either_reviewed_format_field(format_fields):
    package = {
        "entity_key": "VOLARIS",
        "period_id": "2026Q2",
        "sources": [],
        "package_id": "synthetic",
        "evidence_fingerprint": "test",
    }
    node = {
        "calculation_id": "calc_test",
        "value": 1.0,
        "unit": "USD",
        "period_id": "2026Q2",
        **format_fields,
    }
    _, calculated, _ = adapter._normalize(
        package, {"inputs": [], "calculations": {"calc_test": node}}, {"excerpts": []}, {"claims": []}
    )
    assert calculated["nodes"][0]["formatted_value"] == "1,0"


def _source_identity_normalization_case():
    package = {
        "entity_key": "VOLARIS",
        "period_id": "2026Q2",
        "sources": [
            {"artifact_id": "source-a", "source_file": "report-a.pdf"},
            {"artifact_id": "source-b", "source_file": "report-b.pdf"},
        ],
        "package_id": "synthetic",
        "evidence_fingerprint": "test",
    }
    evidence = {
        "excerpts": [
            {
                "excerpt_id": "excerpt-a",
                "source_file": "report-a.pdf",
                "artifact_id": "source-a",
                "literal_text": "Synthetic primary fragment.",
            }
        ]
    }
    context = {
        "inputs": [{"input_id": "metric-a", "excerpt_id": "excerpt-a"}],
        "calculations": {},
    }
    return package, context, evidence, {"claims": []}


@pytest.mark.parametrize("supplied_artifact", [True, False])
def test_normalization_resolves_unique_source_file_and_accepts_matching_artifact(supplied_artifact):
    package, context, evidence, candidate = _source_identity_normalization_case()
    if not supplied_artifact:
        evidence["excerpts"][0].pop("artifact_id")
    normalized, _, _ = adapter._normalize(package, context, evidence, candidate)
    assert normalized["excerpts"][0]["artifact_id"] == "source-a"
    assert normalized["metrics"][0]["artifact_id"] == "source-a"


def test_normalization_rejects_another_valid_artifact_for_the_excerpt_source_file():
    package, context, evidence, candidate = _source_identity_normalization_case()
    evidence["excerpts"][0]["artifact_id"] = "source-b"
    with pytest.raises(ValueError, match="artifact identity differs"):
        adapter._normalize(package, context, evidence, candidate)


def test_normalization_rejects_mistyped_source_even_with_a_valid_supplied_artifact():
    package, context, evidence, candidate = _source_identity_normalization_case()
    evidence["excerpts"][0]["source_file"] = "report-typo.pdf"
    with pytest.raises(ValueError, match="source identity is ambiguous"):
        adapter._normalize(package, context, evidence, candidate)


def test_normalization_rejects_duplicate_source_file_even_with_matching_supplied_artifact():
    package, context, evidence, candidate = _source_identity_normalization_case()
    package["sources"].append({"artifact_id": "source-c", "source_file": "report-a.pdf"})
    with pytest.raises(ValueError, match="source identity is ambiguous"):
        adapter._normalize(package, context, evidence, candidate)


def test_normalization_requires_source_file_even_with_valid_supplied_artifact():
    package, context, evidence, candidate = _source_identity_normalization_case()
    evidence["excerpts"][0].pop("source_file")
    with pytest.raises(ValueError, match="source_file is required"):
        adapter._normalize(package, context, evidence, candidate)


def test_normalization_rejects_same_artifact_id_for_different_valid_source_files():
    package, context, evidence, candidate = _source_identity_normalization_case()
    package["sources"][1]["artifact_id"] = "source-a"
    with pytest.raises(ValueError, match="Duplicate artifact_id"):
        adapter._normalize(package, context, evidence, candidate)


def test_normalization_rejects_same_excerpt_id_for_different_valid_sources():
    package, context, evidence, candidate = _source_identity_normalization_case()
    evidence["excerpts"].append(
        {
            "excerpt_id": "excerpt-a",
            "source_file": "report-b.pdf",
            "artifact_id": "source-b",
            "literal_text": "Another valid primary fragment.",
        }
    )
    with pytest.raises(ValueError, match="Duplicate excerpt_id"):
        adapter._normalize(package, context, evidence, candidate)


@pytest.mark.parametrize("module", ["src/dashboard/market_demand.py", "src/dashboard/news.py", "src/dashboard/flights.py", "src/dashboard/flight_cells.py", "src/dashboard/domestic_routes.py", "src/dashboard/international_routes.py", "src/dashboard/entity_routes.py", "src/dashboard/route_capacity.py", "src/dashboard/executive_summary.py", "src/dashboard/new_package/new_builder.py", "src/conversational_analytics/news_projection.py"])
def test_new_public_builder_mutation_invalidates_presentation(tmp_path, monkeypatch, module):
    from src.analysis_agent.analyst import SKILL
    _temporary_code_tree(tmp_path, monkeypatch)
    path=tmp_path / module
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text("initial approved calculation/projection")
    record={"code_version":adapter.code_version(),"prompt_version":adapter.sha(SKILL)}
    path.write_text("changed calculation/projection")
    with pytest.raises(ValueError,match="implementation changed"):
        adapter.require_current_presentation(record)
