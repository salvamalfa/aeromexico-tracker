"""``python -m src.publish.verify site/`` — CI-safe, no private data needed.

Checks, in order (each failure is printed and every check runs before
exiting non-zero, so one run names everything wrong):

1. ``publication_manifest.json`` exists and matches
   ``contracts/web/publication_manifest.schema.json``.
2. The manifest's own structure is trustworthy: every listed ``contracts/
   web/*`` hash matches ``src.publish.manifest.contract_hashes()`` computed
   from this checkout or an explicitly retained exact version, ``files``
   includes ``index.html`` and at least one other asset,
   ``analysis_manifest`` is non-empty, and neither list
   contains a duplicate key (``path`` for ``files``, entity/period for
   ``analysis_manifest``).
3. Every file the manifest lists exists under ``site/`` with the exact
   SHA-256 and byte size recorded.
4. No file exists under ``site/`` that the manifest does not list (besides
   the manifest itself).
5. Every ``data/v1/**/*.json`` file validates against its
   ``contracts/web/*.schema.json`` sub-schema (see
   ``src/web_export/schemas.py``) and against
   ``contracts/web/privacy.yaml`` (forbidden fields, disallowed carriers,
   and the same ``max_file_size_bytes`` cap ``check_file_size`` enforces at
   export time). A ``data/v1/**/*.json`` file for which
   ``_data_schema_for()`` finds no sub-schema (i.e. it is not one of the
   files ``src/web_export`` is contracted to produce) is itself an error:
   the public data boundary is exactly what the contracts declare, nothing
   more.
6. Every ``analysis_manifest`` entry has the required string fields
   (schema already enforces this; this only adds the readable message) and
   matches, field for field, its own ``data/v1/analysis/<period_id>.json``
   file — the same fields ``src.publish.gate`` copies from
   ``consumer_payload``'s authorized output into both places, so a
   manifest entry that was edited independently of the file it claims to
   describe is caught here rather than trusted on the strength of the
   overall SHA-256/size check alone (which only proves the *file* wasn't
   altered after signing, not that the *manifest entry* was ever
   consistent with it).

Only reads what is public and versioned: ``site/`` itself and
``contracts/web/``. Never touches ``analysis_runs/``, ``data/gold`` or any
secret — this is exactly what ``.github/workflows/pages.yml`` runs before
deploying, with no local data restored.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.config import PATHS
from src.dashboard.route_entities import EXTRA_ROUTE_ENTITIES
from src.web_export.business_metrics import build_approved_payload
from src.web_export.contract_versions import resolve_contract
from src.web_export.privacy import (
    PrivacyViolation,
    check_file_size,
    find_disallowed_carriers,
    find_forbidden_fields,
    load_privacy_rules,
)
from src.web_export.schemas import (
    ANALYSIS_SCHEMA,
    BUSINESS_METRICS_APPROVAL_SCHEMA,
    BUSINESS_METRICS_SCHEMA,
    EXECUTIVE_SCHEMA,
    MARKET_SCHEMA,
    NETWORK_FILE_SCHEMA,
    QUARTERS_FILE_SCHEMA,
    split_flight_schemas,
)

from . import manifest as manifest_mod

ENTITY_KEYS = frozenset(entity.key for entity in EXTRA_ROUTE_ENTITIES)

CONTRACTS_DIR = PATHS.root / "contracts" / "web"
MANIFEST_SCHEMA_PATH = CONTRACTS_DIR / "publication_manifest.schema.json"


# (file sha256, schema digest) pairs that already validated cleanly in this
# process. Validation is deterministic for identical bytes and schema; only
# repeated in-process runs (the test suite) benefit, a CLI run is unchanged.
_CLEAN_DATA_FILES: set[tuple[str, str]] = set()


def _schema_digest(schema: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(schema, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


class SiteVerificationError(RuntimeError):
    """One or more checks failed; the caller has already printed every one."""


def _sha256_file(path: Path) -> str:
    return manifest_mod.sha256_file(path)


def _data_schema_for(
    rel_path: str,
    quarters_schema: dict[str, Any] = QUARTERS_FILE_SCHEMA,
    network_schema: dict[str, Any] = NETWORK_FILE_SCHEMA,
    analysis_schema: dict[str, Any] = ANALYSIS_SCHEMA,
) -> dict[str, Any] | None:
    """Which contracts/web sub-schema this data/v1 file must satisfy, or
    None if it is not a data file this gate validates (e.g. it is part of
    the built web/ bundle, not exported data)."""

    parts = rel_path.split("/")
    if parts[:2] != ["data", "v1"]:
        return None
    if parts[2:] == ["executive.json"]:
        return EXECUTIVE_SCHEMA
    if parts[2:] == ["market-demand.json"]:
        return json.loads((CONTRACTS_DIR / "market_demand.schema.json").read_text())
    if parts[2:] == ["market.json"]:
        return MARKET_SCHEMA
    if parts[2:3] == ["flights"] and parts[3:] == ["quarters.json"]:
        return quarters_schema
    if parts[2:3] == ["flights"] and parts[3:4] in (["domestic"], ["international"]) and len(parts) == 5:
        return network_schema
    # Dashboard v2: flights/entities/<KEY>/{domestic,international}/<period>.json,
    # only for the map entities src.web_export.flights writes.
    if (
        parts[2:4] == ["flights", "entities"]
        and len(parts) == 7
        and parts[4] in ENTITY_KEYS
        and parts[5] in ("domestic", "international")
    ):
        return network_schema
    if parts[2:3] == ["analysis"] and len(parts) == 4:
        return analysis_schema
    if parts[2:3] == ["analysis"] and len(parts) == 5 and parts[3] in manifest_mod.ANALYSIS_ENTITIES:
        return analysis_schema
    if parts[2:] == ["business_metrics.json"]:
        return BUSINESS_METRICS_SCHEMA
    if parts[2:] == ["news.json"]:
        return json.loads((CONTRACTS_DIR / "news.schema.json").read_text())
    if parts[2:] == ["business_metrics.approval.json"]:
        return BUSINESS_METRICS_APPROVAL_SCHEMA
    return None


def verify_site(site_dir: Path) -> list[str]:
    """Return the list of problems found (empty means the site is valid)."""
    return _verify_site(site_dir)


def _verify_site(site_dir: Path, *, preserved_approval_files: frozenset[str] = frozenset()) -> list[str]:
    """Shared structural checks; only editorial.verify_editorial may pass proven bytes.

    The normal public entry point above never exempts semantic approvals.
    """

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

    # --- (2) the manifest's own structure is trustworthy -------------------

    seen_file_paths: set[str] = set()
    duplicate_file_paths: set[str] = set()
    for entry in manifest["files"]:
        path_str = entry["path"]
        if path_str in seen_file_paths:
            duplicate_file_paths.add(path_str)
        seen_file_paths.add(path_str)
    for path_str in sorted(duplicate_file_paths):
        problems.append(f"manifest 'files' lists {path_str!r} more than once")

    seen_period_ids: set[tuple[str, str]] = set()
    duplicate_period_ids: set[tuple[str, str]] = set()
    for entry in manifest["analysis_manifest"]:
        identity = manifest_mod.analysis_identity(entry)
        if identity in seen_period_ids:
            duplicate_period_ids.add(identity)
        seen_period_ids.add(identity)
    for entity, period_id in sorted(duplicate_period_ids):
        problems.append(
            f"manifest 'analysis_manifest' lists period_id {period_id!r} for entity {entity!r} more than once"
        )

    listed_paths = {entry["path"]: entry for entry in manifest["files"]}

    if not manifest["files"]:
        problems.append("manifest 'files' is empty; expected index.html and at least one other asset")
    else:
        if "index.html" not in listed_paths:
            problems.append("manifest 'files' does not include index.html")
        if len(listed_paths) < 2:
            problems.append("manifest 'files' lists no asset besides index.html")
    if not manifest["analysis_manifest"]:
        problems.append("manifest 'analysis_manifest' is empty")

    quarters_schema, network_schema = QUARTERS_FILE_SCHEMA, NETWORK_FILE_SCHEMA
    analysis_schema = ANALYSIS_SCHEMA
    editorial_schema = None
    try:
        expected_contracts = manifest_mod.contract_hashes(manifest_mod.CONTRACTS_DIR)
    except FileNotFoundError as error:
        problems.append(f"cannot verify manifest 'contracts': {error}")
        expected_contracts = None
    if expected_contracts is not None:
        manifest_contracts = manifest.get("contracts", {})
        has_business_metrics = "data/v1/business_metrics.json" in listed_paths
        business_contracts = {"business_metrics.schema.json", "business_metrics_approval.schema.json"}
        optional_payload_contracts = {
            manifest_mod.EDITORIAL_ANALYSIS_CONTRACT: manifest_mod.EDITORIAL_ANALYSIS_PATH,
            "market_demand.schema.json": "data/v1/market-demand.json",
            "news.schema.json": "data/v1/news.json",
        }
        required_contracts = {
            name: digest
            for name, digest in expected_contracts.items()
            if (has_business_metrics or name not in business_contracts)
            and (name not in optional_payload_contracts or optional_payload_contracts[name] in listed_paths)
        }
        if has_business_metrics and not business_contracts <= set(manifest_contracts):
            problems.append("business metrics files require both business-metrics contract hashes")
        for name, current_hash in sorted(required_contracts.items()):
            actual_hash = manifest_contracts.get(name)
            try:
                resolved = resolve_contract(manifest_mod.CONTRACTS_DIR, name, actual_hash)
            except ValueError as error:
                problems.append(
                    f"contracts[{name!r}]: manifest says {actual_hash!r}, but current contract "
                    f"hashes to {current_hash!r}; {error}"
                )
            else:
                if name == "flights.schema.json":
                    quarters_schema, network_schema = split_flight_schemas(
                        json.loads(resolved.read_text(encoding="utf-8"))
                    )
                elif name == "analysis.schema.json":
                    analysis_schema = json.loads(resolved.read_text(encoding="utf-8"))
                elif name == manifest_mod.EDITORIAL_ANALYSIS_CONTRACT:
                    editorial_schema = json.loads(resolved.read_text(encoding="utf-8"))
        for name in sorted(manifest_contracts):
            if name not in expected_contracts:
                problems.append(f"contracts[{name!r}]: not a contract file this checkout expects")

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

    analysis_payloads_by_period: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    data_payloads: dict[str, dict[str, Any]] = {}
    rules = load_privacy_rules()
    for rel in sorted(actual_paths):
        parts = rel.split("/")
        is_data_file = parts[:2] == ["data", "v1"] and rel.endswith(".json")
        schema = _data_schema_for(rel, quarters_schema, network_schema, analysis_schema)
        if rel == manifest_mod.EDITORIAL_ANALYSIS_PATH and editorial_schema is not None:
            schema = editorial_schema
        if schema is None:
            if is_data_file:
                problems.append(
                    f"{rel}: not one of the data/v1 files contracts/web declares "
                    "(src.publish.verify._data_schema_for found no sub-schema for it)"
                )
            continue
        path = site_dir / rel
        try:
            check_file_size(path, rules)
        except PrivacyViolation as error:
            problems.append(f"{rel}: {error}")
        raw = path.read_bytes()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            problems.append(f"{rel}: not valid JSON: {error}")
            continue
        if isinstance(payload, dict):
            data_payloads[rel] = payload
        if rel == "data/v1/news.json" and rel not in preserved_approval_files:
            from src.web_export.news import news_export_payload
            try:
                if payload != news_export_payload():
                    problems.append("news.json differs from the pinned approved index projection")
            except ValueError as error:
                problems.append(f"news approval could not be revalidated: {error}")

        clean_key = (hashlib.sha256(raw).hexdigest(), _schema_digest(schema))
        if clean_key not in _CLEAN_DATA_FILES:
            data_validator = Draft202012Validator(schema)
            errors = [f"{rel} {list(e.path)}: {e.message}" for e in data_validator.iter_errors(payload)]
            problems.extend(errors)
            if not errors:
                _CLEAN_DATA_FILES.add(clean_key)
        forbidden = find_forbidden_fields(payload, rules["forbidden_fields"])
        carriers = find_disallowed_carriers(payload, rules["allowed_estimated_carriers"])
        for field in forbidden:
            problems.append(f"{rel}: forbidden field present: {field}")
        for carrier in carriers:
            problems.append(f"{rel}: disallowed carrier_key: {carrier}")
        if (
            (schema is analysis_schema or schema is editorial_schema)
            and isinstance(payload, dict)
            and isinstance(payload.get("period_id"), str)
        ):
            try:
                identity = manifest_mod.analysis_identity(payload)
            except ValueError as error:
                problems.append(f"{rel}: {error}")
                continue
            expected_path = "data/v1/" + manifest_mod.analysis_relative_path(payload).as_posix()
            if rel != expected_path:
                problems.append(f"{rel}: analysis entity/period header requires path {expected_path}")
            if identity in analysis_payloads_by_period:
                problems.append(f"{rel}: duplicate analysis payload for entity/period {identity}")
            analysis_payloads_by_period[identity] = (rel, payload)

    metrics_path = "data/v1/business_metrics.json"
    receipt_path = "data/v1/business_metrics.approval.json"
    has_metrics = metrics_path in listed_paths
    has_receipt = receipt_path in listed_paths
    if has_metrics != has_receipt:
        problems.append("business metrics payload and approval receipt must be published together")
    elif has_metrics and metrics_path in data_payloads and receipt_path in data_payloads and not {metrics_path, receipt_path} <= preserved_approval_files:
        try:
            expected_payload, expected_receipt = build_approved_payload(
                PATHS.root / "config/chat/business-metrics-proposal.json",
                PATHS.root / "config/chat/metrics-candidates.json",
                site_dir / receipt_path,
            )
        except (OSError, ValueError, json.JSONDecodeError) as error:
            problems.append(f"business metrics approval could not be revalidated: {error}")
        else:
            if data_payloads[metrics_path] != expected_payload:
                problems.append(
                    "published business metrics do not match the current approved proposal and receipt"
                )
            if data_payloads[receipt_path] != expected_receipt:
                problems.append("published business metrics approval receipt does not match its file")

    analysis_fields = (
        "period_id",
        "version",
        "content_hash",
        "evidence_fingerprint",
        "approval_event",
        "audit_hash",
    )
    for index, entry in enumerate(manifest["analysis_manifest"]):
        for field in analysis_fields:
            value = entry.get(field)
            if not isinstance(value, str) or not value:
                problems.append(f"analysis_manifest[{index}]: {field!r} is missing or not a non-empty string")
                break
        else:
            identity = manifest_mod.analysis_identity(entry)
            expected_path = "data/v1/" + manifest_mod.analysis_relative_path(entry).as_posix()
            pair = analysis_payloads_by_period.get(identity)
            if pair is None:
                problems.append(
                    f"analysis_manifest[{index}]: no readable {expected_path} to cross-check against"
                )
                continue
            actual_path, payload = pair
            if actual_path != expected_path:
                problems.append(
                    f"analysis_manifest[{index}]: entity/period identity requires "
                    f"{expected_path}, found {actual_path}"
                )
            for field in analysis_fields:
                if payload.get(field) != entry[field]:
                    problems.append(
                        f"analysis_manifest[{index}] ({field!r}): manifest says {entry[field]!r}, but "
                        f"{actual_path}'s own {field!r} is {payload.get(field)!r}"
                    )
    for identity, (rel, _) in sorted(analysis_payloads_by_period.items()):
        if identity not in seen_period_ids:
            problems.append(f"{rel}: analysis entity/period has no approval identity in analysis_manifest")

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
