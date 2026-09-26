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

QUARTERS_FILE_SCHEMA: dict[str, Any] = {
    "$defs": FLIGHTS_SCHEMA["$defs"],
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "metadata", "quarters", "monthly_passengers", "route_network"],
    "properties": {
        "schema_version": FLIGHTS_SCHEMA["properties"]["schema_version"],
        "metadata": FLIGHTS_SCHEMA["properties"]["metadata"],
        "quarters": FLIGHTS_SCHEMA["properties"]["quarters"],
        "monthly_passengers": {"$ref": "#/$defs/monthly_passengers"},
        "route_network": FLIGHTS_SCHEMA["properties"]["route_network"],
    },
}

NETWORK_FILE_SCHEMA: dict[str, Any] = {
    "$defs": FLIGHTS_SCHEMA["$defs"],
    "$ref": "#/$defs/network",
}
