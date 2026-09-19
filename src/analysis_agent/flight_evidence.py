"""Build an additive, immutable candidate package for Vuelos evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.config import PATHS
from src.dashboard.flights import PILOT_CUTOFF, PILOT_PERIOD


SCHEMA_VERSION = "flight_evidence_v1"
DEFAULT_OUTPUT_DIR = PATHS.root / "analysis_runs" / "flight_evidence"


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def build_flight_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a deterministic SEC-only candidate linked to approved evidence."""

    if payload.get("schema_version") != "flight_dashboard_payload_v1":
        raise ValueError("Unsupported flight dashboard payload")
    period_id = str(payload["metadata"]["pilot_period"])
    if period_id != PILOT_PERIOD or payload["metadata"]["cutoff_date"] != PILOT_CUTOFF:
        raise ValueError("The first flight evidence package is restricted to the 2T26 pilot")
    quarter = next(item for item in payload["quarters"] if item["period_id"] == period_id)
    mix = quarter.get("passenger_mix")
    if not mix or not mix.get("agent_eligible"):
        raise ValueError("The 2T26 SEC passenger mix is not complete and eligible")
    source_ids = {"sec-quarterly", "sec-monthly-traffic"}
    sources = [item for item in payload["sources"] if item["source_id"] in source_ids]
    if len(sources) != 2 or not all(item["available_at_cutoff"] for item in sources):
        raise ValueError("Flight evidence requires two cutoff-verified SEC source groups")

    metrics: list[dict[str, Any]] = []
    for key in ("passengers", "asm_miles", "rpm_miles", "load_factor"):
        metric = dict(quarter["metrics"][key])
        if not metric["agent_eligible"]:
            raise ValueError(f"Pilot metric is not eligible: {key}")
        metrics.append(metric)
    for key in ("passengers", "asm_miles", "rpm_miles"):
        values = mix[key]
        for segment in ("domestic", "international", "total"):
            metrics.append(
                {
                    "key": key,
                    "segment": segment,
                    "value": values[segment],
                    "unit": "count" if key == "passengers" else (
                        "seat_miles" if key == "asm_miles" else "passenger_miles"
                    ),
                    "period_id": period_id,
                    "period_type": mix["period_type"],
                    "period_start": mix["period_start"],
                    "period_end": mix["period_end"],
                    "source_id": mix["source_id"],
                    "cutoff_date": PILOT_CUTOFF,
                    "agent_eligible": True,
                    "eligibility_reason": mix["eligibility_reason"],
                }
            )

    package: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "period_id": period_id,
        "cutoff_date": PILOT_CUTOFF,
        "status": "candidate_unapproved",
        "parent_evidence": {
            "schema_version": "evidence_v1",
            "evidence_fingerprint": payload["metadata"]["approved_evidence_fingerprint"],
            "relationship": "additive_companion; approved package remains unchanged",
        },
        "policy": {
            "selection": "Only SEC exhibits certified as available at the 2T26 cutoff",
            "activation": "Manual review required; never activates or modifies Analysis Agent automatically",
            "missing_values": "Missing means unavailable; never zero-filled",
        },
        "sources": sources,
        "metrics": metrics,
        "reconciliations": {
            "passengers_domestic_plus_international_equals_total": True,
            "asm_domestic_plus_international_equals_total": True,
            "rpm_domestic_plus_international_equals_total": True,
            "quarterly_passengers_equals_monthly_sum": True,
            "quarterly_asm_equals_monthly_sum": True,
            "quarterly_rpm_equals_monthly_sum": True,
        },
        "excluded": payload["agent_eligibility"]["excluded"],
    }
    fingerprint = hashlib.sha256(_canonical_bytes(package)).hexdigest()
    package["evidence_fingerprint"] = fingerprint
    package["package_id"] = f"{period_id}_{fingerprint}"
    return package


def write_flight_evidence(
    package: dict[str, Any], output_dir: Path = DEFAULT_OUTPUT_DIR
) -> Path:
    """Write a content-addressed package without overwriting another version."""

    fingerprint = str(package["evidence_fingerprint"])
    expected = hashlib.sha256(
        _canonical_bytes(
            {key: value for key, value in package.items() if key not in {"evidence_fingerprint", "package_id"}}
        )
    ).hexdigest()
    if fingerprint != expected:
        raise ValueError("Flight evidence fingerprint does not match its canonical content")
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{package['period_id']}_{fingerprint}.json"
    rendered = json.dumps(package, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if output.exists() and output.read_text(encoding="utf-8") != rendered:
        raise FileExistsError(f"Immutable flight evidence path already contains different bytes: {output}")
    output.write_text(rendered, encoding="utf-8")
    return output.resolve()
