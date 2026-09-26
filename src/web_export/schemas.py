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

QUARTERS_FILE_SCHEMA: dict[str, Any] = {
    "$defs": FLIGHTS_SCHEMA["$defs"],
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version", "metadata", "quarters", "monthly_passengers",
        "route_network", "available_periods",
    ],
    "properties": {
        "schema_version": FLIGHTS_SCHEMA["properties"]["schema_version"],
        "metadata": FLIGHTS_SCHEMA["properties"]["metadata"],
        "quarters": FLIGHTS_SCHEMA["properties"]["quarters"],
        "monthly_passengers": {"$ref": "#/$defs/monthly_passengers"},
        "route_network": FLIGHTS_SCHEMA["properties"]["route_network"],
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
            },
        },
    },
}

NETWORK_FILE_SCHEMA: dict[str, Any] = {
    "$defs": FLIGHTS_SCHEMA["$defs"],
    "$ref": "#/$defs/network",
}
