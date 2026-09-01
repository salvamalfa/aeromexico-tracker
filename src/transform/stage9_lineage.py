"""Stage 9 source catalog and deterministic record-level lineage helpers.

The module deliberately keeps two hashes with different meanings:

* ``artifact_sha256`` is the digest of one immutable Bronze file.
* ``lineage_fingerprint`` is the digest of the complete, tagged set of
  artifacts and/or parent records that contributed to one output record.

No helper silently treats an aggregate ``source_hash`` as an artifact digest.
Derived or curated records without a direct public file must declare that state
explicitly in :class:`LineageSpec`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
import hashlib
import ipaddress
import json
import math
import numbers
from pathlib import Path
import re
from typing import Any, Literal
from urllib.parse import urlsplit

import pandas as pd
import yaml

from src.config import PATHS


SOURCE_CATALOG_PATH = PATHS.root / "config" / "source_catalog.yaml"

DIM_SOURCE_COLUMNS = [
    "source_key",
    "source_systems",
    "display_name",
    "institution",
    "business_description",
    "coverage",
    "update_frequency",
    "access_method",
    "official_page_url",
    "artifact_link_policy",
    "limitations",
    "source_kind",
    "artifact_expected",
    "is_active",
]
DIM_SOURCE_ARTIFACT_COLUMNS = [
    "artifact_id",
    "source_key",
    "source_system",
    "source_file",
    "source_url",
    "is_direct_public_artifact",
    "downloaded_at",
    "artifact_sha256",
    "artifact_format",
    "content_type",
    "byte_size",
    "http_status",
    "download_method",
    "logical_key",
    "logical_version",
    "filename_version",
    "is_latest_version",
]
DIM_SOURCE_PRIORITY_COLUMNS = [
    "data_domain",
    "source_system",
    "priority",
    "is_default",
    "source_priority_order",
    "is_preliminary_order",
    "confidence_order",
    "ingested_at_order",
    "rationale",
]
BRIDGE_RECORD_LINEAGE_COLUMNS = [
    "lineage_link_id",
    "record_id",
    "table_name",
    "lineage_type",
    "link_type",
    "lineage_status",
    "has_direct_artifact",
    "artifact_id",
    "artifact_sha256",
    "parent_record_id",
    "lineage_fingerprint",
    "lineage_note",
]

_SAFE_KEY = re.compile(r"^[a-z][a-z0-9_]*$")
_SAFE_TABLE = re.compile(r"^[a-z][a-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RECORD_ID = re.compile(r"^rec_[0-9a-f]{64}$")
_ARTIFACT_ID = re.compile(r"^art_[0-9a-f]{64}$")
_LOCAL_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|file://|\\\\)", re.IGNORECASE)
_DISALLOWED_HOSTS = {"localhost", "example.com", "example.org", "example.net"}
_SOURCE_KINDS = {"public", "curated", "derived", "error_evidence"}
_LINK_POLICIES = {"direct", "landing_page_only", "not_applicable"}
_LINEAGE_TYPES = {"direct_artifact", "derived", "curated"}
_RANK_FIELDS = ("source_priority", "is_preliminary", "confidence", "ingested_at")
_SOURCE_REQUIRED = {
    "source_systems",
    "display_name",
    "institution",
    "business_description",
    "coverage",
    "update_frequency",
    "access_method",
    "official_page_url",
    "allowed_hosts",
    "artifact_link_policy",
    "limitations",
    "source_kind",
    "artifact_expected",
    "is_active",
}


def _required_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    text = value.strip()
    if any(ord(character) < 32 for character in text):
        raise ValueError(f"{field} cannot contain control characters")
    return text


def _safe_note(value: str | None) -> str | None:
    if value is None:
        return None
    note = _required_text(value, field="lineage_note")
    if _LOCAL_PATH.search(note):
        raise ValueError("lineage_note cannot expose an absolute local path")
    return note


def _safe_url(
    value: Any,
    *,
    field: str,
    allowed_hosts: Sequence[str] | None = None,
) -> str:
    url = _required_text(value, field=field)
    parsed = urlsplit(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError(f"{field} must be an absolute HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError(f"{field} cannot contain embedded credentials")
    host = parsed.hostname.lower().rstrip(".")
    if (
        host in _DISALLOWED_HOSTS
        or host.endswith((".local", ".invalid", ".example", ".test"))
    ):
        raise ValueError(f"{field} uses a placeholder or local hostname")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError(f"{field} cannot use a private or local IP address")
    if allowed_hosts:
        normalized = [item.lower().rstrip(".") for item in allowed_hosts]
        if not any(host == item or host.endswith(f".{item}") for item in normalized):
            raise ValueError(
                f"{field} host {host!r} is not allowed for this source"
            )
    return url


def _safe_relative_source_file(value: Any, *, root: Path) -> str:
    source_file = _required_text(value, field="source_file")
    if "\\" in source_file or re.match(r"^[A-Za-z]:", source_file):
        raise ValueError("source_file must be a POSIX-style relative path")
    parts = source_file.split("/")
    if source_file.startswith("/") or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("source_file must stay inside the Bronze directory")
    root_resolved = root.resolve()
    resolved = root_resolved.joinpath(*parts).resolve()
    if not resolved.is_relative_to(root_resolved):
        raise ValueError("source_file must stay inside the Bronze directory")
    return "/".join(parts)


def _positive_int(value: Any, *, field: str, allow_zero: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, numbers.Integral):
        raise ValueError(f"{field} must be an integer")
    integer = int(value)
    minimum = 0 if allow_zero else 1
    if integer < minimum:
        raise ValueError(f"{field} must be >= {minimum}")
    return integer


def _validate_sha256(value: Any, *, field: str = "artifact_sha256") -> str:
    digest = _required_text(value, field=field).lower()
    if not _SHA256.fullmatch(digest):
        raise ValueError(f"{field} must be a 64-character hexadecimal SHA-256")
    return digest


def _source_alias_index(catalog: Mapping[str, Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for source_key, definition in catalog["sources"].items():
        for source_system in definition["source_systems"]:
            aliases[str(source_system)] = str(source_key)
    return aliases


def load_source_catalog(path: Path = SOURCE_CATALOG_PATH) -> dict[str, Any]:
    """Load and strictly validate the versioned source catalog."""

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise ValueError("source catalog must be a mapping with version: 1")
    sources = raw.get("sources")
    if not isinstance(sources, dict) or not sources:
        raise ValueError("source catalog must declare at least one source")

    seen_aliases: set[str] = set()
    for source_key, definition in sources.items():
        if not isinstance(source_key, str) or not _SAFE_KEY.fullmatch(source_key):
            raise ValueError(f"Unsafe source_key: {source_key!r}")
        if not isinstance(definition, dict):
            raise ValueError(f"Source {source_key!r} must be a mapping")
        missing = _SOURCE_REQUIRED - set(definition)
        if missing:
            raise ValueError(f"Source {source_key!r} is missing fields: {sorted(missing)}")
        for field in (
            "display_name",
            "institution",
            "business_description",
            "coverage",
            "update_frequency",
            "access_method",
            "limitations",
        ):
            _required_text(definition[field], field=f"{source_key}.{field}")
        systems = definition["source_systems"]
        if not isinstance(systems, list) or not systems:
            raise ValueError(f"{source_key}.source_systems must be a non-empty list")
        for source_system in systems:
            if not isinstance(source_system, str) or not _SAFE_KEY.fullmatch(source_system):
                raise ValueError(f"Unsafe source_system: {source_system!r}")
            if source_system in seen_aliases:
                raise ValueError(f"Duplicate source_system alias: {source_system}")
            seen_aliases.add(source_system)
        source_kind = definition["source_kind"]
        if source_kind not in _SOURCE_KINDS:
            raise ValueError(f"Unsupported source_kind for {source_key}: {source_kind!r}")
        link_policy = definition["artifact_link_policy"]
        if link_policy not in _LINK_POLICIES:
            raise ValueError(
                f"Unsupported artifact_link_policy for {source_key}: {link_policy!r}"
            )
        if not isinstance(definition["artifact_expected"], bool) or not isinstance(
            definition["is_active"], bool
        ):
            raise ValueError(f"{source_key} boolean flags must be true or false")
        allowed_hosts = definition["allowed_hosts"]
        if not isinstance(allowed_hosts, list) or any(
            not isinstance(host, str)
            or not host
            or "://" in host
            or "/" in host
            for host in allowed_hosts
        ):
            raise ValueError(f"{source_key}.allowed_hosts must contain hostnames only")
        official_url = definition["official_page_url"]
        if official_url is None:
            if source_kind in {"public", "error_evidence"}:
                raise ValueError(f"Public source {source_key} requires an official URL")
            if link_policy != "not_applicable" or definition["artifact_expected"]:
                raise ValueError(
                    f"Internal source {source_key} must declare no public artifact"
                )
        else:
            _safe_url(
                official_url,
                field=f"{source_key}.official_page_url",
                allowed_hosts=allowed_hosts,
            )

    priorities = raw.get("priorities")
    if not isinstance(priorities, list) or not priorities:
        raise ValueError("source catalog must declare source priorities")
    priority_keys: set[tuple[str, str]] = set()
    default_domains: set[str] = set()
    for row in priorities:
        if not isinstance(row, dict):
            raise ValueError("Each source priority must be a mapping")
        domain = row.get("data_domain")
        source_system = row.get("source_system")
        if not isinstance(domain, str) or not _SAFE_KEY.fullmatch(domain):
            raise ValueError(f"Unsafe data_domain: {domain!r}")
        if source_system != "*" and source_system not in seen_aliases:
            raise ValueError(f"Unknown priority source_system: {source_system!r}")
        key = (domain, str(source_system))
        if key in priority_keys:
            raise ValueError(f"Duplicate source priority: {key}")
        priority_keys.add(key)
        _positive_int(row.get("priority"), field="priority", allow_zero=True)
        is_default = row.get("is_default")
        if not isinstance(is_default, bool) or is_default != (source_system == "*"):
            raise ValueError("Only the '*' priority row can be the default")
        if is_default:
            if domain in default_domains:
                raise ValueError(f"Duplicate default priority for {domain}")
            default_domains.add(domain)
        _required_text(row.get("rationale"), field="priority.rationale")
    if {domain for domain, _ in priority_keys} != default_domains:
        raise ValueError("Every priority domain must declare exactly one '*' default")

    ranking = raw.get("ranking_rules")
    if not isinstance(ranking, dict) or tuple(ranking) != _RANK_FIELDS:
        raise ValueError(
            "ranking_rules must be ordered as source_priority, is_preliminary, "
            "confidence, ingested_at"
        )
    if any(value not in {"asc", "desc"} for value in ranking.values()):
        raise ValueError("ranking_rules values must be 'asc' or 'desc'")
    return raw


def build_dim_source(path: Path = SOURCE_CATALOG_PATH) -> pd.DataFrame:
    """Build the business-facing source dimension from the validated catalog."""

    catalog = load_source_catalog(path)
    rows: list[dict[str, Any]] = []
    for source_key, definition in catalog["sources"].items():
        rows.append(
            {
                "source_key": source_key,
                "source_systems": json.dumps(
                    sorted(definition["source_systems"]),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                **{
                    column: definition[column]
                    for column in DIM_SOURCE_COLUMNS
                    if column not in {"source_key", "source_systems"}
                },
            }
        )
    return (
        pd.DataFrame(rows, columns=DIM_SOURCE_COLUMNS)
        .sort_values("source_key", kind="stable")
        .reset_index(drop=True)
    )


def build_dim_source_priority(path: Path = SOURCE_CATALOG_PATH) -> pd.DataFrame:
    """Build the single declarative source-precedence table."""

    catalog = load_source_catalog(path)
    ranking = catalog["ranking_rules"]
    rows = [
        {
            "data_domain": row["data_domain"],
            "source_system": row["source_system"],
            "priority": int(row["priority"]),
            "is_default": bool(row["is_default"]),
            "source_priority_order": ranking["source_priority"],
            "is_preliminary_order": ranking["is_preliminary"],
            "confidence_order": ranking["confidence"],
            "ingested_at_order": ranking["ingested_at"],
            "rationale": row["rationale"],
        }
        for row in catalog["priorities"]
    ]
    return (
        pd.DataFrame(rows, columns=DIM_SOURCE_PRIORITY_COLUMNS)
        .sort_values(
            ["data_domain", "is_default", "priority", "source_system"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def _canonicalize(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC)
            return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
        return value.isoformat(timespec="microseconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Natural keys cannot contain non-finite decimals")
        return format(value.normalize(), "f")
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Integral):
        return int(value)
    if isinstance(value, numbers.Real):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Natural keys cannot contain NaN or infinity")
        return number
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Natural-key mapping keys must be strings")
            normalized[key] = _canonicalize(item)
        return normalized
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    item_method = getattr(value, "item", None)
    if callable(item_method):
        return _canonicalize(item_method())
    raise TypeError(f"Unsupported natural-key value: {type(value).__name__}")


def _stable_identifier(
    *, prefix: str, namespace: str, natural_key: Mapping[str, Any]
) -> str:
    if not _SAFE_KEY.fullmatch(prefix) or not _SAFE_TABLE.fullmatch(namespace):
        raise ValueError("Identifier prefix and namespace must use safe snake_case")
    if not isinstance(natural_key, Mapping) or not natural_key:
        raise ValueError("natural_key must be a non-empty mapping")
    payload = json.dumps(
        {"namespace": namespace, "natural_key": _canonicalize(natural_key)},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()}"


def make_record_id(table_name: str, natural_key: Mapping[str, Any]) -> str:
    """Return a stable opaque record id from a table's complete natural key."""

    if not isinstance(table_name, str) or not _SAFE_TABLE.fullmatch(table_name):
        raise ValueError(f"Unsafe table_name: {table_name!r}")
    return _stable_identifier(
        prefix="rec", namespace=table_name, natural_key=natural_key
    )


def add_record_ids(
    frame: pd.DataFrame,
    *,
    table_name: str,
    natural_key_columns: Sequence[str],
) -> pd.DataFrame:
    """Add or verify stable ids without mutating the caller's DataFrame."""

    columns = list(natural_key_columns)
    if not columns or len(columns) != len(set(columns)):
        raise ValueError("natural_key_columns must be a non-empty unique sequence")
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise KeyError(f"Missing natural-key columns for {table_name}: {missing}")
    generated = [
        make_record_id(table_name, {column: row[column] for column in columns})
        for _, row in frame[columns].iterrows()
    ]
    if len(generated) != len(set(generated)):
        raise ValueError(
            f"Natural key for {table_name} is not unique: {columns}"
        )
    output = frame.copy()
    if "record_id" in output.columns:
        existing = output["record_id"].astype("string").tolist()
        if existing != generated:
            raise ValueError(f"Existing record_id values do not match {table_name} keys")
    else:
        output.insert(0, "record_id", generated)
    return output


def _make_artifact_id(source_file: str, artifact_sha256: str) -> str:
    return _stable_identifier(
        prefix="art",
        namespace="source_artifact",
        natural_key={
            "source_file": source_file,
            "artifact_sha256": artifact_sha256,
        },
    )


def _parse_downloaded_at(value: Any, *, line_number: int) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Manifest line {line_number}: invalid downloaded_at"
        ) from exc
    if pd.isna(timestamp) or timestamp.tz is None:
        raise ValueError(
            f"Manifest line {line_number}: downloaded_at must include a timezone"
        )
    return timestamp.tz_convert("UTC")


def _read_manifest(path: Path) -> list[tuple[int, dict[str, Any]]]:
    if not path.is_file():
        raise FileNotFoundError(f"Bronze manifest is missing: {path}")
    records: list[tuple[int, dict[str, Any]]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON in Bronze manifest at line {line_number}"
                ) from exc
            if not isinstance(record, dict):
                raise ValueError(
                    f"Bronze manifest line {line_number} must be a JSON object"
                )
            records.append((line_number, record))
    if not records:
        raise ValueError("Bronze manifest contains no artifacts")
    return records


def build_dim_source_artifact(
    manifest_path: Path | None = None,
    *,
    catalog_path: Path = SOURCE_CATALOG_PATH,
    verify_files: bool = False,
) -> pd.DataFrame:
    """Build one deterministic row per physical immutable Bronze artifact.

    Content-alias manifest entries are collapsed to their original physical file.
    Set ``verify_files=True`` to additionally read each file and verify its digest.
    """

    path = manifest_path or (PATHS.bronze / "_manifest.jsonl")
    bronze_root = path.parent
    catalog = load_source_catalog(catalog_path)
    aliases = _source_alias_index(catalog)
    normalized: list[dict[str, Any]] = []

    for line_number, record in _read_manifest(path):
        source_system = _required_text(
            record.get("source_system"), field=f"manifest[{line_number}].source_system"
        )
        source_key = aliases.get(source_system)
        if source_key is None:
            raise ValueError(
                f"Manifest line {line_number}: uncatalogued source_system "
                f"{source_system!r}"
            )
        definition = catalog["sources"][source_key]
        source_url = _safe_url(
            record.get("source_url"),
            field=f"manifest[{line_number}].source_url",
            allowed_hosts=definition["allowed_hosts"],
        )
        source_file = _safe_relative_source_file(
            record.get("source_file"), root=bronze_root
        )
        digest = _validate_sha256(
            record.get("sha256"), field=f"manifest[{line_number}].sha256"
        )
        downloaded_at = _parse_downloaded_at(
            record.get("downloaded_at"), line_number=line_number
        )
        byte_size = _positive_int(
            record.get("bytes"),
            field=f"manifest[{line_number}].bytes",
            allow_zero=True,
        )
        http_status = _positive_int(
            record.get("http_status"),
            field=f"manifest[{line_number}].http_status",
            allow_zero=True,
        )
        logical_version = _positive_int(
            record.get("logical_version"),
            field=f"manifest[{line_number}].logical_version",
        )
        filename_version = _positive_int(
            record.get("filename_version"),
            field=f"manifest[{line_number}].filename_version",
        )
        logical_key = _required_text(
            record.get("logical_key"), field=f"manifest[{line_number}].logical_key"
        )
        content_type = _required_text(
            record.get("content_type"), field=f"manifest[{line_number}].content_type"
        ).split(";", maxsplit=1)[0].lower()
        download_method = _required_text(
            record.get("download_method"),
            field=f"manifest[{line_number}].download_method",
        )
        if verify_files:
            artifact_path = bronze_root.joinpath(*source_file.split("/"))
            if not artifact_path.is_file():
                raise FileNotFoundError(
                    f"Manifest artifact is missing: {source_file}"
                )
            actual = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            if actual != digest:
                raise ValueError(
                    f"Manifest SHA-256 mismatch for {source_file}: {actual} != {digest}"
                )
        normalized.append(
            {
                "source_key": source_key,
                "source_system": source_system,
                "source_file": source_file,
                "source_url": source_url,
                "downloaded_at": downloaded_at,
                "artifact_sha256": digest,
                "artifact_format": Path(source_file).suffix.lower().lstrip(".")
                or "unknown",
                "content_type": content_type,
                "byte_size": byte_size,
                "http_status": http_status,
                "download_method": download_method,
                "logical_key": logical_key,
                "logical_version": logical_version,
                "filename_version": filename_version,
                "is_content_alias": bool(record.get("is_content_alias", False)),
                "artifact_link_policy": definition["artifact_link_policy"],
            }
        )

    by_file: dict[str, list[dict[str, Any]]] = {}
    for row in normalized:
        by_file.setdefault(row["source_file"], []).append(row)
    selected: list[dict[str, Any]] = []
    for source_file, candidates in by_file.items():
        digests = {row["artifact_sha256"] for row in candidates}
        if len(digests) != 1:
            raise ValueError(
                f"Immutable Bronze path has conflicting hashes: {source_file}"
            )
        chosen = min(
            candidates,
            key=lambda row: (
                row["is_content_alias"],
                row["downloaded_at"].isoformat(),
                row["source_url"],
                row["logical_key"],
            ),
        ).copy()
        chosen["artifact_id"] = _make_artifact_id(
            source_file, chosen["artifact_sha256"]
        )
        selected.append(chosen)

    latest_versions: dict[str, int] = {}
    for row in selected:
        latest_versions[row["logical_key"]] = max(
            latest_versions.get(row["logical_key"], 0), row["logical_version"]
        )
    rows = []
    for row in selected:
        rows.append(
            {
                "artifact_id": row["artifact_id"],
                "source_key": row["source_key"],
                "source_system": row["source_system"],
                "source_file": row["source_file"],
                "source_url": row["source_url"],
                "is_direct_public_artifact": row["artifact_link_policy"] == "direct",
                "downloaded_at": row["downloaded_at"],
                "artifact_sha256": row["artifact_sha256"],
                "artifact_format": row["artifact_format"],
                "content_type": row["content_type"],
                "byte_size": row["byte_size"],
                "http_status": row["http_status"],
                "download_method": row["download_method"],
                "logical_key": row["logical_key"],
                "logical_version": row["logical_version"],
                "filename_version": row["filename_version"],
                "is_latest_version": row["logical_version"]
                == latest_versions[row["logical_key"]],
            }
        )
    return (
        pd.DataFrame(rows, columns=DIM_SOURCE_ARTIFACT_COLUMNS)
        .sort_values(
            ["source_key", "downloaded_at", "source_file", "artifact_id"],
            kind="stable",
        )
        .reset_index(drop=True)
    )


def artifact_id_for(
    artifacts: pd.DataFrame,
    *,
    artifact_sha256: str,
    source_file: str | None = None,
) -> str:
    """Resolve a verified artifact id without accepting aggregate source hashes."""

    required = {"artifact_id", "artifact_sha256", "source_file"}
    missing = required - set(artifacts.columns)
    if missing:
        raise KeyError(f"Artifact dimension is missing columns: {sorted(missing)}")
    digest = _validate_sha256(artifact_sha256)
    matches = artifacts[artifacts["artifact_sha256"].astype(str).str.lower().eq(digest)]
    if source_file is not None:
        matches = matches[matches["source_file"].astype(str).eq(source_file)]
    if len(matches) != 1:
        raise LookupError(
            "Artifact lookup must resolve exactly one row; pass source_file when "
            "the same bytes occur under multiple immutable paths"
        )
    artifact_id = str(matches.iloc[0]["artifact_id"])
    if not _ARTIFACT_ID.fullmatch(artifact_id):
        raise ValueError(f"Invalid artifact_id in dimension: {artifact_id!r}")
    return artifact_id


@dataclass(frozen=True, slots=True)
class LineageSpec:
    """Complete lineage declaration for one Gold or analytical record."""

    record_id: str
    table_name: str
    lineage_type: Literal["direct_artifact", "derived", "curated"]
    artifact_ids: tuple[str, ...] = ()
    parent_record_ids: tuple[str, ...] = ()
    lineage_note: str | None = None


def _validated_lineage_parts(
    *,
    lineage_type: str,
    artifact_sha256s: Iterable[str],
    parent_record_ids: Iterable[str],
    lineage_note: str | None,
) -> tuple[list[str], list[str], str | None]:
    if lineage_type not in _LINEAGE_TYPES:
        raise ValueError(f"Unsupported lineage_type: {lineage_type!r}")
    artifact_hashes = sorted(
        {_validate_sha256(value) for value in artifact_sha256s}
    )
    parents = sorted(set(parent_record_ids))
    if any(not _RECORD_ID.fullmatch(value) for value in parents):
        raise ValueError("parent_record_ids must contain stable rec_ identifiers")
    note = _safe_note(lineage_note)
    if lineage_type == "direct_artifact":
        if not artifact_hashes or parents:
            raise ValueError(
                "direct_artifact lineage requires artifacts and cannot use parent records"
            )
    elif not artifact_hashes and not parents and note is None:
        raise ValueError(
            "Derived or curated lineage without contributors requires an explicit note"
        )
    return artifact_hashes, parents, note


def make_lineage_fingerprint(
    *,
    lineage_type: Literal["direct_artifact", "derived", "curated"],
    artifact_sha256s: Iterable[str] = (),
    parent_record_ids: Iterable[str] = (),
    lineage_note: str | None = None,
) -> str:
    """Hash a tagged lineage set; never return or reuse an artifact digest."""

    artifacts, parents, note = _validated_lineage_parts(
        lineage_type=lineage_type,
        artifact_sha256s=artifact_sha256s,
        parent_record_ids=parent_record_ids,
        lineage_note=lineage_note,
    )
    payload = json.dumps(
        {
            "lineage_type": lineage_type,
            "artifact_sha256s": artifacts,
            "parent_record_ids": parents,
            "lineage_note": note,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _lineage_link_id(
    *, record_id: str, table_name: str, link_type: str, contributor: str
) -> str:
    return _stable_identifier(
        prefix="lnk",
        namespace="record_lineage",
        natural_key={
            "record_id": record_id,
            "table_name": table_name,
            "link_type": link_type,
            "contributor": contributor,
        },
    )


def build_bridge_record_lineage(
    specs: Iterable[LineageSpec], artifacts: pd.DataFrame
) -> pd.DataFrame:
    """Expand complete lineage declarations into a deterministic M:N bridge."""

    required = {"artifact_id", "artifact_sha256"}
    missing = required - set(artifacts.columns)
    if missing:
        raise KeyError(f"Artifact dimension is missing columns: {sorted(missing)}")
    if artifacts["artifact_id"].duplicated().any():
        raise ValueError("Artifact dimension contains duplicate artifact_id values")
    artifact_hash_by_id: dict[str, str] = {}
    for row in artifacts[["artifact_id", "artifact_sha256"]].itertuples(index=False):
        artifact_id = str(row.artifact_id)
        if not _ARTIFACT_ID.fullmatch(artifact_id):
            raise ValueError(f"Invalid artifact_id: {artifact_id!r}")
        artifact_hash_by_id[artifact_id] = _validate_sha256(row.artifact_sha256)

    declarations = list(specs)
    seen_records: set[tuple[str, str]] = set()
    rows: list[dict[str, Any]] = []
    for spec in declarations:
        if not isinstance(spec, LineageSpec):
            raise TypeError("specs must contain LineageSpec values")
        if not _RECORD_ID.fullmatch(spec.record_id):
            raise ValueError(f"Invalid record_id: {spec.record_id!r}")
        if not _SAFE_TABLE.fullmatch(spec.table_name):
            raise ValueError(f"Unsafe table_name: {spec.table_name!r}")
        record_key = (spec.table_name, spec.record_id)
        if record_key in seen_records:
            raise ValueError(f"Duplicate lineage declaration for {record_key}")
        seen_records.add(record_key)

        artifact_ids = sorted(set(spec.artifact_ids))
        if any(not _ARTIFACT_ID.fullmatch(value) for value in artifact_ids):
            raise ValueError("artifact_ids must contain stable art_ identifiers")
        unknown = [value for value in artifact_ids if value not in artifact_hash_by_id]
        if unknown:
            raise LookupError(f"Unknown artifact ids: {unknown}")
        parent_ids = sorted(set(spec.parent_record_ids))
        artifact_hashes = [artifact_hash_by_id[value] for value in artifact_ids]
        validated_hashes, validated_parents, note = _validated_lineage_parts(
            lineage_type=spec.lineage_type,
            artifact_sha256s=artifact_hashes,
            parent_record_ids=parent_ids,
            lineage_note=spec.lineage_note,
        )
        fingerprint = make_lineage_fingerprint(
            lineage_type=spec.lineage_type,
            artifact_sha256s=validated_hashes,
            parent_record_ids=validated_parents,
            lineage_note=note,
        )
        has_direct_artifact = bool(artifact_ids)

        for artifact_id in artifact_ids:
            digest = artifact_hash_by_id[artifact_id]
            rows.append(
                {
                    "lineage_link_id": _lineage_link_id(
                        record_id=spec.record_id,
                        table_name=spec.table_name,
                        link_type="artifact",
                        contributor=artifact_id,
                    ),
                    "record_id": spec.record_id,
                    "table_name": spec.table_name,
                    "lineage_type": spec.lineage_type,
                    "link_type": "artifact",
                    "lineage_status": "resolved_to_artifact",
                    "has_direct_artifact": has_direct_artifact,
                    "artifact_id": artifact_id,
                    "artifact_sha256": digest,
                    "parent_record_id": None,
                    "lineage_fingerprint": fingerprint,
                    "lineage_note": note,
                }
            )
        for parent_record_id in validated_parents:
            rows.append(
                {
                    "lineage_link_id": _lineage_link_id(
                        record_id=spec.record_id,
                        table_name=spec.table_name,
                        link_type="parent_record",
                        contributor=parent_record_id,
                    ),
                    "record_id": spec.record_id,
                    "table_name": spec.table_name,
                    "lineage_type": spec.lineage_type,
                    "link_type": "parent_record",
                    "lineage_status": "resolved_to_parent_record",
                    "has_direct_artifact": has_direct_artifact,
                    "artifact_id": None,
                    "artifact_sha256": None,
                    "parent_record_id": parent_record_id,
                    "lineage_fingerprint": fingerprint,
                    "lineage_note": note,
                }
            )
        if not artifact_ids and not validated_parents:
            rows.append(
                {
                    "lineage_link_id": _lineage_link_id(
                        record_id=spec.record_id,
                        table_name=spec.table_name,
                        link_type="declaration",
                        contributor=note or spec.lineage_type,
                    ),
                    "record_id": spec.record_id,
                    "table_name": spec.table_name,
                    "lineage_type": spec.lineage_type,
                    "link_type": "declaration",
                    "lineage_status": "declared_without_artifact",
                    "has_direct_artifact": False,
                    "artifact_id": None,
                    "artifact_sha256": None,
                    "parent_record_id": None,
                    "lineage_fingerprint": fingerprint,
                    "lineage_note": note,
                }
            )

    return (
        pd.DataFrame(rows, columns=BRIDGE_RECORD_LINEAGE_COLUMNS)
        .sort_values(
            ["table_name", "record_id", "link_type", "lineage_link_id"],
            kind="stable",
        )
        .reset_index(drop=True)
    )
