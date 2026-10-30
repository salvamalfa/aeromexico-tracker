"""AFAC's source-specific passenger basis for airports already in the dashboard.

No new geography, route estimates, historical backfill or airline attribution.
The direct-report series remains intact and the UI selects the two bases.
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pandas as pd

from src.pipeline.offline import block_network
from src.publish.airport_demand_projection import _facts, _input_files, _validate
from src.source_updates import readiness
from src.source_updates.afac_airports import folded
from src.source_updates.catalog import ROOT
from src.source_updates.closed_editions import accepted
from src.web_export.writer import dumps_deterministic

PRODUCTS = frozenset({"afac_airports"})
TARGETS = ("data/v1/market-demand.json",)
CONTRACTS = ("market_demand.schema.json",)
REFERENCE = "data/reference/afac_city_iata_crosswalk.csv"


def normalized_city(value):
    value = str(value).split("/")[0].split("(")[0].strip()
    value = re.sub(r"^CD\.\s*", "CIUDAD ", value)
    key = folded(value)
    # Exact vocabularies already used by the airport/OD sources, not fuzzy joins.
    return {"CIUDADDEMEXICO": "MEXICO", "BAJIO": "DELBAJIO"}.get(key, key)


def crosswalk(reference):
    if reference.is_symlink() or not reference.is_file():
        raise ValueError("AFAC airport demand requires the retained city/IATA crosswalk")
    data = pd.read_csv(reference, dtype=str)
    if set(data) != {"afac_city", "airport_iata"} or data.isna().any().any():
        raise ValueError("AFAC airport crosswalk has a changed schema or missing mapping")
    data["city"] = data.afac_city.map(normalized_city)
    if data.duplicated("city").any() or not data.airport_iata.str.fullmatch("[A-Z]{3}").all():
        raise ValueError("AFAC city/IATA mapping must be exact and unambiguous")
    return dict(zip(data.city, data.airport_iata, strict=True))


def project_rows(item, checked, before, reference):
    native = _facts(Path(item["workspace"]), "fact_afac_airport_observations", checked)
    selected = native[native.period_id.eq(item["period"]) & native.metric_key.eq("passengers")].copy()
    if selected.empty or not selected.period_type.eq("month").all():
        raise ValueError("AFAC airport projection needs its actual requested monthly passenger observations")
    if not selected.service_scope.eq("as_reported_airport_group_statistics").all():
        raise ValueError("AFAC passenger scope changed; do not substitute another traffic universe")
    mapping = crosswalk(reference)
    selected["airport_iata"] = selected.airport_name_as_reported.map(normalized_city).map(mapping)
    allowed = {row["key"] for row in before["airports"]}
    selected = selected[selected.airport_iata.isin(allowed)].copy()
    artifacts = _facts(Path(item["workspace"]), "dim_source_artifact", checked)
    urls = dict(zip(artifacts.artifact_sha256, artifacts.source_url, strict=True))
    rows = []
    for code, block in selected.groupby("airport_iata", sort=True):
        if len(block) != 2 or set(block.market) != {"domestic", "international"}:
            raise ValueError("AFAC airport needs both distinct domestic/international source cells")
        if block.airport_name_as_reported.nunique() != 1 or block.airport_group_as_reported.nunique() != 1:
            raise ValueError("Two source airports cannot be coalesced through one city mapping")
        if block.value.isna().any() or any(float(value) != int(value) or value < 0 for value in block.value):
            raise ValueError("AFAC monthly passengers require explicit nonnegative source counts")
        if block.source_hash.nunique() != 1:
            raise ValueError("AFAC airport markets must come from the same verified workbook")
        first = block.iloc[0]
        rows.append(
            dict(
                key=str(code),
                group=str(first.airport_group_as_reported),
                period_id=item["period"],
                passengers=int(block.value.sum()),
                previous_period=f"{int(item['period'][:4]) - 1}{item['period'][4:]}",
                previous_passengers=None,
                yoy_pct=None,
                source_system=str(first.source_system),
                source_hash=str(first.source_hash),
                source_url=urls.get(str(first.source_hash)),
                captured_at=str(first.ingested_at),
            )
        )
    if not rows:
        raise ValueError("No already-published airport has a verified AFAC mapping for this source month")
    return {
        "product": "afac_airports",
        "period": item["period"],
        "airports": rows,
        "baseline_airport_keys": sorted(allowed),
        "unmapped_existing_airports": sorted(allowed - {row["key"] for row in rows}),
    }


def replay(profile, baseline):
    if (
        set(profile) != {"schema_version", "item", "as_of"}
        or profile["schema_version"] != "afac_airports_demand_source_v1"
    ):
        raise ValueError("Unsupported AFAC airport demand profile")
    item = profile["item"]
    if item.get("product") != "afac_airports":
        raise ValueError("AFAC airport projection cannot consume another source")
    recipe = {"version": 1, "as_of": profile["as_of"], "required_items": [item["id"]], "items": [item]}
    before = json.loads((baseline / TARGETS[0]).read_bytes())
    _validate(before)
    with block_network():
        task = readiness.preflight(recipe, ROOT / "tmp/source-updates/afac-airports-demand-check")[0]
        checked = readiness.check_task(task, item["candidate_as_of"], profile["as_of"])
        if not accepted(task, checked):
            raise ValueError("AFAC airport source needs its complete physical availability and replay")
        reference = ROOT / REFERENCE
        projection = project_rows(task, checked, before, reference)
        inputs = [*_input_files(task), reference]
    binding = {key: item[key] for key in ("product", "period", "receipt_id", "candidate_as_of")}
    binding["output_sha256"] = checked["output_sha256"]
    return {"source_binding": binding, "projection": projection, "input_files": inputs}


def public_outputs(before, projection):
    fields = {"product", "period", "airports", "baseline_airport_keys", "unmapped_existing_airports"}
    if set(before) != set(TARGETS) or set(projection) != fields or projection["product"] != "afac_airports":
        raise ValueError("AFAC airport projection must target its one existing demand payload")
    payload = json.loads(before[TARGETS[0]])
    _validate(payload)
    allowed = sorted({row["key"] for row in payload["airports"]})
    rows, period = projection["airports"], projection["period"]
    if (
        projection["baseline_airport_keys"] != allowed
        or not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period)
        or not rows
        or any(row["key"] not in allowed or row["period_id"] != period for row in rows)
        or len(rows) != len({row["key"] for row in rows})
        or projection["unmapped_existing_airports"] != sorted(set(allowed) - {row["key"] for row in rows})
        or any(row["previous_passengers"] is not None or row["yoy_pct"] is not None for row in rows)
        or any(row["source_system"] != "afac" for row in rows)
    ):
        raise ValueError(
            "AFAC source basis cannot add geography, backfill or invent an interannual comparison"
        )
    updated = copy.deepcopy(payload)
    keys = {(row["key"], row["period_id"]) for row in rows}
    retained = [row for row in payload.get("afac_airports", []) if (row["key"], row["period_id"]) not in keys]
    updated["afac_airports"] = sorted([*retained, *rows], key=lambda row: (row["period_id"], row["key"]))
    updated["months"] = sorted(set(payload["months"]) | {period})
    note = (
        "AFAC: base alternativa de pasajeros por aeropuerto según el libro oficial; sólo aeropuertos "
        "ya presentes en el dashboard, sin atribución a aerolíneas. Sus cifras no sustituyen los reportes "
        f"directos ni se suman con ellos. Cobertura del mes {period}: {len(rows)} de {len(allowed)} "
        "aeropuertos existentes; no se completa un trimestre ni se inventa base interanual."
    )
    updated["quality_notes"] = [
        value for value in payload["quality_notes"] if not value.startswith("AFAC:")
    ] + [note]
    _validate(updated)
    return {TARGETS[0]: (dumps_deterministic(updated) + "\n").encode()}
