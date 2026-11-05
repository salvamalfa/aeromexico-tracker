"""Official data must pass the same published manifest boundary as other chat data."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys

import pytest

from src.conversational_analytics.data.snapshot import Snapshot, SnapshotError
from src.dashboard.official_routes_contract import PUBLIC_PATH
from tests.test_chat_docker_context import _materialize_runtime_copy
from tests.test_chat_official_routes import ROOT, document


def publish_fixture(site, doc):
    path = site / PUBLIC_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(doc, ensure_ascii=False).encode()
    path.write_bytes(raw)
    manifest_path = site / "publication_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["files"] = [row for row in manifest["files"] if row["path"] != PUBLIC_PATH]
    manifest["files"].append(
        {"path": PUBLIC_PATH, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    )
    manifest["contracts"]["official-routes.schema.json"] = hashlib.sha256(
        (ROOT / "contracts/web/official-routes.schema.json").read_bytes()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def fixture_site(tmp_path):
    site = tmp_path / "site"
    shutil.copytree(ROOT / "tests/fixtures/chat/site", site)
    return site


def test_legacy_snapshot_stays_loadable_and_official_data_changes_conversation_versions(tmp_path):
    site = fixture_site(tmp_path)
    legacy = Snapshot(site)
    manifest = publish_fixture(site, document())
    official = Snapshot(site)
    assert legacy.version != official.version
    assert legacy.semantic_version != official.semantic_version
    assert official.payload(PUBLIC_PATH)["dataset_version"] == document()["dataset_version"]
    assert official.manifest["files"] == manifest["files"]
    assert legacy.catalog() == official.catalog()
    for entry in legacy.manifest["files"]:
        if entry["path"].startswith("data/"):
            assert legacy.payload(entry["path"]) == official.payload(entry["path"])


def test_official_payload_requires_declared_exact_contract(tmp_path):
    site = fixture_site(tmp_path)
    manifest = publish_fixture(site, document())
    del manifest["contracts"]["official-routes.schema.json"]
    (site / "publication_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SnapshotError, match="contrato exacto"):
        Snapshot(site)


def test_file_tamper_rejected_before_payload_is_exposed(tmp_path):
    site = fixture_site(tmp_path)
    publish_fixture(site, document())
    path = site / PUBLIC_PATH
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(SnapshotError, match="Hash o tamaño"):
        Snapshot(site)


def test_modified_content_with_fresh_manifest_but_stale_canonical_identity_rejected(tmp_path):
    site = fixture_site(tmp_path)
    doc = document()
    doc["networks"][0]["routes"][0]["departures"] = 7
    publish_fixture(site, doc)
    with pytest.raises(SnapshotError, match="identidad"):
        Snapshot(site)


def test_unknown_contract_hash_rejected_without_current_schema_fallback(tmp_path):
    site = fixture_site(tmp_path)
    manifest = publish_fixture(site, document())
    manifest["contracts"]["official-routes.schema.json"] = "0" * 64
    (site / "publication_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(SnapshotError, match="Hash de contrato"):
        Snapshot(site)


def test_runtime_copy_queries_official_data_without_private_checkout_imports(tmp_path):
    _materialize_runtime_copy(tmp_path)
    # Replace only the copied test site's data. This never changes the published checkout.
    shutil.rmtree(tmp_path / "site")
    shutil.copytree(ROOT / "tests/fixtures/chat/site", tmp_path / "site")
    publish_fixture(tmp_path / "site", document())
    assert (tmp_path / "src/dashboard/official_routes_contract.py").is_file()
    assert not (tmp_path / "src/dashboard/official_routes.py").exists()
    environment = {**os.environ, "PYTHONPATH": str(tmp_path)}
    environment.pop("OPENAI_API_KEY", None)
    code = """import socket,sys
from pathlib import Path
from types import SimpleNamespace
def refuse(*args,**kwargs): raise AssertionError('network prohibited')
socket.create_connection=refuse
socket.socket.connect=refuse
from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.tools.registry import ToolRegistry
s=Snapshot(Path('site'))
v=s.payload('data/v1/official-routes.json')['dataset_version']
t=ToolRegistry(s,SimpleNamespace(enable_official_route_tools=True,official_route_dataset_sha256=v))
r=t.invoke('query_official_routes',{'period':'2026Q3','scope':'national'})
assert r['total_departures']==6
assert r['dataset_version']==v
assert 'src.dashboard.official_routes' not in sys.modules
assert 'src.web_export.flights' not in sys.modules
assert 'pandas' not in sys.modules
print('official runtime: verified; no provider or private source access')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "official runtime: verified" in result.stdout
