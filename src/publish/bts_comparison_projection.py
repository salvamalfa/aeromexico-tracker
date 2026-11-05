"""Typed repair of unchanged July BTS comparisons; no current-flight changes."""

import hashlib
import json
import math
import subprocess
from collections import defaultdict
from copy import deepcopy

from src.config import PATHS
from src.source_updates import bts_native
from src.source_updates.bts_native import read
from src.web_export.route_support import comparable_previous_departures

from .source_data_scope import encoded

PRODUCT = "bts_unchanged_source_comparisons"
PERIOD = "2026M07"
HISTORICAL_BASELINE = "089f48a656e301d2380c8d1a23aab5bb6ada728b"
TARGETS = (
    "data/v1/flights/international/2026M07.json",
    "data/v1/flights/entities/INDUSTRY/international/2026M07.json",
)
LABEL = "Estados Unidos · BTS T-100"
MEMBERS = {
    TARGETS[0]: {"AEROMEXICO", "AEROMEXICO_CONNECT"},
    TARGETS[1]: {"AEROMEXICO", "AEROMEXICO_CONNECT", "VOLARIS", "VIVA_AEROBUS"},
}


def _original(reference, year, repo):
    if set(reference) != {"path", "sha256", "metadata_sha256"}:
        raise ValueError("BTS comparison requires exact original and capture-sidecar references")
    selected = repo / reference["path"]
    if any(path.is_symlink() for path in (selected, *selected.parents)):
        raise ValueError("BTS comparison original cannot traverse a symlink")
    path = selected.resolve()
    path.relative_to(repo.resolve())
    if path.is_symlink() or not path.is_file():
        raise ValueError("BTS comparison original must be a regular retained file")
    sidecar = path.with_suffix(path.suffix + ".meta.json")
    raw, meta_raw = path.read_bytes(), sidecar.read_bytes()
    meta = json.loads(meta_raw)
    if (
        hashlib.sha256(raw).hexdigest() != reference["sha256"]
        or meta["sha256"] != reference["sha256"]
        or hashlib.sha256(meta_raw).hexdigest() != reference["metadata_sha256"]
        or meta["source_system"] != "bts_t100"
        or meta["http_status"] != 200
        or meta["bytes"] != len(raw)
    ):
        raise ValueError("BTS comparison capture hashes or source identity differ")
    # Reuse the strict native dictionary, units, grain, closed months, all-six-
    # field DOT identity crosswalk and Silver contract. No name-based matching.
    frame, _ = read("bts_segments", {"archive": (raw, meta)}, f"{year}M07")
    return frame[frame.month.eq(7)].copy(), meta, [path, sidecar]


def _cells(frame, members, year, source_hash):
    selected = frame[frame.carrier_key.isin(members) & frame["class"].isin(("F", "G"))]
    return [
        dict(
            carrier_key=carrier,
            origin_iata=origin,
            destination_iata=destination,
            period_id=f"{year}M07",
            kind="observed",
            source_label=LABEL,
            departures=float(group.departures_performed.sum()),
            source_hashes=[source_hash],
            service_class_departures={
                str(key): float(value)
                for key, value in group.groupby("class").departures_performed.sum().items()
            },
        )
        for (carrier, origin, destination), group in selected.groupby(["carrier_key", "origin", "dest"])
    ]


def _by_market(cells):
    result = defaultdict(list)
    for cell in cells:
        result["<>".join(sorted((cell["origin_iata"], cell["destination_iata"])))].append(cell)
    return result


def context(network):
    value = deepcopy(network)
    for route in value["routes"]:
        route["previous"]["departures"] = None
    return hashlib.sha256(encoded(value)).hexdigest()


def replay(profile, candidate_parent_site, repo=PATHS.root):
    if (
        set(profile) != {"schema_version", "current", "previous", "historical_baseline", "crosswalk"}
        or profile["schema_version"] != "bts_comparison_source_v1"
        or profile["historical_baseline"] != HISTORICAL_BASELINE
    ):
        raise ValueError("Unsupported BTS comparison repair source profile")
    crosswalk = profile["crosswalk"]
    identity_path = repo / "config/carrier_crosswalk.csv"
    if (
        set(crosswalk) != {"path", "sha256"}
        or crosswalk["path"] != "config/carrier_crosswalk.csv"
        or identity_path.resolve() != (bts_native.ROOT / crosswalk["path"]).resolve()
        or identity_path.is_symlink()
        or hashlib.sha256(identity_path.read_bytes()).hexdigest() != crosswalk["sha256"]
    ):
        raise ValueError("BTS exact native identity crosswalk changed or names another runtime input")
    current, current_meta, current_files = _original(profile["current"], 2026, repo)
    previous, previous_meta, previous_files = _original(profile["previous"], 2025, repo)
    # Gold route-source hashes use the canonical SHA of the distinct raw set.
    current_hash = hashlib.sha256(current_meta["sha256"].encode()).hexdigest()
    projection = {
        "product": PRODUCT,
        "period": PERIOD,
        "comparisons": {},
        "unavailable": {},
        "current_context_sha256": {},
    }
    for name in TARGETS:
        network = json.loads((candidate_parent_site / name).read_bytes())
        projection["current_context_sha256"][name] = context(network)
        original = json.loads(
            subprocess.check_output(["git", "show", f"{HISTORICAL_BASELINE}:site/{name}"], cwd=repo)
        )
        old_routes = {route["market_key"]: route for route in original["routes"]}
        if network.get("expected_months") != [PERIOD]:
            raise ValueError("BTS comparison repair requires the exact July current window")
        native = _by_market(_cells(current, MEMBERS[name], 2026, current_hash))
        prior = _by_market(_cells(previous, MEMBERS[name], 2025, previous_meta["sha256"]))
        values, unavailable = {}, {}
        for route in network["routes"]:
            market = route["market_key"]
            old = old_routes.get(market)
            if old is None or old["previous"]["departures"] is None:
                continue  # This correction restores only a previously published comparison.
            active = [cell for cell in route.get("flight_components", []) if cell["kind"] != "scheduled"]
            if not active or any(
                cell["source_label"] != LABEL or cell["kind"] != "observed" for cell in active
            ):
                continue
            if any(
                not cell.get("service_class_departures") or set(cell["service_class_departures"]) - {"F", "G"}
                for cell in active
            ):
                unavailable[market] = "Current native service class is outside the regular F/G repair scope"
                continue
            expected = native.get(market, [])

            def identity(cell):
                return tuple(
                    cell[key] for key in ("carrier_key", "origin_iata", "destination_iata", "period_id")
                )

            actual = {identity(cell): cell for cell in active}
            if set(actual) != {identity(cell) for cell in expected}:
                raise ValueError(
                    f"BTS current operator/direction coverage differs from physical source: {name}/{market}; "
                    f"actual={set(actual)} native={ {identity(cell) for cell in expected} }"
                )
            if any(
                actual[identity(cell)]["departures"] != cell["departures"]
                or actual[identity(cell)]["source_hashes"] != [current_hash]
                or actual[identity(cell)].get("service_class_departures") != cell["service_class_departures"]
                for cell in expected
            ):
                raise ValueError("BTS current counts or lineage differ from physical source")
            prior_cells = prior.get(market, [])
            native_total = sum(cell["departures"] for cell in prior_cells)
            comparable = comparable_previous_departures(network, active, prior_cells, native_total)
            if comparable is None:
                unavailable[market] = (
                    "Native regular operator/direction/source/window cohort differs; no inferred zero"
                )
                continue
            if comparable != old["previous"]["departures"]:
                raise ValueError(
                    "Native BTS comparison does not reproduce the independently signed historical value"
                )
            values[market] = comparable
        projection["comparisons"][name] = values
        projection["unavailable"][name] = unavailable
    before = {name: (candidate_parent_site / name).read_bytes() for name in TARGETS}
    outputs = public_outputs(before, projection)
    return dict(
        source_binding={
            "product": PRODUCT,
            "period": PERIOD,
            "current": profile["current"],
            "previous": profile["previous"],
            "historical_baseline": HISTORICAL_BASELINE,
            "crosswalk": crosswalk,
        },
        projection=projection,
        input_files=[*current_files, *previous_files, identity_path],
        outputs=outputs,
    )


def public_outputs(before, projection):
    if (
        set(before) != set(TARGETS)
        or set(projection) != {"product", "period", "comparisons", "unavailable", "current_context_sha256"}
        or projection["product"] != PRODUCT
        or projection["period"] != PERIOD
        or set(projection["comparisons"]) != set(TARGETS)
        or set(projection["unavailable"]) != set(TARGETS)
    ):
        raise ValueError("BTS comparison repair has a fixed two-network scope")
    outputs = {}
    for name, raw in before.items():
        original = json.loads(raw)
        if context(original) != projection["current_context_sha256"].get(name):
            raise ValueError("BTS comparison current counts, eligibility or other context changed")
        result = deepcopy(original)
        routes = {route["market_key"]: route for route in result["routes"]}
        for market, value in projection["comparisons"][name].items():
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < 0
            ):
                raise ValueError("BTS comparison repair requires a finite native nonnegative count")
            if market not in routes:
                raise ValueError("BTS comparison repair cannot add a current route")
            cells = routes[market].get("flight_components", [])
            if not cells or any(
                cell["source_label"] != LABEL
                or cell["kind"] != "observed"
                or not cell.get("service_class_departures")
                or set(cell["service_class_departures"]) - {"F", "G"}
                for cell in cells
            ):
                raise ValueError("BTS comparison repair cannot change another source or service type")
            prior = routes[market]["previous"]["departures"]
            if prior is not None and prior != value:
                raise ValueError("BTS comparison repair cannot overwrite an existing different comparison")
            routes[market]["previous"]["departures"] = value
        outputs[name] = raw if result == original else encoded(result)
    return outputs
