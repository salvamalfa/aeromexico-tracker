"""Build and load ``site/publication_manifest.json``.

The manifest is the signed object described in
``docs/arquitectura/auditoria-arquitectura-20260926.md`` §4.2 punto 5: the
code commit, each ``contracts/web/`` file's own SHA-256 (its "version"),
every other file under ``site/`` with its SHA-256 and byte size, and the
analysis-manifest entries (``period_id``, ``version``, ``content_hash``,
``evidence_fingerprint``, ``approval_event``, ``audit_hash``) the currently
published page also carries (``stage18.consumer_html``'s
``#analysis-manifest``). See ``src/publish/README.md``.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import PATHS
from src.web_export.writer import dumps_deterministic

CONTRACTS_DIR = PATHS.root / "contracts" / "web"
SCHEMA_VERSION = "publication_manifest_v1"
MANIFEST_NAME = "publication_manifest.json"

# Files that describe the public data/contract boundary, not the site's own
# build output. Their own content hash stands in for "the contract version"
# (no separate version field is embedded in every schema file today).
CONTRACT_FILES = (
    "flights.schema.json",
    "executive.schema.json",
    "analysis.schema.json",
    "publication_manifest.schema.json",
    "privacy.yaml",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_commit(root: Path = PATHS.root) -> str:
    """The code commit this build was produced from.

    Fails loudly rather than writing a manifest that cannot be traced to a
    commit: a publish gate run from a dirty/detached tree is a real question
    for the operator, not something to paper over with "unknown".
    """

    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"git rev-parse HEAD failed in {root}: {result.stderr.strip()}")
    return result.stdout.strip()


def contract_hashes(contracts_dir: Path = CONTRACTS_DIR) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for name in CONTRACT_FILES:
        path = contracts_dir / name
        if not path.is_file():
            raise FileNotFoundError(f"contract file missing: {path}")
        hashes[name] = sha256_file(path)
    return hashes


def file_entries(site_dir: Path, *, exclude: tuple[str, ...] = (MANIFEST_NAME,)) -> list[dict[str, Any]]:
    """Every file under site_dir except the ones in exclude, sorted by path."""

    excluded = set(exclude)
    entries: list[dict[str, Any]] = []
    for path in sorted(p for p in site_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(site_dir).as_posix()
        if rel in excluded:
            continue
        entries.append({"path": rel, "sha256": sha256_file(path), "bytes": path.stat().st_size})
    return entries


def build_manifest(
    site_dir: Path,
    analysis_manifest: list[dict[str, str]],
    *,
    code_commit: str | None = None,
    contracts_dir: Path = CONTRACTS_DIR,
    generated_at: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "code_commit": code_commit if code_commit is not None else current_commit(),
        "generated_at": generated_at if generated_at is not None else datetime.now(timezone.utc).isoformat(),
        "contracts": contract_hashes(contracts_dir),
        "files": file_entries(site_dir),
        "analysis_manifest": sorted(analysis_manifest, key=lambda e: e["period_id"]),
    }


def manifest_hash(manifest: dict[str, Any]) -> str:
    """Hash of hashes: the receipt in analysis_runs/publications/ signs this,
    not the raw site/ bytes, since the manifest already lists every file's
    own hash."""

    return hashlib.sha256(dumps_deterministic(manifest).encode("utf-8")).hexdigest()


def write_manifest(site_dir: Path, manifest: dict[str, Any]) -> Path:
    path = site_dir / MANIFEST_NAME
    path.write_text(dumps_deterministic(manifest) + "\n", encoding="utf-8")
    return path


def load_manifest(site_dir: Path) -> dict[str, Any]:
    path = site_dir / MANIFEST_NAME
    return json.loads(path.read_text(encoding="utf-8"))
