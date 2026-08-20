"""Immutable bronze storage with hashes, metadata, and restatement lineage."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any, Iterable

from src.config import PATHS


_WRITE_LOCK = threading.Lock()
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9._-]+")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _safe_component(value: str, *, field: str) -> str:
    cleaned = _SAFE_COMPONENT.sub("_", value.strip()).strip("._")
    if not cleaned:
        raise ValueError(f"{field} must contain at least one safe filename character")
    return cleaned


def _normalize_ext(ext: str) -> str:
    cleaned = ext.strip().lower().lstrip(".")
    if not cleaned or not re.fullmatch(r"[a-z0-9]+", cleaned):
        raise ValueError("ext must contain only letters or digits")
    return cleaned


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL in {path} at line {line_number}") from exc
            if isinstance(value, dict):
                yield value


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _append_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def _versioned_path(base_path: Path) -> tuple[Path, int]:
    if not base_path.exists():
        return base_path, 1
    for version in range(2, 10_000):
        candidate = base_path.with_name(f"{base_path.stem}_v{version}{base_path.suffix}")
        if not candidate.exists():
            return candidate, version
    raise RuntimeError(f"Unable to allocate a versioned bronze path for {base_path}")


def save_bronze(
    content: bytes,
    source_system: str,
    entity: str,
    period: str,
    ext: str,
    source_url: str,
    download_method: str,
    notes: str = "",
    *,
    http_status: int = 200,
    content_type: str = "application/octet-stream",
    bronze_root: Path | None = None,
    downloaded_at: datetime | None = None,
) -> Path:
    """Persist raw bytes exactly once and return their immutable local path.

    Duplicate content is detected by SHA-256 across the complete bronze manifest.
    A changed payload for the same source/entity/period creates a new immutable
    version and an append-only restatement event.
    """

    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    if not source_url.strip():
        raise ValueError("source_url cannot be empty")
    if download_method not in {"httpx", "playwright", "computer_use", "manual"}:
        raise ValueError("unsupported download_method")

    timestamp = downloaded_at or _utc_now()
    if timestamp.tzinfo is None:
        raise ValueError("downloaded_at must be timezone-aware")
    timestamp = timestamp.astimezone(UTC)

    safe_source = _safe_component(source_system, field="source_system")
    safe_entity = _safe_component(entity, field="entity")
    safe_period = _safe_component(period, field="period")
    safe_ext = _normalize_ext(ext)
    digest = _sha256(content)
    root = (bronze_root or PATHS.bronze).resolve()
    root.mkdir(parents=True, exist_ok=True)
    source_directory = root / safe_source
    source_directory.mkdir(parents=True, exist_ok=True)
    manifest_path = root / "_manifest.jsonl"
    restatements_path = root / "_restatements.jsonl"
    logical_key = f"{safe_source}|{safe_entity}|{safe_period}|{safe_ext}"

    with _WRITE_LOCK:
        manifest_records = list(_iter_jsonl(manifest_path))
        for existing in manifest_records:
            if existing.get("sha256") != digest:
                continue
            existing_name = existing.get("source_file")
            if isinstance(existing_name, str):
                existing_path = root / existing_name
                if existing_path.is_file():
                    return existing_path

        previous_versions = [
            record for record in manifest_records if record.get("logical_key") == logical_key
        ]
        base_name = (
            f"{safe_source}_{safe_entity}_{safe_period}_"
            f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}.{safe_ext}"
        )
        target_path, filename_version = _versioned_path(source_directory / base_name)
        content_relative = target_path.relative_to(root).as_posix()
        logical_version = len(previous_versions) + 1

        metadata: dict[str, Any] = {
            "source_system": source_system,
            "source_url": source_url,
            "downloaded_at": timestamp.isoformat(),
            "sha256": digest,
            "http_status": http_status,
            "content_type": content_type,
            "bytes": len(content),
            "download_method": download_method,
            "notes": notes,
            "source_file": content_relative,
            "logical_key": logical_key,
            "logical_version": logical_version,
            "filename_version": filename_version,
        }
        meta_path = target_path.with_suffix(target_path.suffix + ".meta.json")

        _atomic_write(target_path, content)
        _atomic_write(
            meta_path,
            (json.dumps(metadata, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode(
                "utf-8"
            ),
        )
        _append_jsonl(manifest_path, metadata)

        if previous_versions:
            previous = previous_versions[-1]
            restatement = {
                "detected_at": timestamp.isoformat(),
                "logical_key": logical_key,
                "previous_source_file": previous.get("source_file"),
                "previous_sha256": previous.get("sha256"),
                "new_source_file": content_relative,
                "new_sha256": digest,
                "logical_version": logical_version,
            }
            _append_jsonl(restatements_path, restatement)

    return target_path
