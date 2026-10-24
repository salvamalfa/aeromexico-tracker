"""Load contracts/web/*.schema.json and derive per-split-file sub-schemas.

A split file (e.g. one period's network) is not a full v1 payload, so it
cannot validate against the top-level schema directly. Each sub-schema below
reuses the same ``$defs`` and points ``$ref`` at the definition that
describes that one file's shape — the two never drift apart because they
share one JSON document.
"""

from __future__ import annotations

import json
from typing import Any

from src.config import PATHS

CONTRACTS_DIR = PATHS.root / "contracts" / "web"


def _load(name: str) -> dict[str, Any]:
    return json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))


FLIGHTS_SCHEMA = _load("flights.schema.json")
EXECUTIVE_SCHEMA = _load("executive.schema.json")
ANALYSIS_SCHEMA = _load("analysis.schema.json")
EDITORIAL_ANALYSIS_SCHEMA = _load("analysis_editorial.schema.json")


def analysis_schema_for(period_id: str, entity_key: str = "AEROMEXICO") -> dict[str, Any]:
    """The additional citation contract is confined to the approved Q3 slot."""
    return (
        EDITORIAL_ANALYSIS_SCHEMA if (entity_key, period_id) == ("AEROMEXICO", "2026Q3") else ANALYSIS_SCHEMA
    )


MARKET_SCHEMA = _load("market.schema.json")
BUSINESS_METRICS_SCHEMA = _load("business_metrics.schema.json")
BUSINESS_METRICS_APPROVAL_SCHEMA = _load("business_metrics_approval.schema.json")


def split_flight_schemas(flights_schema: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Derive both split schemas from the exact resolved contract document."""

    quarters: dict[str, Any] = {
        "$defs": flights_schema["$defs"],
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "metadata",
            "quarters",
            "monthly_passengers",
            "route_network",
            "available_periods",
        ],
        "properties": {
            "schema_version": flights_schema["properties"]["schema_version"],
            "metadata": flights_schema["properties"]["metadata"],
            "quarters": flights_schema["properties"]["quarters"],
            "monthly_passengers": {"$ref": "#/$defs/monthly_passengers"},
            "route_network": flights_schema["properties"]["route_network"],
            # web/ front-end manifest: which per-period files export_flights()
            # wrote, so fetch() knows what to ask for (see src/web_export/flights.py).
            "available_periods": {
                "type": "object",
                "additionalProperties": False,
                "required": ["domestic", "domestic_monthly", "international"],
                "properties": {
                    "domestic": {"type": "array", "items": {"type": "string"}},
                    "domestic_monthly": {"type": "array", "items": {"type": "string"}},
                    "international": {"type": "array", "items": {"type": "string"}},
                    # Dashboard v2: per-entity map files (flights/entities/<KEY>/…).
                    "entities": {
                        "type": "object",
                        "additionalProperties": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["label", "domestic_monthly", "international"],
                            "properties": {
                                "label": {"type": "string"},
                                "domestic_monthly": {"type": "array", "items": {"type": "string"}},
                                "international": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                },
            },
        },
    }
    if "map_coverage" in flights_schema["properties"]:
        quarters["properties"]["map_coverage"] = flights_schema["properties"]["map_coverage"]
    network = {"$defs": flights_schema["$defs"], "$ref": "#/$defs/network"}
    return quarters, network


QUARTERS_FILE_SCHEMA, NETWORK_FILE_SCHEMA = split_flight_schemas(FLIGHTS_SCHEMA)
