"""``python -m src.publish.verify site/`` — CI-safe, no private data needed.

Checks, in order (each failure is printed and every check runs before
exiting non-zero, so one run names everything wrong):

1. ``publication_manifest.json`` exists and matches
   ``contracts/web/publication_manifest.schema.json``.
2. Every file the manifest lists exists under ``site/`` with the exact
   SHA-256 and byte size recorded.
3. No file exists under ``site/`` that the manifest does not list (besides
   the manifest itself).
4. Every ``data/v1/**/*.json`` file validates against its
   ``contracts/web/*.schema.json`` sub-schema (see
   ``src/web_export/schemas.py``) and against
   ``contracts/web/privacy.yaml`` (forbidden fields, disallowed carriers).
5. Every ``analysis_manifest`` entry has the required string fields
   (schema already enforces this; this only adds the readable message).

Only reads what is public and versioned: ``site/`` itself and
``contracts/web/``. Never touches ``analysis_runs/``, ``data/gold`` or any
secret — this is exactly what ``.github/workflows/pages.yml`` runs before
deploying, with no local data restored.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.config import PATHS
from src.web_export.privacy import find_disallowed_carriers, find_forbidden_fields, load_privacy_rules
from src.web_export.schemas import ANALYSIS_SCHEMA, EXECUTIVE_SCHEMA, NETWORK_FILE_SCHEMA, QUARTERS_FILE_SCHEMA

from . import manifest as manifest_mod

CONTRACTS_DIR = PATHS.root / "contracts" / "web"
MANIFEST_SCHEMA_PATH = CONTRACTS_DIR / "publication_manifest.schema.json"


class SiteVerificationError(RuntimeError):
    """One or more checks failed; the caller has already printed every one."""


def _sha256_file(path: Path) -> str:
    return manifest_mod.sha256_file(path)


def _data_schema_for(rel_path: str) -> dict[str, Any] | None:
    """Which contracts/web sub-schema this data/v1 file must satisfy, or
    None if it is not a data file this gate validates (e.g. it is part of
    the built web/ bundle, not exported data)."""

    parts = rel_path.split("/")
    if parts[:2] != ["data", "v1"]:
        return None
    if parts[2:] == ["executive.json"]:
        return EXECUTIVE_SCHEMA
    if parts[2:3] == ["flights"] and parts[3:] == ["quarters.json"]:
        return QUARTERS_FILE_SCHEMA
    if parts[2:3] == ["flights"] and parts[3:4] in (["domestic"], ["international"]) and len(parts) == 5:
        return NETWORK_FILE_SCHEMA
    if parts[2:3] == ["analysis"] and len(parts) == 4:
        return ANALYSIS_SCHEMA
    return None


def verify_site(site_dir: Path) -> list[str]:
    """Return the list of problems found (empty means the site is valid)."""

    site_dir = Path(site_dir)
    problems: list[str] = []

    manifest_path = site_dir / manifest_mod.MANIFEST_NAME
    if not manifest_path.is_file():
        return [f"{manifest_path} is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [f"{manifest_path} is not valid JSON: {error}"]

    if not MANIFEST_SCHEMA_PATH.is_file():
        return [f"{MANIFEST_SCHEMA_PATH} is missing; cannot verify the manifest's own shape"]
    manifest_schema = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(manifest_schema)
    schema_errors = [f"manifest {list(e.path)}: {e.message}" for e in validator.iter_errors(manifest)]
    if schema_errors:
        # A manifest that doesn't match its own schema cannot be trusted for
        # the per-file checks below (e.g. "files" might not even be a list).
        return schema_errors

    listed_paths = {entry["path"]: entry for entry in manifest["files"]}

    actual_paths = set()
    for path in sorted(p for p in site_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(site_dir).as_posix()
        if rel == manifest_mod.MANIFEST_NAME:
            continue
        actual_paths.add(rel)
        entry = listed_paths.get(rel)
        if entry is None:
            problems.append(f"unlisted file present on disk, not in manifest: {rel}")
            continue
        size = path.stat().st_size
        if size != entry["bytes"]:
            problems.append(f"{rel}: size on disk is {size} bytes, manifest says {entry['bytes']}")
            continue
        digest = _sha256_file(path)
        if digest != entry["sha256"]:
            problems.append(f"{rel}: SHA-256 on disk ({digest}) does not match manifest ({entry['sha256']})")

    for rel in listed_paths:
        if rel not in actual_paths:
            problems.append(f"manifest lists {rel}, which is missing on disk")

    rules = load_privacy_rules()
    for rel in sorted(actual_paths):
        schema = _data_schema_for(rel)
        if schema is None:
            continue
        path = site_dir / rel
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            problems.append(f"{rel}: not valid JSON: {error}")
            continue
        data_validator = Draft202012Validator(schema)
        errors = [f"{rel} {list(e.path)}: {e.message}" for e in data_validator.iter_errors(payload)]
        problems.extend(errors)
        forbidden = find_forbidden_fields(payload, rules["forbidden_fields"])
        carriers = find_disallowed_carriers(payload, rules["allowed_estimated_carriers"])
        for field in forbidden:
            problems.append(f"{rel}: forbidden field present: {field}")
        for carrier in carriers:
            problems.append(f"{rel}: disallowed carrier_key: {carrier}")

    for index, entry in enumerate(manifest["analysis_manifest"]):
        for field in ("period_id", "version", "content_hash", "evidence_fingerprint", "approval_event", "audit_hash"):
            value = entry.get(field)
            if not isinstance(value, str) or not value:
                problems.append(f"analysis_manifest[{index}]: {field!r} is missing or not a non-empty string")

    return problems


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site_dir", type=Path, nargs="?", default=PATHS.root / "site")
    args = parser.parse_args(argv)

    problems = verify_site(args.site_dir)
    if problems:
        print(f"src.publish.verify: {args.site_dir} failed {len(problems)} check(s):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"src.publish.verify: {args.site_dir} is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
