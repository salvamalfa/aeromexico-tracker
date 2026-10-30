"""Source-verified monthly airport rows for the existing demand table only.

This bridge does not mutate Gold, infer airline traffic or certify a new source
edition. The common source-data gate owns authorization, atomicity and delivery.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import tempfile
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator

from src.dashboard.market_demand import build_market_demand
from src.pipeline.offline import block_network
from src.source_updates import readiness
from src.source_updates.airport_group_native import ASUR, GAP
from src.source_updates.catalog import ROOT
from src.source_updates.closed_editions import accepted
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.writer import dumps_deterministic

PRODUCTS = frozenset({"aicm_traffic", "aifa_traffic", "asur_traffic", "gap_traffic"})
TARGETS = ("data/v1/market-demand.json",)
CONTRACTS = ("market_demand.schema.json",)
SCOPES = {
    "aicm_traffic": ("MEX", 1, "AICM: pasajeros comerciales; total aeroportuario de todas las compañías."),
    "aifa_traffic": (
        "NLU",
        1,
        "AIFA: pasajeros comerciales y de aviación general; total aeroportuario de todas las compañías.",
    ),
    "asur_traffic": (
        "ASUR",
        9,
        "ASUR: sólo sus nueve aeropuertos mexicanos; pasajeros enteros reportados, sin tránsito ni "
        "aviación general. Reconstrucción visible autorizada; no se certifican los bytes originales "
        "del emisor ni revisiones posteriores.",
    ),
    "gap_traffic": (
        "GAP",
        12,
        "GAP: sólo sus doce aeropuertos mexicanos; datos preliminares redondeados a cien pasajeros "
        "(cota de redondeo ±50 por aeropuerto y ±600 para el grupo). Jamaica excluida; "
        "CBX está incluido en Tijuana y no se suma de nuevo.",
    ),
}


def _projection_scope(projection):
    product, period = projection["product"], projection["period"]
    if product not in PRODUCTS or not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("Unknown airport product or native monthly period")
    if projection["quality_note"] != SCOPES[product][2]:
        raise ValueError("Altered airport source meaning")
    key = SCOPES[product][0]
    airports = (
        {key}
        if product in {"aicm_traffic", "aifa_traffic"}
        else (set(ASUR) if product == "asur_traffic" else set(GAP.values()) - {"MBJ", "KIN"})
    )
    expected_group = "GOVERNMENT" if len(airports) == 1 else key
    if (
        len(projection["airports"]) != len(airports)
        or {row["key"] for row in projection["airports"]} != airports
        or any(row["group"] != expected_group for row in projection["airports"])
        or len(projection["groups"]) != (0 if len(airports) == 1 else 1)
        or any(row["key"] != key or row["group"] != key for row in projection["groups"])
        or any(row["period_id"] != period for table in ("airports", "groups") for row in projection[table])
    ):
        raise ValueError("Airport projection would alter an unrelated airport, group or historical month")


def _validate(payload):
    schema = json.loads((ROOT / "contracts/web/market_demand.schema.json").read_bytes())
    Draft202012Validator(schema).validate(payload)
    check_privacy(payload, load_privacy_rules())
    for table in ("airports", "groups"):
        grains = [(row["key"], row["period_id"]) for row in payload[table]]
        if len(grains) != len(set(grains)):
            raise ValueError("Duplicate public airport demand grain")
    if payload["months"] != sorted(set(payload["months"])):
        raise ValueError("Airport demand periods must be unique and ordered")


def _facts(candidate, name, checked):
    key = "gold/" + name
    path = candidate / "data" / (key + ".parquet")
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing regular verified airport fact")
    if hashlib.sha256(path.read_bytes()).hexdigest() != checked["output_sha256"].get(key):
        raise ValueError("Airport fact changed after source validation")
    return pd.read_parquet(path)


def projection_rows(item, checked):
    """Use the existing demand generator over temporary candidate copies, never active Gold."""
    product, period = item["product"], item["period"]
    if product not in PRODUCTS or "M" not in period:
        raise ValueError("Select an admitted airport product and a native monthly period")
    candidate = Path(item["workspace"])
    airports = _facts(candidate, "fact_airport_traffic", checked)
    artifacts = _facts(candidate, "dim_source_artifact", checked)
    key, count, note = SCOPES[product]
    if not airports.country.eq("MX").all():
        raise ValueError("Airport projection must receive the certified Mexico-only Gold")
    expected = airports.period_id.eq(period)
    if airports.loc[expected, "airport_iata"].nunique() != count or expected.sum() != count:
        raise ValueError("Incomplete airport detail for the requested source month")
    if product in {"aicm_traffic", "aifa_traffic"}:
        if set(airports.airport_iata) != {key} or not airports.operator_group.eq("GOVERNMENT").all():
            raise ValueError("Government source cannot overwrite another airport or group")
        groups = pd.DataFrame(columns=["country", "airport_group_key", "period_id", "passengers_total"])
    else:
        if not airports.operator_group.eq(key).all():
            raise ValueError("Airport group differs from the verified product")
        groups = _facts(candidate, "fact_airport_group_traffic", checked)
        if not groups.country.eq("MX").all() or set(groups.airport_group_key) != {key}:
            raise ValueError("Foreign or unrelated airport group cannot enter the Mexico view")
        if groups.period_id.eq(period).sum() != 1:
            raise ValueError("One complete Mexico group row is required for this month")
    # The legacy consumer uses country names; the source facts use ISO codes.
    # Normalize only these disposable copies, preserving original facts and hashes.
    with tempfile.TemporaryDirectory(prefix="airport-demand-projection-") as temporary:
        gold = Path(temporary)
        airports.assign(country="Mexico").to_parquet(gold / "fact_airport_traffic.parquet")
        groups.assign(country="Mexico").to_parquet(gold / "fact_airport_group_traffic.parquet")
        artifacts.to_parquet(gold / "dim_source_artifact.parquet")
        generated = build_market_demand(gold)
    if generated["quarantined_group_months"]:
        raise ValueError("Candidate source detail fails the existing subtotal quarantine")
    rows = {
        name: [row for row in generated[name] if row["period_id"] == period]
        for name in ("airports", "groups")
    }
    if len(rows["airports"]) != count or len(rows["groups"]) != (0 if count == 1 else 1):
        raise ValueError("Existing consumer omitted source rows; do not publish a partial projection")
    projection = {"product": product, "period": period, **rows, "quality_note": note}
    _projection_scope(projection)
    return projection


def _input_files(item):
    candidates = [Path(item["workspace"])]
    availability = item.get("availability", {})
    if "workspace" in availability:
        candidates.append(Path(availability["workspace"]))
    files = []
    for directory in candidates:
        if directory.resolve() != directory or not directory.is_dir():
            raise ValueError("Airport input closure requires its physical candidate directories")
        for path in directory.rglob("*"):
            if path.is_symlink():
                raise ValueError("Do not follow a symlink in the airport evidence closure")
            if path.is_file():
                files.append(path)
    return sorted(set(files))


def replay(profile: dict, baseline: Path) -> dict:
    if (
        set(profile) != {"schema_version", "item", "as_of"}
        or profile["schema_version"] != "airport_demand_source_v1"
    ):
        raise ValueError("Unsupported airport demand source profile")
    item = profile["item"]
    if item.get("product") not in PRODUCTS:
        raise ValueError("Airport demand bridge does not admit this product")
    recipe = {"version": 1, "as_of": profile["as_of"], "required_items": [item["id"]], "items": [item]}
    with block_network():
        selected = readiness.preflight(recipe, ROOT / "tmp/source-updates/airport-demand-source-check")[0]
        checked = readiness.check_task(selected, item["candidate_as_of"], profile["as_of"])
        if not accepted(selected, checked):
            raise ValueError("Airport source needs its own verified availability or admitted closed edition")
        projection = projection_rows(selected, checked)
        inputs = _input_files(selected)
    binding = {key: item[key] for key in ("product", "period", "receipt_id", "candidate_as_of")}
    binding["output_sha256"] = checked["output_sha256"]
    return {"source_binding": binding, "projection": projection, "input_files": inputs}


def public_outputs(before: dict[str, bytes], projection: dict) -> dict[str, bytes]:
    if set(before) != set(TARGETS) or set(projection) != {
        "product",
        "period",
        "airports",
        "groups",
        "quality_note",
    }:
        raise ValueError("Airport projection must name its one permitted existing payload")
    _projection_scope(projection)
    product, period = projection["product"], projection["period"]
    old = json.loads(before[TARGETS[0]])
    _validate(old)
    updated = copy.deepcopy(old)
    for table in ("airports", "groups"):
        rows = projection[table]
        if any(row["period_id"] != period for row in rows):
            raise ValueError("A monthly arrival cannot rewrite its comparative historical months")
        replacement = {(row["key"], row["period_id"]): row for row in rows}
        if len(replacement) != len(rows):
            raise ValueError("Duplicate airport projection row")
        kept = [row for row in old[table] if (row["key"], row["period_id"]) not in replacement]
        updated[table] = sorted([*kept, *rows], key=lambda row: (row["period_id"], row["key"]))
    updated["months"] = sorted(set(old["months"]) | {period})
    prefix = SCOPES[product][2].split(":", 1)[0] + ":"
    updated["quality_notes"] = [note for note in old["quality_notes"] if not note.startswith(prefix)] + [
        projection["quality_note"]
    ]
    _validate(updated)
    return {TARGETS[0]: (dumps_deterministic(updated) + "\n").encode()}
