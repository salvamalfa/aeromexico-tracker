"""Export the Vuelos v1 payload as files split by period.

Splits exactly the payload the published HTML already embeds
(``integration_flight_payload(build_flight_payload())``) with no new
computation: ``flights/quarters.json`` (metadata, quarters, monthly
passengers, world geometry), one ``flights/domestic/<period_id>.json`` and
one ``flights/international/<period_id>.json`` per period. See
``src/web_export/README.md`` and ``tests/test_web_export.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.dashboard.flights_html import integration_flight_payload
from src.web_export.inputs import require_inputs
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.schemas import NETWORK_FILE_SCHEMA, QUARTERS_FILE_SCHEMA
from src.web_export.writer import write_json


def _validate(schema: dict[str, Any], payload: Any, *, what: str) -> None:
    validator = Draft202012Validator(schema)
    errors = [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(payload)]
    if errors:
        raise ValueError(f"{what} does not match its schema: {errors[:5]}")


def export_flights(
    raw_payload: dict[str, Any],
    out_dir: Path,
    *,
    skip_input_check: bool = False,
) -> list[Path]:
    """Write the split v1 flight files under out_dir/flights/. Returns the paths written."""

    if not skip_input_check:
        require_inputs("flights")

    embedded = integration_flight_payload(raw_payload)
    rules = load_privacy_rules()
    check_privacy(embedded, rules)

    written: list[Path] = []
    base = out_dir / "flights"

    domestic_periods = {**embedded["domestic_networks"], **embedded["domestic_monthly_networks"]}
    international_periods = embedded["route_networks"]

    quarters_doc = {
        "schema_version": embedded["schema_version"],
        "metadata": embedded["metadata"],
        "quarters": embedded["quarters"],
        "monthly_passengers": embedded["monthly_passengers"],
        "route_network": embedded["route_network"],
        # Front-end manifest (web/): fetch() has no directory listing, so the
        # front-end needs to know which per-period files exist before asking
        # for them. Domestic quarter ids ("…Q…") and month ids ("…M…") are
        # told apart the same way recombine_flights() does below.
        "available_periods": {
            "domestic": sorted(p for p in domestic_periods if "Q" in p),
            "domestic_monthly": sorted(p for p in domestic_periods if "M" in p),
            "international": sorted(international_periods),
        },
    }
    _validate(QUARTERS_FILE_SCHEMA, quarters_doc, what="flights/quarters.json")
    written.append(write_json(base / "quarters.json", quarters_doc))

    for period_id, network in domestic_periods.items():
        _validate(NETWORK_FILE_SCHEMA, network, what=f"flights/domestic/{period_id}.json")
        written.append(write_json(base / "domestic" / f"{period_id}.json", network))

    for period_id, network in international_periods.items():
        _validate(NETWORK_FILE_SCHEMA, network, what=f"flights/international/{period_id}.json")
        written.append(write_json(base / "international" / f"{period_id}.json", network))

    return written


def recombine_flights(out_dir: Path) -> dict[str, Any]:
    """Reverse export_flights: rebuild the embedded v1 payload from the split files.

    Used by the equivalence test to prove the split is lossless. Domestic
    files are routed back to ``domestic_networks`` (quarter ids, "…Q…") or
    ``domestic_monthly_networks`` (month ids, "…M…") by the same convention
    every period id in this codebase already follows.
    """

    import json

    base = out_dir / "flights"
    quarters_doc = json.loads((base / "quarters.json").read_text(encoding="utf-8"))

    domestic_networks: dict[str, Any] = {}
    domestic_monthly_networks: dict[str, Any] = {}
    domestic_dir = base / "domestic"
    if domestic_dir.exists():
        for path in sorted(domestic_dir.glob("*.json")):
            period_id = path.stem
            network = json.loads(path.read_text(encoding="utf-8"))
            if "M" in period_id:
                domestic_monthly_networks[period_id] = network
            else:
                domestic_networks[period_id] = network

    route_networks: dict[str, Any] = {}
    international_dir = base / "international"
    if international_dir.exists():
        for path in sorted(international_dir.glob("*.json")):
            route_networks[path.stem] = json.loads(path.read_text(encoding="utf-8"))

    return {
        "schema_version": quarters_doc["schema_version"],
        "metadata": quarters_doc["metadata"],
        "quarters": quarters_doc["quarters"],
        "monthly_passengers": quarters_doc["monthly_passengers"],
        "route_network": quarters_doc["route_network"],
        "route_networks": route_networks,
        "domestic_networks": domestic_networks,
        "domestic_monthly_networks": domestic_monthly_networks,
    }
