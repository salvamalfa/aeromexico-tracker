"""Exercise the issuer publisher's real frontend guard after a fare/UI release.

Private source/approval replay and network calls have deterministic boundaries;
the publisher, frontend closure comparison, historical-byte scope and atomic
site assembly are real. In particular, no replacement frontend guard can make
these tests pass while publish_issuer still rejects the inherited marker.
"""

import json
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from src.publish import editorial as transport
from src.publish import issuer_scope, issuer_update as update
from src.publish import manifest as manifests
from src.publish import presentation_release as presentation


@pytest.fixture
def issuer(tmp_path, monkeypatch, request):
    from src.analysis_agent import entity_adapter
    from src.publish import gate, issuer_authority, verify

    site = tmp_path / "site"
    (site / "data/v1").mkdir(parents=True)
    (site / "assets").mkdir()
    html = b'<html><head><script src="assets/app.js"></script></head><body>dashboard</body></html>'
    marker = {
        "schema_version": presentation.PRESENTATION_RECEIPT_SCHEMA,
        "baseline_commit": "a" * 40,
        "baseline_manifest_sha256": "b" * 64,
        "source_producer_commit": "c" * 40,
        "source_producer_code_version": "d" * 64,
        "frontend_commit": "e" * 40,
    }
    has_marker = getattr(request, "param", True)
    (site / "index.html").write_bytes(
        presentation.embed_presentation_receipt(html, marker) if has_marker else html
    )
    (site / "assets/app.js").write_bytes(b"const dashboard = 'unchanged';")
    executive = b'{"financial":"unchanged"}'
    (site / update.EXECUTIVE).write_bytes(executive)
    for name in ("fare-quotes-publication.json", "afac-history-publication.json"):
        (site / name).write_bytes(b'{"inherited":"receipt"}')
    old = {
        "analysis_manifest": [], "contracts": {}, "code_commit": "e" * 40,
        "files": manifests.file_entries(site),
    }
    manifests.write_manifest(site, old)
    baseline_files = {p.relative_to(site).as_posix(): p.read_bytes() for p in site.rglob("*") if p.is_file()}
    spec = {
        "baseline_commit": "f" * 40,
        "baseline_manifest_sha256": update.sha((site / manifests.MANIFEST_NAME).read_bytes()),
        "producer_code_version": "1" * 64,
        "stage": "data_only", "analysis_entry": None, "previous_entry": None,
        "entity_key": "VIVA_AEROBUS", "period_id": "2026Q3",
        "executive_sha256": update.sha(executive), "executive_bytes": len(executive),
    }
    anchor = tmp_path / update.ANCHOR
    anchor.parent.mkdir(parents=True)
    anchor.write_text(json.dumps(spec))
    package = tmp_path / "package.json"
    package.write_text("{}")
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_bytes(html)
    (dist / "assets/app.js").write_bytes((site / "assets/app.js").read_bytes())
    witness = {
        "baseline_commit": spec["baseline_commit"],
        "manifest_sha256": spec["baseline_manifest_sha256"],
        "files_verified": len(old["files"]), "origin": transport.ORIGIN,
        "deployment_run": 123, "deployment_commit": spec["baseline_commit"],
    }
    calls = []

    def history(*_args):
        calls.append("historical_authority")
        return old

    def git(_repo, *args):
        if args[0] == "show":
            return baseline_files[args[1].split(":site/", 1)[1]]
        if args[0] == "ls-remote":
            return spec["baseline_commit"].encode()
        return b""

    monkeypatch.setattr(update, "PATHS", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(update, "anchor", lambda *_: spec)
    monkeypatch.setattr(update, "verify_historical_baseline", history)
    monkeypatch.setattr(update, "verify_approval_cohorts", lambda *_: {"authorized": []})
    monkeypatch.setattr(transport, "baseline", lambda *_: (old, b""))
    monkeypatch.setattr(transport, "witness_remote", lambda *_: witness)
    monkeypatch.setattr(transport, "_git", git)
    monkeypatch.setattr(entity_adapter, "code_version", lambda: spec["producer_code_version"])
    monkeypatch.setattr(issuer_authority, "verified_data", lambda *_: (executive, {}))
    monkeypatch.setattr(issuer_authority, "input_snapshot", lambda *_: {"source": "fixed"})
    monkeypatch.setattr(issuer_scope, "require_scope", lambda *_: None)
    monkeypatch.setattr(manifests, "refuse_if_build_inputs_dirty", lambda: None)
    monkeypatch.setattr(manifests, "current_commit", lambda *_: "2" * 40)
    monkeypatch.setattr(gate.flow, "writer", lambda *_: nullcontext())
    monkeypatch.setattr(gate, "_trusted_site_commit", lambda *_: spec["baseline_commit"])
    monkeypatch.setattr(gate, "require_trusted_site_baseline", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(gate, "load_records", lambda *_: [])
    monkeypatch.setattr(gate, "WEB_DATA_V1", tmp_path / "web/public/data/v1")
    monkeypatch.setattr(gate, "build_web", lambda: calls.append("build") or dist)
    monkeypatch.setattr(gate, "write_receipt", lambda *_: {"written": True})
    monkeypatch.setattr(verify, "_verify_site", lambda *_args, **_kwargs: [])
    return SimpleNamespace(**locals())


@pytest.mark.parametrize("issuer", [True, False], indirect=True)
def test_real_issuer_gate_preserves_marker_receipts_and_frontend(issuer):
    e = issuer
    assert (transport.frontend_entries(e.dist) != transport.frontend_entries(e.site)) == e.has_marker
    result = update.publish_issuer([], e.site, package_path=e.package)
    assert result["receipt"]["written"]
    assert e.calls[:2] == ["historical_authority", "build"]
    for name, raw in e.baseline_files.items():
        if name != manifests.MANIFEST_NAME:
            assert (e.site / name).read_bytes() == raw
    assert presentation.read_presentation_receipt(e.site) == (e.marker if e.has_marker else None)
    assert (e.site / update.PROOF).exists()


@pytest.mark.parametrize("change", ["html", "asset", "foreign_marker", "duplicate_marker"])
def test_real_issuer_gate_still_refuses_interface_or_marker_changes(issuer, change):
    e = issuer
    if change == "asset":
        (e.dist / "assets/app.js").write_bytes(b"changed dashboard")
    elif change == "html":
        (e.dist / "index.html").write_bytes(e.html.replace(b"dashboard", b"changed"))
    else:
        raw = presentation.embed_presentation_receipt(e.html, {**e.marker, "frontend_commit": "9" * 40})
        (e.dist / "index.html").write_bytes(raw if change == "foreign_marker" else raw + raw)
    with pytest.raises((ValueError, update.PublicationRefused), match="unchanged dashboard frontend|already contains"):
        update.publish_issuer([], e.site, package_path=e.package)
    assert {p.relative_to(e.site).as_posix(): p.read_bytes() for p in e.site.rglob("*") if p.is_file()} == e.baseline_files


def test_inherited_marker_never_bypasses_historical_authority(issuer, monkeypatch):
    def refused(*_args):
        raise ValueError("historical marker or authority invalid")

    monkeypatch.setattr(update, "verify_historical_baseline", refused)
    with pytest.raises(ValueError, match="historical marker or authority invalid"):
        update.publish_issuer([], issuer.site, package_path=issuer.package)
    assert "build" not in issuer.calls
