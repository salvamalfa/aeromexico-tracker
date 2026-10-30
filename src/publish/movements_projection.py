"""Reclassify existing Aerocivil cells without changing source counts or other data."""

from __future__ import annotations

import math
import re
from copy import deepcopy

import pandas as pd
from jsonschema import Draft202012Validator

from src.dashboard.map_periods import period_months
from src.dashboard.recorded_movements import LABEL, movement_payload
from src.web_export.schemas import NETWORK_FILE_SCHEMA

HISTORICAL_SHA = "ef1468b4f92af37ec287f68114a912498b8a86ef5829afb431c8926598237697"
Q2_SHA = "b77f81b0acae11f94de6f028acb1a56a243105da8ddaabf63f5d26790dc6594c"
JULY_SHA = "8a49675fe9c7e91ed9552a1c57c4e9260eee2c4e926643654fdd8105d1204fe5"
CAPTURES = {
    HISTORICAL_SHA: (36860, "2026-09-08T23:45:36.408453+00:00"),
    Q2_SHA: (15547, "2026-10-19T15:12:29.288823+00:00"),
    JULY_SHA: (2074, "2026-10-21T00:27:49.519118+00:00"),
}
BINDING_OUTPUTS = {
    "silver/international_routes/observations",
    "gold/fact_international_route_observations",
    "gold/dim_source_artifact",
    "gold/bridge_international_route_lineage",
}
SOURCE_COUNTS = {HISTORICAL_SHA: (147, 6308), Q2_SHA: (64, 1636), JULY_SHA: (8, 347)}
OPERATORS = {"AEROMEXICO": "AMX", "AEROMEXICO_CONNECT": "SLI", "VIVA_AEROBUS": "VIV", "VOLARIS": "VOI"}
PERIODS = tuple(
    [f"2025M{m:02d}" for m in range(1, 13)]
    + [f"2026M{m:02d}" for m in range(1, 8)]
    + [f"2025Q{q}" for q in range(1, 5)]
    + [f"2026Q{q}" for q in range(1, 4)]
)
NETWORK_TARGETS = tuple(
    sorted(
        [f"data/v1/flights/international/{period}.json" for period in PERIODS]
        + [
            f"data/v1/flights/entities/{entity}/international/{period}.json"
            for entity in ("VIVA_AEROBUS", "VOLARIS", "INDUSTRY")
            for period in ("2026M04", "2026M05", "2026M06", "2026Q2")
        ]
    )
)
TARGETS = tuple(sorted((*NETWORK_TARGETS, "data/v1/flights/quarters.json")))
COLUMNS = (
    "source_system",
    "observation_scope",
    "metric_key",
    "operator_icao",
    "marketing_carrier",
    "commercial_designator_as_reported",
    "source_flight_type_code",
    "source_traffic_code",
    "period_id",
    "origin_iata",
    "dest_iata",
    "operations",
    "departures",
    "passengers",
    "seats",
    "load_factor",
    "source_hash",
    "source_locator",
    "downloaded_at",
    "agent_eligible",
)
GRAIN = ["source_hash", "operator_icao", "period_id", "origin_iata", "dest_iata"]


def projection_frame(rows, evidence):
    """Public verification uses only the reviewed exact projection, never private paths."""
    if not isinstance(rows, list) or len(rows) != 219 or any(set(r) != set(COLUMNS) for r in rows):
        raise ValueError("Movement projection requires all 219 reviewed source rows")
    if not isinstance(evidence, dict) or set(evidence) != {
        "originals",
        "airport_reference",
        "source_binding",
    }:
        raise ValueError("Missing reviewed original source evidence")
    originals = evidence["originals"]
    if len(originals) != 3 or {r["sha256"] for r in originals} != set(SOURCE_COUNTS):
        raise ValueError("Movement projection must retain the three exact originals")
    binding = evidence["source_binding"]
    if (
        set(binding) != {"product", "period", "receipt_id", "candidate_as_of", "output_sha256"}
        or (binding["product"], binding["period"]) != ("aerocivil", "2026M07")
        or not re.fullmatch("[a-f0-9]{32}", binding["receipt_id"])
        or set(binding["output_sha256"]) != BINDING_OUTPUTS
        or any(not re.fullmatch("[a-f0-9]{64}", value) for value in binding["output_sha256"].values())
    ):
        raise ValueError("Missing physically checked July source binding")
    frame = pd.DataFrame(rows)
    if (
        not frame.source_system.eq("aerocivil").all()
        or not frame.observation_scope.eq("carrier_route").all()
        or frame.agent_eligible.ne(False).any()
        or frame.marketing_carrier.notna().any()
    ):
        raise ValueError("Source labels/eligibility escaped the reviewed movement scope")
    for original in originals:
        if set(original) != {"sha256", "bytes", "downloaded_at", "source_url", "metadata_sha256"}:
            raise ValueError("Invalid original evidence fields")
        if (original["bytes"], original["downloaded_at"]) != CAPTURES[original["sha256"]]:
            raise ValueError("Original capture timestamp/size must not be renewed")
        if not re.fullmatch("[a-f0-9]{64}", original["metadata_sha256"]):
            raise ValueError("Original sidecar digest missing")
        group = frame[frame.source_hash.eq(original["sha256"])]
        expected_rows, count = SOURCE_COUNTS[original["sha256"]]
        if len(group) != expected_rows or not group.downloaded_at.eq(original["downloaded_at"]).all():
            raise ValueError("Original observation dates or complete source rows changed")
        movement_payload(group)  # Typed counts, provisional codes and duplicate native grain.
        if group.operations.sum() != count:
            raise ValueError("Movement source totals changed")
    if not set(frame.operator_icao) <= set(OPERATORS.values()):
        raise ValueError("Unknown movement operator")
    return frame


def _key(cell):
    if (
        cell["carrier_key"] not in OPERATORS
        or len(cell["source_hashes"]) != 1
        or cell["source_hashes"][0] not in {HISTORICAL_SHA, Q2_SHA}
    ):
        raise ValueError("Unknown Aerocivil operator/hash scope")
    return (
        cell["source_hashes"][0],
        OPERATORS[cell["carrier_key"]],
        cell["period_id"],
        cell["origin_iata"],
        cell["destination_iata"],
    )


def _previous_departures(route, bad, kept, frame):
    previous = route["previous"].get("departures")
    if previous is None or kept:
        return previous  # Independent prior evidence is outside this correction.
    expected = {
        (
            OPERATORS[c["carrier_key"]],
            f"{int(c['period_id'][:4]) - 1}{c['period_id'][4:]}",
            c["origin_iata"],
            c["destination_iata"],
        )
        for c in bad
    }
    relevant = frame[frame.source_hash.eq(HISTORICAL_SHA)]
    cells = relevant.groupby(GRAIN[1:], dropna=False).operations.sum().to_dict()
    if not expected <= set(cells) or sum(cells[key] for key in expected) != previous:
        raise ValueError("Previous Aerocivil comparison cannot be bound to its original; needs review")
    return None


def project_network(before, frame):
    """Match every old observation by original/operator/month/direction before relabelling."""
    result = deepcopy(before)
    months = set(before["expected_months"])
    source = frame[frame.period_id.isin(months)]
    native = source.groupby(GRAIN, dropna=False).operations.sum().to_dict()
    used = set()
    movements_months = set()
    for route in result["routes"]:
        bad = [c for c in route.get("flight_components", []) if "Aerocivil" in c["source_label"]]
        if not bad:
            continue
        if route.get("recorded_movements"):
            raise ValueError("Movement projection is already applied; reuse its receipt")
        matching = []
        for cell in bad:
            key = _key(cell)
            count = cell["departures"]
            if (
                key in used
                or key not in native
                or cell["kind"] != "observed"
                or isinstance(count, bool)
                or not isinstance(count, (int, float))
                or not math.isfinite(count)
                or native[key] != count
                or "<>".join(sorted(key[-2:])) != route["market_key"]
            ):
                raise ValueError(f"Aerocivil historical cell differs from original; needs review: {key}")
            used.add(key)
            selected_key = key
            if key[0] == HISTORICAL_SHA and key[2] == "2026M07":
                selected_key = (JULY_SHA, *key[1:])
                if selected_key not in native or native[selected_key] != count:
                    raise ValueError("Current July edition differs from historical original; needs review")
            matching.append(source.loc[(source[GRAIN] == pd.Series(selected_key, index=GRAIN)).all(axis=1)])
        movement = movement_payload(pd.concat(matching, ignore_index=True))
        if movement["count"] != sum(c["departures"] for c in bad):
            raise ValueError("Semantic correction cannot change a recorded movement count")
        movements_months.update(movement["observed_months"])
        route["recorded_movements"] = movement
        kept = [c for c in route["flight_components"] if "Aerocivil" not in c["source_label"]]
        route["flight_components"] = kept
        active = [c for c in kept if c["kind"] != "scheduled"] or kept
        route["departures"] = sum(c["departures"] for c in active) if active else None
        kinds = {c["kind"] for c in active}
        route["operation_status"] = (
            {
                frozenset({"observed"}): "operated_observed",
                frozenset({"estimated"}): "estimated_from_retained_frequencies",
                frozenset({"scheduled"}): "assigned_slot_not_flown",
            }.get(frozenset(kinds), "mixed_observed_estimated_cells")
            if active
            else "recorded_movements_provisional"
        )
        route["source_label"] = " · ".join(sorted({c["source_label"] for c in active})) if active else LABEL
        route["previous"]["departures"] = _previous_departures(route, bad, kept, frame)
        for direction in route["directions"]:
            cells = [
                c
                for c in active
                if (c["origin_iata"], c["destination_iata"])
                == (direction["origin_iata"], direction["destination_iata"])
            ]
            direction["departures"] = sum(c["departures"] for c in cells) if cells else None
        note = re.sub(r" · Vuelos por celda operador/ruta/sentido/mes:.*$", "", route["coverage_note"])
        route["coverage_note"] = note.replace("Colombia · Aerocivil", LABEL) + " · " + movement["definition"]
    if not used:
        raise ValueError("Expected reviewed Aerocivil cells are absent from baseline")
    hashes, operators = {k[0] for k in used}, {k[1] for k in used}
    if used != {k for k in native if k[0] in hashes and k[1] in operators}:
        raise ValueError("Historical source coverage is incomplete; do not omit original cells")
    coverage = result["coverage_by_source"]
    for label in list(coverage):
        if "Aerocivil" in label:
            del coverage[label]
    coverage[LABEL] = sorted(movements_months)
    Draft202012Validator(NETWORK_FILE_SCHEMA).validate(result)
    return result


def project_coverage(before, frame):
    """Remove only Aerocivil's misclassified Q2 contribution to regular-flight coverage."""
    result = deepcopy(before)
    rows = result["map_coverage"]["rows"]
    expected = {
        (entity, period)
        for entity in ("AEROMEXICO", "VIVA_AEROBUS", "VOLARIS")
        for period in ("2026M04", "2026M05", "2026M06", "2026Q2")
    }
    seen = set()
    for row in rows:
        if row["scope"] != "international":
            continue
        key = (row["entity"], row["period_id"])
        if key not in expected or key in seen:
            raise ValueError("Unexpected/duplicate movement coverage row")
        seen.add(key)
        operators = {"AMX", "SLI"} if key[0] == "AEROMEXICO" else {OPERATORS[key[0]]}
        selected = frame[
            frame.source_hash.eq(Q2_SHA)
            & frame.operator_icao.isin(operators)
            & frame.period_id.isin(period_months(key[1]))
        ]
        count = selected.operations.sum()
        observed = row["observed_regular"]
        if not isinstance(observed, (int, float)) or not math.isfinite(observed) or observed < count:
            raise ValueError("Regular-flight coverage cannot reconcile the Aerocivil correction")
        row["observed_regular"] = observed - count
    if seen != expected:
        raise ValueError("Incomplete movement coverage correction")
    return result


def project_file(name, before, frame):
    if name not in TARGETS:
        raise ValueError("File outside the reviewed movement correction scope")
    return (
        project_coverage(before, frame) if name.endswith("/quarters.json") else project_network(before, frame)
    )
