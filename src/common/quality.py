"""Append-only data-quality issue ledger."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import threading
from typing import Final
from uuid import uuid4

from src.config import PATHS


SEVERITIES: Final[frozenset[str]] = frozenset({"info", "warning", "error", "critical"})
ISSUE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "missing_period",
        "schema_drift",
        "value_out_of_range",
        "restatement",
        "unmapped_entity",
        "unit_ambiguity",
        "parse_failure",
        "source_conflict",
    }
)
_APPEND_LOCK = threading.Lock()


def _utc_now() -> datetime:
    return datetime.now(UTC)


def log_issue(
    layer: str,
    table_name: str,
    source_file: str,
    severity: str,
    issue_type: str,
    description: str,
    affected_rows: int | None = None,
    *,
    issues_path: Path | None = None,
    detected_at: datetime | None = None,
) -> dict[str, object]:
    """Validate and append one quality issue, returning the exact stored record."""

    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {sorted(SEVERITIES)}")
    if issue_type not in ISSUE_TYPES:
        raise ValueError(f"issue_type must be one of {sorted(ISSUE_TYPES)}")
    if affected_rows is not None and affected_rows < 0:
        raise ValueError("affected_rows cannot be negative")
    if not description.strip():
        raise ValueError("description cannot be empty")

    timestamp = detected_at or _utc_now()
    if timestamp.tzinfo is None:
        raise ValueError("detected_at must be timezone-aware")

    record: dict[str, object] = {
        "issue_id": str(uuid4()),
        "detected_at": timestamp.astimezone(UTC).isoformat(),
        "layer": layer,
        "table_name": table_name,
        "source_file": source_file,
        "severity": severity,
        "issue_type": issue_type,
        "description": description,
        "affected_rows": affected_rows,
        "resolved": False,
    }

    target = issues_path or (PATHS.quality / "issues.jsonl")
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    with _APPEND_LOCK, target.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(encoded)
        handle.flush()
    return record
