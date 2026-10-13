from __future__ import annotations

import json
import shutil
from pathlib import Path

from src.publish import manifest as manifest_mod

ROOT = Path(__file__).resolve().parents[1]


def copy_pre_financial_snapshot(destination: Path) -> Path:
    """Copy site/ into tmp_path and remove only its separately approved overlay."""
    source = ROOT / "site"
    source_manifest = source / "publication_manifest.json"
    original_manifest = source_manifest.read_bytes()
    original_files = manifest_mod.file_entries(source)
    destination.mkdir(parents=True, exist_ok=True)
    site = destination / "site"
    shutil.copytree(source, site)
    manifest_path = site / "publication_manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    for name in ("business_metrics.json", "business_metrics.approval.json"):
        (site / "data/v1" / name).unlink(missing_ok=True)
    manifest["files"] = manifest_mod.file_entries(site)
    manifest["contracts"] = {
        name: digest
        for name, digest in manifest["contracts"].items()
        if name not in {"business_metrics.schema.json", "business_metrics_approval.schema.json"}
    }
    manifest_mod.write_manifest(site, manifest)
    source_unchanged = (
        source_manifest.read_bytes() == original_manifest
        and manifest_mod.file_entries(source) == original_files
    )
    if not source_unchanged:
        raise AssertionError("temporary snapshot preparation modified the source site")
    return site
