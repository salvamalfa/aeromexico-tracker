"""Prove unchanged retained BTS facts against their actual published consumers.

This is a no-change verifier, not a projection for a new BTS edition or a model
refresh. A changed business cell or unpublished native month fails closed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import httpx
import pandas as pd

from src.dashboard.route_entities import AEROMEXICO_ROUTES, EXTRA_ROUTE_ENTITIES
from src.source_updates import readiness
from src.source_updates.checks import period_end
from src.source_updates.closed_editions import accepted

IGNORED = {"record_id", "source_file", "source_hash", "ingested_at"}
GRAIN = ["carrier_key", "route_key", "period_id", "aircraft_type", "service_class"]
LABEL = "Estados Unidos · BTS T-100"
CONSUMERS = (
    "src/dashboard/flights.py",
    "src/dashboard/flight_cells.py",
    "src/dashboard/entity_routes.py",
    "src/dashboard/route_entities.py",
    "src/web_export/flights.py",
    "web/src/views/flights/state.ts",
)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _file(path):
    if path.is_symlink() or path.resolve() != path or not path.is_file():
        raise ValueError("BTS equivalence requires a regular physical file")
    return path.read_bytes()


def _expected(frame, carriers):
    rows = frame[frame.carrier_key.isin(carriers)]
    expected = []
    for keys, block in rows.groupby(["carrier_key", "route_key", "period_id"], sort=True):
        carrier, route, period = keys
        if len(str(route).split("-")) != 2:
            raise ValueError("BTS route needs its two explicit directional airport codes")
        origin, destination = str(route).split("-")
        expected.append(
            dict(
                carrier_key=str(carrier),
                origin_iata=origin,
                destination_iata=destination,
                period_id=str(period),
                kind="observed",
                source_label=LABEL,
                departures=float(block.departures_performed.sum(min_count=1)),
                source_hashes=sorted(set(block.source_hash.dropna().astype(str))),
                service_class_departures={
                    str(k): float(v)
                    for k, v in block.groupby("service_class", dropna=False)
                    .departures_performed.sum()
                    .items()
                },
            )
        )
    return sorted(expected, key=lambda row: json.dumps(row, sort_keys=True))


def _observed(payload, months):
    components = [
        component
        for route in payload["routes"]
        for component in route.get("flight_components", [])
        if component.get("source_label") == LABEL and component.get("period_id") in months
    ]
    return sorted(components, key=lambda row: json.dumps(row, sort_keys=True))


def verify(item, expected_binding, *, site: Path, root: Path):
    if item.get("product") != "bts_segments":
        raise ValueError("BTS equivalence cannot certify another source product")
    native = {
        key: value
        for key, value in item.items()
        if key not in {"source_period", "cadence", "used", "depends_on"}
    }
    native["period"] = item.get("source_period", item["period"])
    if (
        "M" not in native["period"]
        or "M" not in item["period"]
        or period_end(native["period"]) > period_end(item["period"])
    ):
        raise ValueError("BTS native monthly period cannot become a later or quarterly observation")
    checked = readiness.check_task(native, item["candidate_as_of"], item["candidate_as_of"])
    if not accepted(native, checked):
        raise ValueError("Retain BTS own verified source availability before a no-change assertion")
    binding = {key: native[key] for key in ("product", "period", "receipt_id", "candidate_as_of")}
    binding["output_sha256"] = checked["output_sha256"]
    if binding != expected_binding:
        raise ValueError("BTS no-change source differs from the exact outbox binding")
    candidate = Path(item["workspace"]) / "data/gold/fact_route_traffic.parquet"
    active = root / "data/gold/fact_route_traffic.parquet"
    candidate_raw, active_raw = _file(candidate), _file(active)
    if _sha(candidate_raw) != checked["output_sha256"]["gold/fact_route_traffic"]:
        raise ValueError("BTS source fact changed after its complete replay")
    fresh, previous = pd.read_parquet(candidate), pd.read_parquet(active)
    if set(fresh) != set(previous) or fresh.empty or fresh.duplicated(GRAIN).any():
        raise ValueError("BTS input schema/grain differs; use its own reviewed data projection")
    months = sorted(set(fresh.period_id.astype(str)))
    if months != [native["period"]]:
        raise ValueError("BTS facts must preserve their one explicitly verified native month")
    previous = previous[previous.period_id.isin(months)].copy()
    columns = sorted(set(fresh) - IGNORED)
    try:
        pd.testing.assert_frame_equal(
            fresh[columns].sort_values(GRAIN).reset_index(drop=True),
            previous[columns].sort_values(GRAIN).reset_index(drop=True),
            check_exact=True,
            check_dtype=False,
        )
    except AssertionError as error:
        raise ValueError(
            "BTS business facts changed; a new data projection is required, not a no-op"
        ) from error
    manifest_raw = _file(site / "publication_manifest.json")
    manifest = json.loads(manifest_raw)
    pins = {entry["path"]: entry["sha256"] for entry in manifest["files"]}
    commit = subprocess.check_output(["git", "rev-parse", "origin/master"], cwd=root, text=True).strip()
    names = ["publication_manifest.json", "data/v1/flights/quarters.json"]
    listing = json.loads(_file(site / names[-1]))["available_periods"]
    for entity in (AEROMEXICO_ROUTES, *EXTRA_ROUTE_ENTITIES):
        periods = (
            listing["international"]
            if entity.key == "AEROMEXICO"
            else listing["entities"][entity.key]["international"]
        )
        for month in months:
            if month not in periods:
                raise ValueError("BTS native month is not advertised by the published map")
            name = (
                f"data/v1/flights/international/{month}.json"
                if entity.key == "AEROMEXICO"
                else f"data/v1/flights/entities/{entity.key}/international/{month}.json"
            )
            raw = _file(site / name)
            if pins.get(name) != _sha(raw):
                raise ValueError("Published BTS consumer differs from the manifest")
            if _observed(json.loads(raw), {month}) != _expected(
                previous[previous.period_id.eq(month)], entity.t100_carriers
            ):
                raise ValueError("Current published BTS flight cells do not equal retained facts")
            names.append(name)
    observed = []
    with httpx.Client(follow_redirects=False, timeout=30) as client:
        for name in names:
            raw = _file(site / name)
            trusted = subprocess.check_output(["git", "show", f"{commit}:site/{name}"], cwd=root)
            if raw != trusted or (name != "publication_manifest.json" and pins.get(name) != _sha(raw)):
                raise ValueError("BTS no-change must use the actual published Git baseline")
            url = "https://salvamalfa.github.io/aeromexico-tracker/" + name
            response = client.get(url)
            if response.status_code != 200 or _sha(response.content) != _sha(raw):
                raise ValueError("BTS public consumer has not served these exact approved baseline bytes")
            observed.append({"path": name, "url": url, "sha256": _sha(raw), "http_status": 200})
    if (
        _file(candidate) != candidate_raw
        or _file(active) != active_raw
        or _file(site / "publication_manifest.json") != manifest_raw
    ):
        raise ValueError("BTS source, active input or publication changed during no-change verification")
    return {
        "schema_version": "bts_published_equivalence_v1",
        "status": "no_visual_change",
        "source_binding": binding,
        "native_months": months,
        "rows_compared": len(fresh),
        "business_columns": columns,
        "capture_fields_excluded": sorted(IGNORED),
        "source_fact_sha256": _sha(candidate_raw),
        "published_input_fact_sha256": _sha(active_raw),
        "baseline_commit": commit,
        "manifest_sha256": _sha(manifest_raw),
        "served_files": observed,
        "consumer_code": {name: _sha(_file(root / name)) for name in CONSUMERS},
        "new_source_capture": False,
        "new_models_or_estimates": False,
        "publication_performed": False,
    }
