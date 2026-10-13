"""Version and entity identities for the analysis lifecycle ledger.

Legacy records and events retain their original bytes and map to Aeromexico.
New records and references must carry an explicit matching entity.
"""

from __future__ import annotations

import re

from .evidence import digest

LEGACY_ENTITY = "AEROMEXICO"


def is_entity_record(record):
    return record["draft"].get("schema_version") == "entity_analyst_v1"


def entity_key(record):
    draft = record["draft"]
    entity = draft.get("entity_key") if is_entity_record(record) else LEGACY_ENTITY
    if not isinstance(entity, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", entity):
        raise ValueError("Invalid entity identity")
    if draft.get("entity_key", entity) != entity or record.get("entity_key", entity) != entity:
        raise ValueError("Record entity identity mismatch")
    return entity


def record_identity(record):
    return entity_key(record), record["draft"]["period_id"], record["version"]


def event_identity(event):
    entity = event.get("entity_key", LEGACY_ENTITY)
    period, version = event.get("period_id"), event.get("version")
    if (
        not isinstance(entity, str)
        or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", entity)
        or not isinstance(period, str)
        or not re.fullmatch(r"\d{4}Q[1-4]", period)
        or not isinstance(version, str)
        or not re.fullmatch(r"[a-f0-9]{64}", version)
    ):
        raise ValueError("Invalid ledger event identity")
    return entity, period, version


def check_entity_reference(reference, record, label):
    entity = entity_key(record)
    if (is_entity_record(record) and reference.get("entity_key") != entity) or (
        "entity_key" in reference and reference["entity_key"] != entity
    ):
        raise ValueError(f"{label} entity identity mismatch")
    if "period_id" in reference and reference["period_id"] != record["draft"]["period_id"]:
        raise ValueError(f"{label} period identity mismatch")


def verify_record(record):
    if record["content_hash"] != digest(record["draft"]):
        raise ValueError("Draft content changed after versioning")
    version = digest({k: record[k] for k in ("draft", "prompt_version", "code_version")})
    prefix = record["draft"]["period_id"]
    entity = entity_key(record)
    if is_entity_record(record):
        prefix = entity + "_" + prefix
    if version != record["version"] or record["analysis_id"] != prefix + "_" + version:
        raise ValueError("Version identity mismatch")
    if not re.fullmatch(r"\d{4}Q[1-4]", record["draft"]["period_id"]):
        raise ValueError("Invalid period")
