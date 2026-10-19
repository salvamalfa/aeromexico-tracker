"""Project the accepted Q2 flight cells over the exact audited public baseline.

No source download, estimator fit or financial/analysis export. The input edition
and each replacement's old value are checked before producing any output.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

from src.dashboard.flight_cells import apply_flight_cells
from src.dashboard.flights_html import integration_flight_payload
from src.web_export.flights import _validate
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.schemas import NETWORK_FILE_SCHEMA, QUARTERS_FILE_SCHEMA
from src.web_export.writer import write_json

MEMBERS = {
    "AEROMEXICO": {"AEROMEXICO", "AEROMEXICO_CONNECT"},
    "VIVA_AEROBUS": {"VIVA_AEROBUS"},
    "VOLARIS": {"VOLARIS"},
}
KEY = ("carrier_key", "origin_iata", "destination_iata", "period_id")
MONTHS = ("2026M04", "2026M05", "2026M06")


def cell_key(cell):
    return tuple(cell[k] for k in KEY)


def flight_hashes(directory):
    return {
        f"data/v1/{p.relative_to(directory).as_posix()}": hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((directory / "flights").rglob("*.json"))
    }


def baseline_digest(hashes):
    return hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def index_cells(network, members, periods):
    cells = {}
    for route in network["routes"]:
        for c in route.get("flight_components", []):
            key = cell_key(c)
            if (
                key[0] not in members
                and not (
                    key[0] == "AEROMEXICO_GROUP" and "AEROMEXICO" in members and c["kind"] == "scheduled"
                )
            ) or key[3] not in periods:
                raise ValueError("Projection input cell outside operator/period scope")
            if "<>".join(sorted(key[1:3])) != route["market_key"]:
                raise ValueError("Projection input cell differs from market")
            identity = (*key, c["kind"] == "scheduled")
            if identity in cells:
                raise ValueError("Duplicate or overlapping operative projection cell")
            cells[identity] = deepcopy(c)
    return cells


def project_network(network, members, periods, config, endpoint):
    result = deepcopy(network)
    indexed = index_cells(result, members, periods)
    for change in config["colombia_replacements"]:
        key = cell_key(change)
        if key[0] not in members or key[3] not in periods:
            continue
        old = indexed.get((*key, False))
        if (old is None) != (change["previous_kind"] is None):
            raise ValueError("Colombia replacement presence differs from audited baseline")
        if old and (
            old["kind"] != change["previous_kind"] or old["departures"] != change["previous_departures"]
        ):
            raise ValueError("Colombia replacement differs from audited old cell")
        if change["departures"] - change["previous_departures"] != change["delta"]:
            raise ValueError("Colombia replacement delta does not reconcile")
        indexed[(*key, False)] = {
            **dict(zip(KEY, key)),
            "kind": "observed",
            "departures": change["departures"],
            "source_label": "Colombia · Aerocivil",
            "source_hashes": [config["sources"]["colombia"]["sha256"]],
            "regularity": "regular",
        }
    brazil = {cell_key(c): c for c in config["brazil_regular_cells"]}
    cells = []
    for c in indexed.values():
        if c["kind"] != "observed":
            cells.append(c)
            continue
        source = c["source_label"]
        if "BTS T-100" in source:
            classes = c.get("service_class_departures", {})
            if not classes or abs(sum(classes.values()) - c["departures"]) > 0.01:
                raise ValueError("BTS source classes do not reconcile")
            c["service_class_departures"] = {k: v for k, v in classes.items() if k in {"F", "G"}}
            c["departures"] = sum(c["service_class_departures"].values())
        elif "ANAC" in source:
            proof = brazil.get(cell_key(c))
            if (
                not proof
                or proof["departures"] != c["departures"]
                or proof["source_hash"] not in c["source_hashes"]
            ):
                raise ValueError("ANAC regularity does not match accepted original proof")
        elif "Aerocivil" in source:
            if c.get("regularity") != "regular":
                raise ValueError("Aerocivil cell lacks accepted regular replacement")
        elif "CAA" in source:
            continue  # Commercial attribution has not proved the effective operator.
        else:
            raise ValueError("Unclassified observed source in accepted Q2 projection")
        c["regularity"] = "regular"
        cells.append(c)
    return rebuild_network(result, cells, endpoint)


def rebuild_network(network, cells, endpoint):
    result = deepcopy(network)
    # Clear stale flight values before re-aggregation, retaining historical
    # passenger/capacity fields and the separately identified scheduling cells.
    for route in result["routes"]:
        route["departures"] = None
        route["flight_components"] = []
        route["previous"]["departures"] = None
        route["coverage_note"] = "Observados regulares y frecuencias estimadas; programación separada"
        for direction in route.get("directions", []):
            direction["departures"] = None
        for month in route.get("monthly", []):
            month["departures"] = None
    apply_flight_cells(result, cells, endpoint)
    by_market = defaultdict(list)
    for c in cells:
        by_market["<>".join(sorted((c["origin_iata"], c["destination_iata"])))].append(c)
    for route in result["routes"]:
        components = by_market[route["market_key"]]
        # apply_flight_cells has a legacy fallback to scheduling; that measure
        # is retained as evidence, never used as this projection's headline.
        active = [c for c in components if c["kind"] != "scheduled"]
        route["departures"] = sum(c["departures"] for c in active) if active else None
        for projected, original in zip(route.get("flight_components", []), components):
            if original.get("regularity"):
                projected["regularity"] = original["regularity"]
        # Historical monthly passenger rows keep their values; the complete
        # flight-by-operator/direction/month detail is in flight_components.
        for month in route.get("monthly", []):
            month["departures"] = None
        if not active:
            for direction in route.get("directions", []):
                direction["departures"] = None
        route["previous"]["departures"] = None
    # Reuse the canonical whitelist to supply all nullable fields for new
    # markets (e.g. NLU-CLO April) and exclude internal aggregate fields.
    result["airports"] = list(
        {a["iata"]: a for r in result["routes"] for a in (r["origin"], r["destination"])}.values()
    )
    minimal = {
        "schema_version": "flight_dashboard_payload_v1",
        "metadata": {},
        "quarters": [],
        "monthly_passengers": {},
        "route_network": {"world_geometry": {}},
        "route_networks": {"projection": result},
        "domestic_networks": {},
    }
    return integration_flight_payload(minimal)["route_networks"]["projection"]


def network_path(entity, scope, period):
    base = Path("flights") if entity == "AEROMEXICO" else Path("flights/entities") / entity
    return base / scope / f"{period}.json"


def representation(network, scope):
    if scope == "domestic":
        values = [r["departures"] for r in network["routes"] if r.get("departures") is not None]
        if any(r.get("operation_status", "").startswith("scheduled") for r in network["routes"]):
            raise ValueError("Scheduling is not a domestic frequency estimate")
        return 0, sum(values)
    components = [c for r in network["routes"] for c in r.get("flight_components", [])]
    return (
        sum(c["departures"] for c in components if c["kind"] == "observed"),
        sum(c["departures"] for c in components if c["kind"] == "estimated"),
    )


def project_flights(baseline_data: Path, output_data: Path, config: dict):
    """Write only affected flight JSON; caller preserves the non-flight baseline."""
    if baseline_data.resolve() == output_data.resolve() or output_data.resolve().is_relative_to(
        baseline_data.resolve()
    ):
        raise ValueError("Projection output must be isolated from the trusted baseline")
    if config["schema_version"] != "accepted_flight_projection_v1" or config["quarter"] != "2026Q2":
        raise ValueError("Unrecognized accepted flight projection")
    hashes = flight_hashes(baseline_data)
    if (
        len(hashes) != config["baseline_file_count"]
        or baseline_digest(hashes) != config["baseline_flights_sha256"]
    ):
        raise ValueError("Published flights differ from the audited immutable edition")
    if len({cell_key(c) for c in config["colombia_replacements"]}) != len(config["colombia_replacements"]):
        raise ValueError("Duplicate Colombia accepted replacement")
    if len({cell_key(c) for c in config["brazil_regular_cells"]}) != len(config["brazil_regular_cells"]):
        raise ValueError("Duplicate Brazil regularity proof")
    docs = {
        p.relative_to(baseline_data): json.loads(p.read_text())
        for p in (baseline_data / "flights").rglob("*.json")
    }
    airports = {
        a["iata"]: a
        for d in docs.values()
        for r in d.get("routes", [])
        for a in (r["origin"], r["destination"])
    }
    changed = {}
    for entity, members in MEMBERS.items():
        for period in [*MONTHS, config["quarter"]]:
            path = network_path(entity, "international", period)
            periods = (period,) if period in MONTHS else MONTHS
            changed[path] = project_network(docs[path], members, periods, config, airports.__getitem__)
    # The retained Industry edition did not include every authority source of
    # Aeromexico. Build its flight cells from the three resolved operators,
    # rather than applying deltas against that different aggregate edition.
    for period in [*MONTHS, config["quarter"]]:
        cells = [
            c
            for entity in MEMBERS
            for route in changed[network_path(entity, "international", period)]["routes"]
            for c in route.get("flight_components", [])
        ]
        index_cells(
            {
                "routes": [
                    {
                        "market_key": "<>".join(sorted((c["origin_iata"], c["destination_iata"]))),
                        "flight_components": [c],
                    }
                    for c in cells
                ]
            },
            set.union(*MEMBERS.values()),
            (period,) if period in MONTHS else MONTHS,
        )
        path = network_path("INDUSTRY", "international", period)
        changed[path] = rebuild_network(docs[path], cells, airports.__getitem__)
    rows = []
    for expected in config["expected"]:
        entity, scope, period = (expected[k] for k in ("entity", "scope", "period_id"))
        if entity not in MEMBERS or period not in (*MONTHS, "2026Q2"):
            raise ValueError("Coverage expectation outside accepted scope")
        if scope == "combined":
            continue
        months = (period,) if period in MONTHS else MONTHS
        networks = (
            [docs[network_path(entity, scope, m)] for m in months]
            if scope == "domestic"
            else [changed[network_path(entity, scope, period)]]
        )
        counts = [representation(n, scope) for n in networks]
        observed, estimated = (sum(c[i] for c in counts) for i in (0, 1))
        if observed != (expected["strict_observed_regular_flights"] or 0) or estimated != (
            expected["estimated_flights"] or 0
        ):
            raise ValueError("Projected routes do not reconcile to accepted observed/estimated counts")
        if observed + estimated != expected["strict_regular_observed_plus_estimated_flights"]:
            raise ValueError("Projected represented total differs from accepted count")
        rows.append(
            dict(
                entity=entity,
                scope=scope,
                period_id=period,
                observed_regular=observed,
                estimated=estimated,
                official_regular=expected["official_regular_flights"],
            )
        )
    for expected in config["expected"]:
        if expected["scope"] != "combined":
            continue
        parts = [
            r for r in rows if r["entity"] == expected["entity"] and r["period_id"] == expected["period_id"]
        ]
        if len(parts) != 2:
            raise ValueError("Combined coverage needs both complete source scopes")
        actual = sum(r["observed_regular"] + r["estimated"] for r in parts)
        official = sum(r["official_regular"] for r in parts)
        if (
            actual != expected["strict_regular_observed_plus_estimated_flights"]
            or official != expected["official_regular_flights"]
        ):
            raise ValueError("Combined projected coverage differs from the accepted AFAC universe")
    for period in [*MONTHS, config["quarter"]]:
        industry = representation(changed[network_path("INDUSTRY", "international", period)], "international")
        individuals = [
            representation(changed[network_path(e, "international", period)], "international")
            for e in MEMBERS
        ]
        if industry != tuple(sum(v[i] for v in individuals) for i in (0, 1)):
            raise ValueError("Industry does not reconcile to the three resolved operators")
        if period in MONTHS:
            native = representation(docs[network_path("INDUSTRY", "domestic", period)], "domestic")
            others = [representation(docs[network_path(e, "domestic", period)], "domestic") for e in MEMBERS]
            if native != tuple(sum(v[i] for v in others) for i in (0, 1)):
                raise ValueError("Retained domestic Industry does not reconcile to the selected operators")
    metadata = deepcopy(docs[Path("flights/quarters.json")])
    metadata["map_coverage"] = {
        "source": "AFAC · VLOSREG",
        "source_url": config["sources"]["afac"]["source_url"],
        "source_sha256": config["sources"]["afac"]["sha256"],
        "rows": rows,
    }
    rules = load_privacy_rules()
    for path, value in {**changed, Path("flights/quarters.json"): metadata}.items():
        _validate(
            QUARTERS_FILE_SCHEMA if path.name == "quarters.json" else NETWORK_FILE_SCHEMA,
            value,
            what=str(path),
        )
        check_privacy(value, rules)
        destination = output_data / path
        if destination.exists():
            destination.unlink()  # Break any local staging hardlink before write.
        write_json(destination, value)
    return rows
