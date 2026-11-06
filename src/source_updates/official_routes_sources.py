"""Offline physical replay of selected originals for the new map, never activation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.dashboard.official_routes import build_payload
from src.dashboard.official_routes_geo import airport_points, city_points
from src.source_updates.afac_margins import parse as parse_afac
from src.source_updates.bts_native import read as read_bts
from src.source_updates.official_routes_geography import verify_cities


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def physical(ref: dict, root: Path) -> Path:
    if set(ref) != {"path", "sha256"}:
        raise ValueError("Official route reference requires path and SHA256")
    path = root / ref["path"]
    if Path(ref["path"]).is_absolute() or ".." in path.parts or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Official route reference escapes candidate workspace")
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file() or digest(path) != ref["sha256"]:
        raise ValueError("Official route physical input changed or is missing")
    return path


def original(ref: dict, root: Path) -> tuple[bytes, dict]:
    path = physical(ref, root)
    meta = json.loads(path.with_suffix(path.suffix + ".meta.json").read_bytes())
    if meta["sha256"] != ref["sha256"]:
        raise ValueError("Official original and retained sidecar disagree")
    return path.read_bytes(), meta


def replay(selection: dict, root: Path) -> tuple[dict, dict, list[Path]]:
    """Certify native rows and emit deterministic payload plus private cell evidence."""
    if set(selection) != {"schema_version", "source_as_of", "afac", "bts", "cities", "airports", "geonames"} or selection.get("schema_version") != "official_route_selection_v1":
        raise ValueError("Unsupported official route input selection")
    cutoff = datetime.fromisoformat(selection["source_as_of"].replace("Z", "+00:00"))
    if cutoff.tzinfo is None:
        raise ValueError("Official source cutoff requires a timezone")
    afac, bts, sources, evidence, inputs = [], [], [], [], []
    periods = set()
    for item in selection["afac"]:
        if item["period"] in periods:
            raise ValueError("Duplicate AFAC source edition")
        periods.add(item["period"])
        selected = {role: original(item[role], root) for role in ("routes", "carriers")}
        if any(meta["source_system"] not in {"afac", "afac_research"} for _, meta in selected.values()):
            raise ValueError("Official AFAC role requires an AFAC original")
        frame, checks = parse_afac(selected, item["period"])
        afac.append(frame)
        evidence.append(dict(source="afac", period=item["period"], checks=checks))
        for role, (_, meta) in selected.items():
            sources.append(dict(id=f"afac-{item['period'][:4]}-{role}", label="AFAC SASE" if role == "routes"
                                else "AFAC resumen por empresa", url=meta["source_url"],
                                source_period=item["period"], captured_at=meta["downloaded_at"], sha256=meta["sha256"]))
            path = physical(item[role], root)
            inputs.extend([path, path.with_suffix(path.suffix + ".meta.json")])
    periods = set()
    for item in selection["bts"]:
        if item["period"][:4] in periods:
            raise ValueError("Duplicate BTS observation year")
        periods.add(item["period"][:4])
        raw = original(item["archive"], root)
        if raw[1]["source_system"] != "bts_t100":
            raise ValueError("Official BTS role requires a BTS original")
        frame, checks = read_bts("bts_segments", {"archive": raw}, item["period"])
        if checks["observed_max_period"] != item["period"]:
            raise ValueError("BTS selected source period must disclose the actual latest retained month")
        # read() checks the requested month; regular-flight departures never hide invalid quantities.
        if frame.departures_performed.isna().any() or frame.departures_performed.lt(0).any():
            raise ValueError("Invalid observed departures")
        bts.append(frame)
        evidence.append(dict(source="bts", period=item["period"], checks=checks))
        meta = raw[1]
        sources.append(dict(id=f"bts-{item['period'][:4]}", label="BTS T-100 International Segment All Carriers",
                            url=meta["source_url"], source_period=item["period"],
                            captured_at=meta["downloaded_at"], sha256=meta["sha256"]))
        path = physical(item["archive"], root)
        inputs.extend([path, path.with_suffix(path.suffix + ".meta.json")])
    city_path, airport_path, geo_path = (physical(selection[k], root) for k in ("cities", "airports", "geonames"))
    original(selection["airports"], root)
    geo_checks = verify_cities(city_path, geo_path, selection["geonames"]["sha256"])
    evidence.append(dict(source="geography", checks=geo_checks))
    inputs.extend([city_path, airport_path, geo_path, airport_path.with_suffix(airport_path.suffix + ".meta.json"),
                   geo_path.with_suffix(geo_path.suffix + ".meta.json")])
    cities = city_points(pd.read_csv(city_path))
    airports = airport_points(pd.read_csv(airport_path, low_memory=False))
    afac_frame, bts_frame = pd.concat(afac, ignore_index=True), pd.concat(bts, ignore_index=True)
    if any(datetime.fromisoformat(s["captured_at"].replace("Z", "+00:00")) > cutoff for s in sources):
        raise ValueError("Official source cutoff predates a retained capture")
    payload = build_payload(afac_frame, bts_frame, cities, airports, sources,
                            source_as_of=selection["source_as_of"])
    evidence = dict(schema_version="official_route_certification_v1", source_checks=evidence,
                    afac_rows=len(afac_frame), bts_rows=len(bts_frame), dataset_version=payload["dataset_version"],
                    activation="none", publication="not_authorized", network_requests=0, paid_requests=0)
    return payload, evidence, inputs
