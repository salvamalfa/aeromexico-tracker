"""Adversarial boundaries for source replay and an atomic story replacement."""

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.publish import quarterly_story_data as data
from src.publish import quarterly_story_scope as scope
from src.publish import quarterly_story_update as update
from src.publish import replay_directories as directories


def ref(path):
    return {"path": str(path), "sha256": scope.sha(path.read_bytes())}


@pytest.fixture
def afac_capture(tmp_path, monkeypatch):
    monkeypatch.setattr(data, "PATHS", SimpleNamespace(root=tmp_path))
    folder = tmp_path / "data/bronze/afac"
    folder.mkdir(parents=True)
    workbook = folder / "original.xlsx"
    workbook.write_bytes(b"workbook")
    sidecar = workbook.with_suffix(".xlsx.meta.json")
    metadata = dict(
        sha256=scope.sha(workbook.read_bytes()),
        http_status=200,
        source_system="afac",
        download_method="httpx",
        bytes=8,
        source_url="https://www.gob.mx/cms/uploads/attachment/file/1112829/resumen-septiembre-2026-27102026.xlsx",
        downloaded_at=datetime.now(UTC).isoformat(),
    )

    def retain(value):
        sidecar.write_text(json.dumps(value), encoding="utf-8")
        (folder.parent / "_manifest.jsonl").write_text(json.dumps(value) + "\n", encoding="utf-8")
        return {"workbook": ref(workbook), "metadata": ref(sidecar)}

    return workbook, metadata, retain


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_url", "https://untrusted.invalid/file.xlsx"),
        ("source_system", "unreviewed"),
        ("bytes", 9),
        ("download_method", "manual"),
        ("downloaded_at", "future"),
        ("downloaded_at", "2026-10-27T00:00:00"),
    ],
)
def test_afac_receipt_rejects_invalid_provenance_even_with_matching_hashes(afac_capture, field, value):
    workbook, metadata, retain = afac_capture
    assert data.afac_input(retain(metadata))[0] == workbook
    if value == "future":
        value = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="AFAC"):
        data.afac_input(retain({**metadata, field: value}))


def test_afac_original_must_exist_in_its_actual_capture_manifest(afac_capture):
    workbook, metadata, retain = afac_capture
    references = retain(metadata)
    (workbook.parents[1] / "_manifest.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest"):
        data.afac_input(references)


@pytest.mark.parametrize("duplicate", [False, True])
def test_anac_selected_certificate_must_be_the_exact_unique_consumed_receipt(
    tmp_path, monkeypatch, duplicate
):
    from src.source_updates import collection

    monkeypatch.setattr(data, "PATHS", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(collection, "ROOT", tmp_path)
    monkeypatch.setattr(data, "afac_input", lambda _: (tmp_path / "unused.xlsx", {}))
    candidate = tmp_path / "tmp/source-updates/anac"
    receipts = candidate / "receipts"
    receipts.mkdir(parents=True)
    certificate = receipts / "certified-anac-2026M09.json"
    certificate.write_text("{}")
    decoy = receipts / ("certified-anac-other.json" if duplicate else "unrelated.json")
    decoy.write_text("{}")
    sources = dict(
        afac_summary=dict(workbook={}, metadata={}, year=2026, through=9),
        anac=dict(
            candidate=str(candidate), certification=ref(certificate if duplicate else decoy), quarter="2026Q3"
        ),
        news={},
    )
    with pytest.raises(ValueError, match="exact certification"):
        data.outputs(sources, tmp_path, {})


def denied_symlink(*args, **kwargs):
    error = OSError("Symlink privilege unavailable")
    error.winerror = 1314
    raise error


def test_windows_copy_fallback_preserves_every_nested_file(tmp_path, monkeypatch):
    source = tmp_path / "source"
    (source / "nested").mkdir(parents=True)
    (source / "nested/original.bin").write_bytes(b"exact\x00original")
    (source / "receipt.json").write_text('{"actual":true}')
    monkeypatch.setattr(Path, "symlink_to", denied_symlink)
    target = tmp_path / "copy"
    assert directories.materialize_directory(source, target) == "copied_bytes_verified"
    assert directories.inventory(source) == directories.inventory(target)


def test_copy_fallback_does_not_hide_another_symlink_failure(tmp_path, monkeypatch):
    def different_error(*args, **kwargs):
        raise PermissionError("Other failure")

    monkeypatch.setattr(Path, "symlink_to", different_error)
    with pytest.raises(PermissionError, match="Other"):
        directories.materialize_directory(tmp_path, tmp_path / "copy")
    assert not (tmp_path / "copy").exists()


@pytest.mark.parametrize("changed", ["target", "source"])
def test_copy_fallback_rejects_any_input_or_output_mutation(tmp_path, monkeypatch, changed):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    (source / "original.bin").write_bytes(b"exact")
    copytree = directories.shutil.copytree

    def changing_copy(src, dst, *args, **kwargs):
        result = copytree(src, dst, *args, **kwargs)
        if Path(dst) == target:
            ((target if changed == "target" else source) / "original.bin").write_bytes(b"changed")
        return result

    monkeypatch.setattr(Path, "symlink_to", denied_symlink)
    monkeypatch.setattr(directories.shutil, "copytree", changing_copy)
    with pytest.raises(ValueError, match="changed while copying"):
        directories.materialize_directory(source, target)


@pytest.fixture
def historical_site(tmp_path, monkeypatch):
    site = tmp_path / "site"
    (site / "data/v1").mkdir(parents=True)
    config = tmp_path / scope.ANCHOR
    config.parent.mkdir(parents=True)
    config.write_text("{}")

    def entry(entity, period):
        return dict(entity_key=entity, period_id=period, version=entity)

    retained = [entry(e, "2026Q2") for e in scope.ENTITIES]
    superseded = [entry(e, "2026Q3") for e in scope.ENTITIES - {"INDUSTRY"}]
    new = [entry(e, "2026Q3") for e in scope.ENTITIES]
    historical = site / "data/v1/history.json"
    historical.write_bytes(b'{"historical":true}')
    market = site / "data/v1/market.json"
    market.write_bytes(b'{"new":true}')
    (site / "index.html").write_bytes(b"new")
    old = dict(
        analysis_manifest=retained + superseded,
        files=[
            {
                "path": "data/v1/history.json",
                "sha256": scope.sha(historical.read_bytes()),
                "bytes": historical.stat().st_size,
            }
        ],
    )
    spec = dict(
        baseline_commit="a" * 40,
        baseline_manifest_sha256="b" * 64,
        retained_analysis_manifest=retained,
        superseded_analysis_manifest=superseded,
        analysis_manifest=new,
        contracts={},
        data_files=[
            dict(
                path="data/v1/market.json", sha256=scope.sha(market.read_bytes()), bytes=market.stat().st_size
            )
        ],
        frontend_files=[dict(path="index.html", sha256=scope.sha(b"new"), bytes=3)],
    )
    (site / scope.PROOF).write_text(
        json.dumps(
            dict(
                schema_version="quarterly_story_publication_v1",
                anchor_sha256=scope.sha(config.read_bytes()),
                historical_source_status="superseded_Q3_source_not_replayed_not_consumed",
                remote_witness=dict(
                    baseline_commit="a" * 40,
                    manifest_sha256="b" * 64,
                    files_verified=1,
                    origin=scope.transport.ORIGIN,
                    deployment_run=123,
                    deployment_commit="c" * 40,
                ),
            )
        )
    )
    manifest = dict(
        analysis_manifest=sorted(retained + new, key=scope.manifests.analysis_sort_key), contracts={}
    )
    (site / scope.manifests.MANIFEST_NAME).write_text(json.dumps(manifest))
    monkeypatch.setattr(scope.transport, "baseline", lambda *args: (old, b"{}"))
    monkeypatch.setattr(scope.transport, "_git", lambda *args: b"")
    assert scope.preserved_files(site, tmp_path, spec) == frozenset({"data/v1/history.json"})
    return site, tmp_path, spec


@pytest.mark.parametrize("mutation", ["changed", "missing", "extra", "contracts", "frontend", "new_data"])
def test_historical_and_reviewed_site_bytes_cannot_be_changed(historical_site, mutation):
    site, repo, spec = historical_site
    if mutation == "changed":
        (site / "data/v1/history.json").write_bytes(b'{"historical":false}')
    elif mutation == "missing":
        (site / "data/v1/history.json").unlink()
    elif mutation == "extra":
        (site / "undeclared.json").write_text("{}")
    elif mutation == "frontend":
        (site / "index.html").write_bytes(b"changed")
    elif mutation == "new_data":
        (site / "data/v1/market.json").write_bytes(b'{"new":false}')
    else:
        path = site / scope.manifests.MANIFEST_NAME
        manifest = json.loads(path.read_bytes())
        manifest["contracts"] = {"unknown.schema.json": "f" * 64}
        path.write_text(json.dumps(manifest))
    with pytest.raises((ValueError, OSError)):
        scope.preserved_files(site, repo, spec)


def test_retained_q2_revocation_between_final_inspection_and_lock_prevents_swap(tmp_path, monkeypatch):
    site = tmp_path / "site"
    site.mkdir()
    dist = tmp_path / "dist"
    dist.mkdir()
    config = tmp_path / scope.ANCHOR
    config.parent.mkdir(parents=True)
    config.write_text("{}")
    payload = dict(entity_key="AEROMEXICO", period_id="2026Q3")
    output = {"data/v1/analysis/AEROMEXICO/2026Q3.json": data.encoded(payload)}
    inspected = dict(retained_analysis_manifest=[], superseded_analysis_manifest=[])
    spec = dict(
        scope=inspected,
        baseline_commit="a" * 40,
        authorization_sha256="b" * 64,
        independent_audit_sha256="c" * 64,
        data_files=update.pins(output),
        frontend_files=[],
    )
    state = dict(inspections=0, revoked=False, locked=False)

    def inspect(_):
        state["inspections"] += 1
        if state["inspections"] == 2:
            state["revoked"] = True
        return inspected, {}, {"sources": {}}, [], []

    @contextmanager
    def writer(_):
        state["locked"] = True
        try:
            yield
        finally:
            state["locked"] = False

    def historical(*args):
        assert state["locked"] and state["revoked"]
        raise ValueError("Retained Q2 approval was revoked before swap")

    monkeypatch.setattr(update, "PATHS", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(update, "anchor", lambda: spec)
    monkeypatch.setattr(update, "inspect", inspect)
    monkeypatch.setattr(update, "authority", lambda *args: ("b" * 64, "c" * 64))
    monkeypatch.setattr(update.gate, "verify_records", lambda _: [({}, {}, {"source_packages": {}}, {})])
    monkeypatch.setattr(update.gate, "_analysis_payload", lambda *args: payload)
    monkeypatch.setattr(update, "_build", lambda _: dist)
    monkeypatch.setattr(update.transport, "frontend_entries", lambda _: [])
    monkeypatch.setattr(update.transport, "witness_remote", lambda *args: {})
    monkeypatch.setattr(update.transport, "baseline", lambda *args: ({}, b"{}"))
    monkeypatch.setattr(update.flow, "writer", writer)
    monkeypatch.setattr(update, "historical_approvals", historical)
    assemble = Mock()
    monkeypatch.setattr(update.gate, "assemble_site", assemble)
    with pytest.raises(ValueError, match="Q2 approval was revoked"):
        update.publish(tmp_path / "request.json", site)
    assemble.assert_not_called()
