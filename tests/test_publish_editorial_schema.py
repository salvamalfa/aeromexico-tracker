"""Scoped editorial schema preserves historical contracts in exporter and chat."""

import hashlib
import json
import shutil

import pytest

from src.publish import editorial as e


def encoded(value):
    return json.dumps(value, sort_keys=True).encode()


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def resign_site(site):
    """Attacker can regenerate their own inventory; this must grant no authority."""
    p = site / "publication_manifest.json"
    m = json.loads(p.read_bytes())
    m["files"] = [
        {
            "path": x.relative_to(site).as_posix(),
            "bytes": len(x.read_bytes()),
            "sha256": hashlib.sha256(x.read_bytes()).hexdigest(),
        }
        for x in site.rglob("*")
        if x.is_file() and x.name != "publication_manifest.json"
    ]
    put(p, encoded(m))


@pytest.fixture
def editorial_schema_site(tmp_path):
    from pathlib import Path

    source = Path(__file__).parent / "fixtures/site/valid"
    site = tmp_path / "public-schema-site"
    shutil.copytree(source, site)
    payload = json.loads((site / "data/v1/analysis/2026Q2.json").read_bytes())
    payload.update(period_id="2026Q3", version="fixture-editorial-version")
    payload["claims"][0]["citations"][0]["href"] = "https://www.globenewswire.com/issuer-original"
    put(site / e.ANALYSIS, encoded(payload))
    manifest_path = site / "publication_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    entry = {**manifest["analysis_manifest"][0], "period_id": "2026Q3", "version": payload["version"]}
    manifest["analysis_manifest"].append(entry)
    contract = (e.PATHS.root / "contracts/web" / e.manifests.EDITORIAL_ANALYSIS_CONTRACT).read_bytes()
    manifest["contracts"][e.manifests.EDITORIAL_ANALYSIS_CONTRACT] = hashlib.sha256(contract).hexdigest()
    put(manifest_path, encoded(manifest))
    resign_site(site)
    return site


def test_new_primary_domain_is_valid_only_with_scoped_editorial_contract(editorial_schema_site):
    from src.publish.verify import verify_site

    assert verify_site(editorial_schema_site) == []


def test_normal_verifier_requires_editorial_contract_for_new_endpoint(editorial_schema_site):
    from src.publish.verify import verify_site

    path = editorial_schema_site / "publication_manifest.json"
    manifest = json.loads(path.read_bytes())
    del manifest["contracts"][e.manifests.EDITORIAL_ANALYSIS_CONTRACT]
    put(path, encoded(manifest))
    assert any(
        e.manifests.EDITORIAL_ANALYSIS_CONTRACT in issue for issue in verify_site(editorial_schema_site)
    )


def test_new_contract_does_not_change_retained_historical_schema(editorial_schema_site):
    from src.publish.verify import verify_site

    path = editorial_schema_site / "data/v1/analysis/2026Q2.json"
    payload = json.loads(path.read_bytes())
    payload["claims"][0]["citations"][0]["href"] = "https://www.globenewswire.com/issuer-original"
    put(path, encoded(payload))
    resign_site(editorial_schema_site)
    assert any("2026Q2.json" in issue for issue in verify_site(editorial_schema_site))


def test_snapshot_requires_editorial_contract_for_new_endpoint(editorial_schema_site):
    from src.conversational_analytics.data.snapshot import Snapshot, SnapshotError

    payload_path = editorial_schema_site / e.ANALYSIS
    payload = json.loads(payload_path.read_bytes())
    payload["claims"][0]["citations"][0]["href"] = "https://www.sec.gov/example"
    put(payload_path, encoded(payload))
    resign_site(editorial_schema_site)
    path = editorial_schema_site / "publication_manifest.json"
    manifest = json.loads(path.read_bytes())
    del manifest["contracts"][e.manifests.EDITORIAL_ANALYSIS_CONTRACT]
    put(path, encoded(manifest))
    with pytest.raises(SnapshotError, match="editorial|Editorial|analysis_editorial"):
        Snapshot(editorial_schema_site)


def test_snapshot_accepts_scoped_schema_and_rejects_wrong_pinned_hash(editorial_schema_site):
    from src.conversational_analytics.data.snapshot import Snapshot, SnapshotError

    Snapshot(editorial_schema_site)
    path = editorial_schema_site / "publication_manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["contracts"][e.manifests.EDITORIAL_ANALYSIS_CONTRACT] = "f" * 64
    put(path, encoded(manifest))
    with pytest.raises(SnapshotError, match="Hash de contrato"):
        Snapshot(editorial_schema_site)


@pytest.mark.parametrize("field,value", [("period_id", "2026Q2"), ("entity_key", "VOLARIS")])
def test_editorial_contract_cannot_authorize_another_identity(editorial_schema_site, field, value):
    from jsonschema import Draft202012Validator

    schema = json.loads(
        (e.PATHS.root / "contracts/web" / e.manifests.EDITORIAL_ANALYSIS_CONTRACT).read_bytes()
    )
    payload = json.loads((editorial_schema_site / e.ANALYSIS).read_bytes())
    payload[field] = value
    assert list(Draft202012Validator(schema).iter_errors(payload))


def test_optional_editorial_contract_is_not_applied_to_another_entity_endpoint(editorial_schema_site):
    from src.publish.verify import verify_site

    site = editorial_schema_site
    payload = json.loads((site / e.ANALYSIS).read_bytes())
    payload.update(
        entity_key="VOLARIS",
        period_label="3T26",
        cutoff_date="2026-10-24",
        selection_mode="retrospective",
        guidance_as_of="report_date",
    )
    (site / e.ANALYSIS).unlink()
    other = "data/v1/analysis/VOLARIS/2026Q3.json"
    put(site / other, encoded(payload))
    path = site / "publication_manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["analysis_manifest"][-1]["entity_key"] = "VOLARIS"
    put(path, encoded(manifest))
    resign_site(site)
    assert any(other in issue and "href" in issue for issue in verify_site(site))
