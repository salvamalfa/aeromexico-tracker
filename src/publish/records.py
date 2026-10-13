"""Record loading, entity publication slots and authorized manifest entries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import manifest as manifest_mod

ANALYSIS_MANIFEST_FIELDS = (
    "period_id",
    "version",
    "content_hash",
    "evidence_fingerprint",
    "approval_event",
    "audit_hash",
)


class PublicationRefused(RuntimeError):
    """A record failed verification, or web_export/npm build failed. Nothing was written."""


def _analysis_manifest_entry(authorized: dict[str, Any]) -> dict[str, str]:
    entry = {key: authorized[key] for key in ANALYSIS_MANIFEST_FIELDS}
    if "entity_key" in authorized:
        entry["entity_key"] = authorized["entity_key"]
    manifest_mod.analysis_identity(entry)
    return entry


def _reject_duplicate_periods(records: list[dict[str, Any]]) -> None:
    """Refuse multiple records for one entity/period before export or build."""

    by_period: dict[tuple[str, str], list[str]] = {}
    for record in records:
        try:
            identity = manifest_mod.analysis_identity(record["draft"])
        except ValueError as error:
            raise PublicationRefused(str(error)) from error
        by_period.setdefault(identity, []).append(record.get("version", "?"))
    for (entity, period_id), versions in sorted(by_period.items()):
        if len(versions) > 1:
            versions_str = ", ".join(sorted(versions))
            raise PublicationRefused(
                f"Multiple approved versions for period {period_id} (entity {entity}): {versions_str} — "
                "revoke one or select explicitly"
            )


def load_records(record_paths: list[Path]) -> list[dict[str, Any]]:
    records = [json.loads(Path(path).read_text(encoding="utf-8")) for path in record_paths]
    _reject_duplicate_periods(records)
    return records
