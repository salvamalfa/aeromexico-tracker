"""The real published analysis bytes keep their declared, identity-bound contracts."""

import copy
import hashlib
import json
from pathlib import Path

import pytest

from src.conversational_analytics.data.snapshot import Snapshot, SnapshotError

ROOT = Path(__file__).resolve().parents[1]
AERO_Q3 = "data/v1/analysis/AEROMEXICO/2026Q3.json"
INDUSTRY_Q3 = "data/v1/analysis/INDUSTRY/2026Q3.json"
GLOBE = "https://www.globenewswire.com/fr/news-release/2026/10/19/3383928/0/en/aerom%C3%A9xico-reports-unaudited-third-quarter-2026-results.html"


def analysis_site(tmp_path):
    source = ROOT / "site"
    site = tmp_path / "site"
    manifest = json.loads((source / "publication_manifest.json").read_bytes())
    manifest["files"] = [row for row in manifest["files"] if row["path"].startswith("data/v1/analysis/")]
    for row in manifest["files"]:
        target = site / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / row["path"]).read_bytes())
    write_manifest(site, manifest)
    return site, manifest


def write_manifest(site, manifest):
    (site / "publication_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def rewrite_payload(site, manifest, name, payload):
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    (site / name).write_bytes(raw)
    row = next(row for row in manifest["files"] if row["path"] == name)
    row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    write_manifest(site, manifest)


def test_real_namespaced_q3_and_original_q2_load_with_their_published_contracts(tmp_path):
    site, _ = analysis_site(tmp_path)
    snapshot = Snapshot(site)
    assert snapshot.payload(AERO_Q3)["entity_key"] == "AEROMEXICO"
    assert snapshot.payload(INDUSTRY_Q3)["entity_key"] == "INDUSTRY"
    assert snapshot.payload("data/v1/analysis/2026Q2.json")["period_id"] == "2026Q2"
    assert any(
        citation["href"].startswith("https://www.globenewswire.com/")
        for claim in snapshot.payload(AERO_Q3)["claims"]
        for citation in claim["citations"]
    )


@pytest.mark.parametrize(
    "contract", ["analysis_editorial.schema.json", "analysis_industry_story.schema.json"]
)
def test_additional_q3_contract_is_required_without_generic_fallback(tmp_path, contract):
    site, manifest = analysis_site(tmp_path)
    del manifest["contracts"][contract]
    write_manifest(site, manifest)
    with pytest.raises(SnapshotError, match="requires its declared contract"):
        Snapshot(site)


def test_declared_contract_hash_is_still_verified(tmp_path):
    site, manifest = analysis_site(tmp_path)
    manifest["contracts"]["analysis_editorial.schema.json"] = "0" * 64
    write_manifest(site, manifest)
    with pytest.raises(SnapshotError, match="Hash de contrato distinto"):
        Snapshot(site)


def test_q2_keeps_its_historical_citation_domain_boundary(tmp_path):
    site, manifest = analysis_site(tmp_path)
    name = "data/v1/analysis/2026Q2.json"
    payload = json.loads((site / name).read_bytes())
    claim = next(claim for claim in payload["claims"] if claim["citations"])
    claim["citations"][0]["href"] = GLOBE
    rewrite_payload(site, manifest, name, payload)
    with pytest.raises(SnapshotError, match="does not match"):
        Snapshot(site)


@pytest.mark.parametrize(
    "field,value",
    [
        ("entity_key", "INDUSTRY"),
        ("period_id", "2026Q2"),
        *[
            (field, "0" * 64)
            for field in ("version", "content_hash", "evidence_fingerprint", "approval_event", "audit_hash")
        ],
    ],
)
def test_payload_headers_cannot_select_another_contract_or_approval(tmp_path, field, value):
    site, manifest = analysis_site(tmp_path)
    payload = json.loads((site / AERO_Q3).read_bytes())
    payload[field] = value
    rewrite_payload(site, manifest, AERO_Q3, payload)
    with pytest.raises(SnapshotError, match="differs from its published identity"):
        Snapshot(site)


def test_unlisted_analysis_endpoint_cannot_choose_a_contract(tmp_path):
    site, manifest = analysis_site(tmp_path)
    manifest["analysis_manifest"] = [
        row for row in manifest["analysis_manifest"] if row.get("entity_key") != "INDUSTRY"
    ]
    write_manifest(site, manifest)
    with pytest.raises(SnapshotError, match="absent from its published manifest"):
        Snapshot(site)


def test_invalid_payload_identity_is_rejected(tmp_path):
    site, manifest = analysis_site(tmp_path)
    payload = json.loads((site / AERO_Q3).read_bytes())
    payload["entity_key"] = "UNDECLARED"
    rewrite_payload(site, manifest, AERO_Q3, payload)
    with pytest.raises(SnapshotError, match="Invalid analysis payload identity"):
        Snapshot(site)


def test_cached_payload_validation_does_not_skip_manifest_identity_checks(tmp_path):
    site, manifest = analysis_site(tmp_path)
    Snapshot(site)
    changed = copy.deepcopy(manifest)
    entry = next(row for row in changed["analysis_manifest"] if row.get("entity_key") == "AEROMEXICO")
    entry["version"] = "0" * 64
    write_manifest(site, changed)
    with pytest.raises(SnapshotError, match="differs from its published identity"):
        Snapshot(site)
