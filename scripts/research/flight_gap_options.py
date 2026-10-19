"""Offline, private comparison of official flight candidates; never activates data.

Keep the AFAC denominator and retained estimator fixed. Colombia replaces exact
operator/direction/month cells, including negative changes. Brazil only changes
the regularity classification of already represented observations after checking
their original records. Source-native calendars remain source-native.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pandas as pd

from scripts.research.flight_coverage import ENTITIES, load_official
from scripts.research.flight_representation import audit_snapshot, finalize, load_networks, select_network
from src.ingest.international_routes import anac_rows
from src.transform.international_routes import folded

OPERATORS = {"AMX": "AEROMEXICO", "SLI": "AEROMEXICO_CONNECT", "VIV": "VIVA_AEROBUS", "VOI": "VOLARIS"}
MONTHS = ("2026M04", "2026M05", "2026M06")
KEY = ("carrier_key", "origin_iata", "destination_iata", "period_id")
NATIVE = (
    "anio",
    "mes",
    "aeropuerto_operacion",
    "origen",
    "destino",
    "empresa",
    "explotador",
    "tipo_vuelo",
    "trafico",
    "tipo_operacion",
)
ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def captured_json(path):
    meta = json.loads(Path(str(path) + ".meta.json").read_text())
    if digest(path) != meta["sha256"]:
        raise ValueError("Original capture hash mismatch")
    return json.loads(path.read_text()), meta


def colombia_capture_pair(records_meta, count_meta):
    queries = []
    for meta in (records_meta, count_meta):
        url = urlsplit(meta["source_url"])
        if (url.scheme, url.netloc, url.path) != ("https", "www.datos.gov.co", "/resource/jh8x-n6h6.json"):
            raise ValueError("Unexpected Colombia capture source")
        queries.append(parse_qs(url.query))
    records, count = queries
    if not records.get("$where") or records.get("$where") != count.get("$where"):
        raise ValueError("Colombia count and records select different universes")
    if count.get("$select") != ["count(*)"] or "$select" in records or "$offset" in records:
        raise ValueError("Unexpected Colombia count/record projection")
    return integer(records["$limit"][0])


def integer(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not an operations count")
    number = float(value)
    if not 0 <= number < float("inf") or int(number) != number:
        raise ValueError("Expected nonnegative integer operations")
    return int(number)


def colombia_cells(rows, airports, expected_count):
    """Preserve native grain before aggregation; absence never creates zero."""
    if len(rows) != expected_count:
        raise ValueError("Colombia pagination/count mismatch")
    seen, totals, locators = set(), defaultdict(int), defaultdict(list)
    for index, row in enumerate(rows, 1):
        native = tuple(row[k] for k in NATIVE)
        if native in seen:
            raise ValueError("Duplicate native Colombia record")
        seen.add(native)
        period = f"{integer(row['anio'])}M{integer(row['mes']):02d}"
        if period not in MONTHS or row["explotador"] not in OPERATORS:
            raise ValueError("Capture outside selected operators/calendar")
        if row["tipo_vuelo"] != "S" or row["trafico"] != "I":
            continue
        a, b = row["origen"], row["destino"]
        if a not in airports or b not in airports:
            raise ValueError("Unmapped Colombia endpoint")
        countries = (airports[a]["country"], airports[b]["country"])
        if set(countries) != {"MX", "CO"}:
            continue
        local = a if countries[0] == "CO" else b
        if row["aeropuerto_operacion"] != local:
            raise ValueError("Colombia reporting airport mismatch")
        if row["tipo_operacion"] != ("SALIDA" if a == local else "LLEGADA"):
            raise ValueError("Colombia direction mismatch")
        key = (OPERATORS[row["explotador"]], airports[a]["airport_iata"], airports[b]["airport_iata"], period)
        totals[key] += integer(row["totaloperaciones"])
        locators[key].append(f"record:{index}")
    return [
        {**dict(zip(KEY, key)), "departures": value, "source_locators": locators[key]}
        for key, value in sorted(totals.items())
    ]


def operative_cells(site):
    result = {}
    for entity in ENTITIES:
        network, _ = select_network(load_networks(site, entity, "international"), "international", "2026Q2")
        if network is None:
            raise ValueError("Missing international baseline")
        for route in network["routes"]:
            if not route.get("flight_components"):
                raise ValueError("Baseline requires operator/month components")
            for cell in route["flight_components"]:
                if cell["kind"] not in ("observed", "estimated"):
                    continue
                key = tuple(cell[k] for k in KEY)
                if key in result:
                    raise ValueError("Overlapping operative baseline cells")
                result[key] = cell
    return result


def replacement_deltas(candidates, baseline):
    changes, seen = [], set()
    for candidate in candidates:
        key = tuple(candidate[k] for k in KEY)
        if key in seen:
            raise ValueError("Duplicate candidate cell")
        seen.add(key)
        old = baseline.get(key)
        if old and old["kind"] == "observed" and "Aerocivil" not in old.get("source_label", ""):
            raise ValueError("Observed source conflict requires explicit reconciliation")
        previous = old["departures"] if old else 0
        changes.append(
            {
                **candidate,
                "previous_kind": old["kind"] if old else None,
                "previous_departures": previous,
                "delta": candidate["departures"] - previous,
            }
        )
    return changes


def verified_anac(gold, bronze, baseline):
    """Verify the original locator, operator, scope, class, count and map cell."""
    selected = gold[(gold.source_system == "anac") & gold.period_id.isin(MONTHS)]
    if selected.empty:
        raise ValueError("Missing ANAC regularity evidence")
    proof, seen_locators = [], set()
    for relative, group in selected.groupby("source_file"):
        path = bronze / str(relative).replace("\\", "/")
        source_hash = digest(path)
        if set(group.source_hash) != {source_hash}:
            raise ValueError("ANAC original hash differs from Gold")
        originals = anac_rows(path.read_bytes())
        for row in group.to_dict("records"):
            locator = re.fullmatch(r"record:([1-9][0-9]*)", row["source_locator"])
            if locator is None or int(locator[1]) > len(originals):
                raise ValueError("Invalid ANAC original record locator")
            identity = (source_hash, row["source_locator"])
            if identity in seen_locators:
                raise ValueError("Duplicate ANAC original record locator")
            seen_locators.add(identity)
            index = int(locator[1])
            raw = originals[index - 1]
            name = folded(raw["EMPRESA_NOME"])
            operator = "SLI" if "AEROLITORAL" in name else "AMX" if "AEROVIAS DE MEXICO" in name else None
            if (
                operator != row["operator_icao"]
                or raw["GRUPO_DE_VOO"] != "REGULAR"
                or raw["NATUREZA"] != "INTERNACIONAL"
                or f"{integer(raw['ANO'])}M{integer(raw['MES']):02d}" != row["period_id"]
                or raw["AEROPORTO_DE_ORIGEM_SIGLA"] != row["origin_icao"]
                or raw["AEROPORTO_DE_DESTINO_SIGLA"] != row["dest_icao"]
                or integer(raw["DECOLAGENS"]) != row["departures"]
            ):
                raise ValueError("ANAC original does not prove regular operated cell")
            key = (OPERATORS[operator], row["origin_iata"], row["dest_iata"], row["period_id"])
            cell = baseline.get(key, {})
            if (
                cell.get("kind") != "observed"
                or "ANAC" not in cell.get("source_label", "")
                or cell.get("departures") != row["departures"]
                or source_hash not in cell.get("source_hashes", [])
            ):
                raise ValueError("ANAC evidence does not reconcile to existing map cell")
            proof.append(
                {
                    **dict(zip(KEY, key)),
                    "departures": row["departures"],
                    "source_hash": source_hash,
                    "source_locator": row["source_locator"],
                }
            )
        del originals
    if len({tuple(r[k] for k in KEY) for r in proof}) != len(proof):
        raise ValueError("Duplicate ANAC evidence cell")
    return proof


def apply_options(rows, changes, regularity):
    result = deepcopy(rows)
    for row in result:
        row["snapshot"] = "candidate_not_activated"
        if row["scope"] == "domestic":
            continue
        if row.get("period_export_available") is False:
            # A quarter's observations do not identify a missing monthly
            # baseline automatically. Do not turn N/D into a Colombia-only
            # numerator or discard the retained domestic part of a total.
            row["candidate_update_status"] = "Not applied: baseline period/scope unavailable"
            continue
        # A totals-only scenario does not rebuild routes, top-12 or source labels.
        # Retain these only in the separately labelled baseline, never as candidate facts.
        for key in list(row):
            if (
                key.startswith("all_")
                or key.startswith("initial_top12_")
                or key
                in (
                    "quantified_routes",
                    "routes_with_unknown_flights",
                    "source_labels",
                    "estimator_versions",
                    "component_source_hashes",
                    "comparability_notes",
                )
            ):
                del row[key]
        row["route_metrics_status"] = "Not recomputed; inspect baseline only for retained route metadata"
        members = ENTITIES[row["entity"]]
        months = MONTHS if row["period_id"] == "2026Q2" else (row["period_id"],)
        for change in changes:
            if change["carrier_key"] not in members or change["period_id"] not in months:
                continue
            previous = change["previous_departures"]
            if change["previous_kind"] == "estimated":
                row["estimated_flights"] -= previous
            elif change["previous_kind"] == "observed":
                row["observed_flights"] -= previous
                row["strict_observed_regular_flights"] -= previous
            row["observed_flights"] = (row["observed_flights"] or 0) + change["departures"]
            row["strict_observed_regular_flights"] = (row["strict_observed_regular_flights"] or 0) + change[
                "departures"
            ]
        for proof in regularity:
            if proof["carrier_key"] in members and proof["period_id"] in months:
                row["strict_observed_regular_flights"] = (
                    row["strict_observed_regular_flights"] or 0
                ) + proof["departures"]
        finalize(row)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("site", "gold", "private-root", "bronze", "colombia", "colombia-count", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.out.resolve().is_relative_to(ROOT):
        raise ValueError("Write private candidate evidence outside the public checkout")
    before = {p.name: digest(p) for p in sorted(args.gold.glob("*.parquet"))}
    exported_before = {
        str(p.relative_to(args.site)): digest(p)
        for p in sorted((args.site / "data/v1/flights").rglob("*.json"))
    }
    code_before = {
        name: digest(ROOT / name)
        for name in (
            "scripts/research/flight_gap_options.py",
            "scripts/research/flight_representation.py",
            "scripts/research/flight_coverage.py",
            "src/dashboard/map_periods.py",
            "src/ingest/international_routes.py",
            "src/transform/international_routes.py",
        )
    }
    official, official_evidence = load_official(args.private_root)
    baseline = audit_snapshot("retained", args.site, args.gold, official, [*MONTHS, "2026Q2"])
    airports = {
        r["airport_icao"]: r
        for r in pd.read_parquet(args.gold / "dim_airport.parquet").to_dict("records")
        if r["airport_icao"]
    }
    records, meta = captured_json(args.colombia)
    count, count_meta = captured_json(args.colombia_count)
    limit = colombia_capture_pair(meta, count_meta)
    if len(count) != 1 or set(count[0]) != {"count"} or not 0 < integer(count[0]["count"]) <= limit:
        raise ValueError("Invalid Colombia count or insufficient bounded page")
    candidates = colombia_cells(records, airports, integer(count[0]["count"]))
    cells = operative_cells(args.site)
    changes = replacement_deltas(candidates, cells)
    proof = verified_anac(
        pd.read_parquet(args.gold / "fact_international_route_observations.parquet"), args.bronze, cells
    )
    proposal = apply_options(baseline, changes, proof)
    after = {p.name: digest(p) for p in sorted(args.gold.glob("*.parquet"))}
    if before != after:
        raise ValueError("Gold changed during the audit")
    if exported_before != {
        str(p.relative_to(args.site)): digest(p)
        for p in sorted((args.site / "data/v1/flights").rglob("*.json"))
    }:
        raise ValueError("Baseline exports changed during audit")
    if code_before != {name: digest(ROOT / name) for name in code_before}:
        raise ValueError("Method code changed during audit")
    report = {
        "schema_version": 1,
        "private_candidate_report": True,
        "activation": "none",
        "paid_requests": 0,
        "publication": "not_authorized",
        "gold_sha256": before,
        "baseline_export_sha256": exported_before,
        "method_code_sha256": code_before,
        "auditor_sha256": digest(Path(__file__)),
        "afac_evidence": official_evidence,
        "colombia_capture": meta,
        "colombia_count_capture": count_meta,
        "colombia_changes": changes,
        "anac_regularity_proof": proof,
        "baseline": baseline,
        "candidate": proposal,
        "limits": [
            "Fixed AFAC regular denominator; estimates remain estimates, not observed coverage",
            "Source-native calendars; no flight-by-flight harmonization",
            "Argentina held for calendar and physical-continuity issues",
            "CAA physical operator unconfirmed; scheduling never adds operated flights",
            "Missing Colombia cells keep the baseline; absence is not zero",
            "Runtime authority/operator handling and lineage integration still require review",
        ],
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "flight-gap-options.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": "candidate_audited", "rows": len(proposal), "activation": "none"}))


if __name__ == "__main__":
    main()
