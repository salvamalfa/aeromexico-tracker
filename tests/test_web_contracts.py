"""Validate the current embedded web payloads against contracts/web/*.schema.json.

See docs/arquitectura/auditoria-arquitectura-20260926.md Fase 2 and
contracts/web/README.md. The schemas describe the payload the published
HTML embeds *today* (v1); they are not aspirational.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from src.config import PATHS
from src.dashboard.flights_html import integration_flight_payload

CONTRACTS_DIR = PATHS.root / "contracts" / "web"
FIXTURES_DIR = PATHS.root / "tests" / "fixtures" / "web"

FLIGHTS_SCHEMA = json.loads((CONTRACTS_DIR / "flights.schema.json").read_text(encoding="utf-8"))
EXECUTIVE_SCHEMA = json.loads((CONTRACTS_DIR / "executive.schema.json").read_text(encoding="utf-8"))


def _errors(schema: dict[str, Any], payload: Any) -> list[str]:
    validator = Draft202012Validator(schema)
    return [
        f"{list(error.path)}: {error.message}"
        for error in sorted(validator.iter_errors(payload), key=lambda e: list(e.path))
    ]


def test_flights_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(FLIGHTS_SCHEMA)


def test_executive_schema_is_valid_draft_2020_12() -> None:
    Draft202012Validator.check_schema(EXECUTIVE_SCHEMA)


def test_flights_fixture_matches_schema() -> None:
    payload = json.loads((FIXTURES_DIR / "flights_sample.json").read_text(encoding="utf-8"))
    assert _errors(FLIGHTS_SCHEMA, payload) == []


def test_executive_fixture_matches_schema() -> None:
    payload = json.loads((FIXTURES_DIR / "executive_sample.json").read_text(encoding="utf-8"))
    assert _errors(EXECUTIVE_SCHEMA, payload) == []


@pytest.mark.local_data
def test_real_integrated_flights_payload_matches_schema(flight_payload: dict[str, Any]) -> None:
    """The payload actually embedded in the published HTML validates as v1."""

    embedded = integration_flight_payload(flight_payload)
    errors = _errors(FLIGHTS_SCHEMA, embedded)
    assert errors == [], errors[:10]


@pytest.mark.local_data
def test_real_executive_payload_matches_schema(executive_payload: dict[str, Any]) -> None:
    errors = _errors(EXECUTIVE_SCHEMA, executive_payload)
    assert errors == [], errors[:10]
