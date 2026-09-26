"""Enforce contracts/web/privacy.yaml against real and synthetic payloads.

See docs/arquitectura/auditoria-arquitectura-20260926.md §4.2.2 and
contracts/web/README.md.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.config import PATHS
from src.dashboard.flights_html import integration_flight_payload
from src.web_export.privacy import (
    PrivacyViolation,
    check_privacy,
    find_disallowed_carriers,
    find_forbidden_fields,
    load_privacy_rules,
)

FIXTURES_DIR = PATHS.root / "tests" / "fixtures" / "web"
RULES = load_privacy_rules()


def test_privacy_yaml_has_the_documented_shape() -> None:
    assert "AEROMEXICO" in RULES["allowed_estimated_carriers"]
    assert "AEROMEXICO_CONNECT" in RULES["allowed_estimated_carriers"]
    assert "AEROMEXICO_GROUP" in RULES["allowed_estimated_carriers"]
    assert "registration" in RULES["forbidden_fields"]
    assert "flight_number" in RULES["forbidden_fields"]
    assert isinstance(RULES["max_file_size_bytes"], int) and RULES["max_file_size_bytes"] > 0


def test_flights_fixture_has_no_privacy_violations() -> None:
    payload = json.loads((FIXTURES_DIR / "flights_sample.json").read_text(encoding="utf-8"))
    check_privacy(payload, RULES)


def test_executive_fixture_has_no_privacy_violations() -> None:
    payload = json.loads((FIXTURES_DIR / "executive_sample.json").read_text(encoding="utf-8"))
    check_privacy(payload, RULES)


def test_crafted_violation_fixture_is_rejected() -> None:
    """Negative test: the checker must catch a forbidden field and a bad carrier."""

    payload = json.loads((FIXTURES_DIR / "flights_privacy_violation.json").read_text(encoding="utf-8"))

    forbidden = find_forbidden_fields(payload, RULES["forbidden_fields"])
    assert any(path.endswith("registration") for path in forbidden)

    carriers = find_disallowed_carriers(payload, RULES["allowed_estimated_carriers"])
    assert any("COMPETITOR_AIRLINE" in entry for entry in carriers)

    with pytest.raises(PrivacyViolation):
        check_privacy(payload, RULES)


def test_checker_ignores_a_clean_payload() -> None:
    clean = {"routes": [{"market_key": "AAA<>BBB", "monthly": [{"carrier_key": "AEROMEXICO"}]}]}
    check_privacy(clean, RULES)


@pytest.mark.local_data
def test_real_integrated_flights_payload_has_no_privacy_violations(
    flight_payload: dict[str, Any],
) -> None:
    embedded = integration_flight_payload(flight_payload)
    check_privacy(embedded, RULES)


@pytest.mark.local_data
def test_real_executive_payload_has_no_privacy_violations(
    executive_payload: dict[str, Any],
) -> None:
    check_privacy(executive_payload, RULES)
