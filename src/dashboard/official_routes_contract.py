"""Shared wire definitions for the official regular-flight map (no legacy mutation)."""

from __future__ import annotations

import hashlib
import json

VERSION = "official_route_network_v1"
PUBLIC_PATH = "data/v1/official-routes.json"
CARRIERS = [
    {"key": "AEROMEXICO", "label": "Grupo Aeroméxico", "operator_ids": ["19534", "20250"]},
    {"key": "VOLARIS", "label": "Volaris", "operator_ids": ["21351"]},
    {"key": "VIVA_AEROBUS", "label": "Viva", "operator_ids": ["21342"]},
]
REGIONS = ("canada", "central_america_caribbean", "south_america", "europe", "asia")


def encoded(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()


def dataset_version(value: dict) -> str:
    """Content identity excluding only its own hash, reproducible across machines."""
    return hashlib.sha256(encoded({k: v for k, v in value.items() if k != "dataset_version"})).hexdigest()


def validate(value: dict) -> None:
    from pathlib import Path

    from jsonschema import Draft202012Validator

    schema = Path(__file__).resolve().parents[2] / "contracts/web/official-routes.schema.json"
    Draft202012Validator(json.loads(schema.read_bytes())).validate(value)
    if value["dataset_version"] != dataset_version(value):
        raise ValueError("Official routes content identity changed")
    identities = [(n["period_id"], n["scope"], tuple(n["carrier_keys"])) for n in value["networks"]]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate official route network")
