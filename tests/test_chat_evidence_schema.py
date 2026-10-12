from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_PATH = Path("contracts/chat/evidence-index.schema.json")


def test_empty_runtime_index_and_approved_fixture_match_versioned_contract() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    for path in (
        Path("config/chat/evidence/approved-index.json"),
        Path("tests/fixtures/chat_evidence/index.json"),
    ):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if path.parent.name == "chat_evidence":
            payload["records"] = [
                row for row in payload["records"]
                if row.get("review", {}).get("decision") == "owner_approved"
            ]
        assert list(validator.iter_errors(payload)) == []


def test_schema_requires_candidate_content_receipt_binding() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = json.loads(Path("tests/fixtures/chat_evidence/index.json").read_text(encoding="utf-8"))
    del payload["records"][0]["review"]["receipt"]["candidate_content_sha256"]
    errors = list(Draft202012Validator(schema).iter_errors(payload))
    assert errors
