"""Audit map flight coverage against retained official AFAC operations.

Reads only existing workbooks, Gold and a selected site/data/v1 tree. Does
not download, fit a model, change Gold, publish a site or write approvals.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

import openpyxl
import pandas as pd

from src.dashboard.map_periods import period_months

ROOT = Path(__file__).resolve().parents[2]
ENTITIES = {"AEROMEXICO": ("AEROMEXICO", "AEROMEXICO_CONNECT"),
            "VOLARIS": ("VOLARIS",), "VIVA_AEROBUS": ("VIVA_AEROBUS",)}
KINDS = ("observed", "scheduled", "estimated", "attributed")


def clean(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text.upper()) if not unicodedata.combining(c))


def carrier_key(name: str) -> str | None:
    text = clean(name)
    if "CONNECT" in text or "AEROLITORAL" in text:
        return "AEROMEXICO_CONNECT"
    if "AEROMEXICO" in text or "AEROVIAS DE MEXICO" in text:
        return "AEROMEXICO"
    if "VIVAAEROBUS" in text.replace(" ", "") or "AEROENLACES" in text:
        return "VIVA_AEROBUS"
    if (text.startswith("VOLARIS") or "CONCESIONARIA VUELA" in text) and not any(
        suffix in text for suffix in ("COSTA RICA", "EL SALVADOR")
    ):
        return "VOLARIS"
    return None


def official_rows(path: Path, year: int, maximum_month: int = 12) -> list[dict]:
    """VLOSREG's Mexican-operator blocks, regular domestic/international.

    VLOSFLET is not regular service. Foreign subsidiaries Q6/N3 are never
    included in Y4, and blanks/future months are never interpreted as zero.
    """
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        rows = list(workbook["VLOSREG"].iter_rows(values_only=True))
    finally:
        workbook.close()
    records, scope, mexican = [], None, False
    for row in rows:
        name = str(row[0]).strip() if row and row[0] is not None else ""
        # Older VLOSREG files place merged section headings in B or D;
        # carrier names and monthly values still begin in A and B.
        label = clean(" ".join(cell for cell in row if isinstance(cell, str)))
        if label.startswith("EMPRESAS NACIONALES"):
            mexican, scope = True, None
        elif label.startswith("EMPRESAS EXTRANJERAS"):
            mexican, scope = False, None
        elif "REGULAR INTERNACIONAL" in label:
            scope = "international" if mexican else None
        elif "REGULAR NACIONAL" in label:
            scope = "domestic" if mexican else None
        key = carrier_key(name)
        if scope is None or key is None:
            continue
        for month in range(1, maximum_month + 1):
            value = row[month] if len(row) > month else None
            if value is None:
                continue
            if not isinstance(value, (float, int)) or value < 0 or int(value) != value:
                raise ValueError(f"Invalid AFAC operations cell: {year}/{scope}/{key}/{month}")
            records.append({"carrier": key, "scope": scope,
                            "month": f"{year}M{month:02d}", "flights": int(value)})
    keys = [(r["carrier"], r["scope"], r["month"]) for r in records]
    if len(keys) != len(set(keys)):
        raise ValueError("AFAC workbook repeats an operator/scope/month")
    return records


def load_official(private: Path) -> tuple[dict, list[dict]]:
    bronze = private / "snapshot/data/bronze"
    records, evidence = [], []
    for year in range(2015, 2027):
        pattern = (f"afac/{year}/*.xlsx" if year < 2026 else
                   "afac_research/afac_research_airline_summary_2026M07_*.xlsx")
        paths = sorted(bronze.glob(pattern))
        if len(paths) != 1:
            raise ValueError(f"Expected one retained AFAC summary for {year}, got {len(paths)}")
        path = paths[0]
        meta = json.loads(Path(str(path) + ".meta.json").read_text())
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != meta["sha256"]:
            raise ValueError(f"Retained official workbook hash differs for {year}")
        records += official_rows(path, year, 7 if year == 2026 else 12)
        evidence.append({"year": year, "source_url": meta["source_url"], "sha256": digest,
                         "metadata_sha256": hashlib.sha256(Path(str(path) + ".meta.json").read_bytes()).hexdigest(),
                         "sheet": "VLOSREG", "last_month": 7 if year == 2026 else 12})
    return {(r["carrier"], r["scope"], r["month"]): r["flights"] for r in records}, evidence


def denominator(official: dict, entity: str, scope: str, months: list[str]) -> float | None:
    cells = [(carrier, scope, month) for carrier in ENTITIES[entity] for month in months]
    return float(sum(official[cell] for cell in cells)) if cells and all(cell in official for cell in cells) else None


def flight_kind(route: dict) -> str | None:
    if not isinstance(route.get("departures"), (int, float)):
        return None
    components = route.get("flight_components", [])
    if components:
        kinds = {cell["kind"] for cell in components}
        if not kinds <= set(KINDS):
            raise ValueError("Unknown flight component kind")
        return next(iter(kinds)) if len(kinds) == 1 else "mixed"
    status = route.get("operation_status", "")
    if status.startswith("mixed"):
        raise ValueError("Mixed flight route requires flight_components for a reliable audit")
    if status == "assigned_slot_not_flown" or status.startswith("scheduled_"):
        return "scheduled"
    if status == "carrier_inferred_market_observed":
        return "attributed"
    if status.startswith("estimated_"):
        return "estimated"
    return "observed"


def flight_parts(route: dict, network: dict, period: str) -> list[tuple]:
    """Preserve operator/direction/month/source/kind before any audit sum."""
    components = route.get("flight_components", [])
    if not components:
        kind = flight_kind(route)
        months = [period] if "M" in period else route_months(route, network, period)
        return [(kind, route, months)] if kind else []
    expected, seen, operated, parts = set(period_months(period)), set(), set(), []
    for cell in components:
        kind, value = cell["kind"], cell["departures"]
        if (kind not in KINDS or not isinstance(value, (int, float))
                or isinstance(value, bool) or not math.isfinite(value) or value < 0):
            raise ValueError("Invalid flight component kind or departures")
        key = tuple(cell[field] for field in ("carrier_key", "origin_iata", "destination_iata", "period_id"))
        if key[3] not in expected or "<>".join(sorted(key[1:3])) != route["market_key"]:
            raise ValueError("Flight component differs from requested period or market")
        if (*key, kind) in seen or (kind in ("observed", "estimated") and key in operated):
            raise ValueError("Duplicate or overlapping flight component")
        seen.add((*key, kind))
        if kind in ("observed", "estimated"):
            operated.add(key)
        part = {k: v for k, v in route.items() if k != "flight_components"}
        part.update(departures=value, source_label=cell.get("source_label", ""),
                    _flight_component=cell, _audit_record=(route["market_key"], period))
        parts.append((kind, part, [key[3]]))
    active = [part["departures"] for kind, part, _ in parts if kind != "scheduled"]
    total = sum(active) if active else sum(part["departures"] for _, part, _ in parts)
    displayed = route.get("departures")
    if (not isinstance(displayed, (int, float)) or isinstance(displayed, bool)
            or not math.isfinite(displayed) or abs(total - displayed) > .01):
        raise ValueError("Map departures differ from flight component total")
    return parts


def route_months(route: dict, network: dict, quarter: str) -> list[str]:
    if route.get("monthly"):
        return sorted({item["period_id"] for item in route["monthly"]
                       if isinstance(item.get("departures"), (int, float))})
    match = re.match(r"Meses:\s*([\d,\s]+)", route.get("coverage_note", ""))
    if match:
        return [f"{quarter[:4]}M{int(value):02d}" for value in match[1].split(",") if value.strip()]
    return network.get("observed_months", [])


def bts_index(gold: Path) -> dict:
    frame = pd.read_parquet(gold / "fact_route_traffic.parquet")
    routes = pd.read_parquet(gold / "dim_route.parquet")[["route_key", "market_key"]]
    frame = frame[frame.carrier_key.isin(ENTITIES) & frame.source_system.eq("bts_t100")]
    frame = frame.merge(routes, on="route_key", validate="many_to_one")
    keys = ["carrier_key", "period_id", "market_key"]
    all_counts = frame.groupby(keys).departures_performed.sum(min_count=1).to_dict()
    regular = frame[frame.service_class.isin(["F", "G"])].groupby(keys).departures_performed.sum(min_count=1).to_dict()
    return {key: (float(value), float(regular.get(key, 0))) for key, value in all_counts.items()}


def bts_component_index(gold: Path) -> dict:
    """Authoritative Gold counts at operator/directional airport/month grain."""
    frame = pd.read_parquet(gold / "fact_route_traffic.parquet")
    frame = frame[frame.source_system.eq("bts_t100")]
    routes = pd.read_parquet(gold / "dim_route.parquet")[["route_key", "origin_iata", "dest_iata"]]
    frame = frame.merge(routes, on="route_key", validate="many_to_one")
    result = {}
    for key, group in frame.groupby(["carrier_key", "origin_iata", "dest_iata", "period_id"]):
        result[key] = {
            "departures": float(group.departures_performed.sum(min_count=1)),
            "classes": group.groupby("service_class").departures_performed.sum(min_count=1).to_dict(),
            "hashes": sorted(set(group.source_hash.dropna().astype(str))) if "source_hash" in group else [],
        }
    return result


def match_component_hashes(component: dict, expected: list[str]) -> None:
    actual = component.get("source_hashes", [])
    if not isinstance(actual, list) or sorted(set(actual)) != expected:
        raise ValueError("Flight component source hashes differ from authoritative Gold")


def regular_observed(route: dict, months: list[str], entity: str, counts: dict,
                     observations: pd.DataFrame, *, component_counts: dict | None = None) -> tuple[float | None, str]:
    source = route.get("source_label", "")
    if "Aerocivil" in source:
        raise ValueError("Aerocivil recorded movements are not authoritative Gold departures or regular flights")
    if component := route.get("_flight_component"):
        carrier = component["carrier_key"]
        if carrier not in ENTITIES[entity]:
            raise ValueError("Observed component operator differs from requested entity")
        key = tuple(component[field] for field in
                    ("carrier_key", "origin_iata", "destination_iata", "period_id"))
        if "BTS T-100" in source:
            expected = component_counts.get(key) if component_counts is not None else None
            if expected is None:
                raise ValueError("BTS component lacks matching authoritative Gold cell")
            classes = component.get("service_class_departures")
            if (not classes or any(not isinstance(v, (int, float)) or isinstance(v, bool)
                                   or not math.isfinite(v) or v < 0 for v in classes.values())
                    or abs(sum(classes.values()) - component["departures"]) > .01):
                raise ValueError("BTS component needs reconciled service-class departures")
            if classes != expected["classes"] or abs(component["departures"] - expected["departures"]) > .01:
                raise ValueError("BTS component count/classes differ from authoritative Gold")
            match_component_hashes(component, expected["hashes"])
            return sum(expected["classes"].get(k, 0) for k in ("F", "G")), "BTS Gold component F/G; L/P excluded"
        authority = next(((label, system) for label, system in (
            ("Aerocivil", "aerocivil"), ("ANAC", "anac"), ("CAA", "caa")
        ) if label in source), None)
        if authority:
            label, system = authority
            operator = {"AEROMEXICO": "AMX", "AEROMEXICO_CONNECT": "SLI",
                        "VOLARIS": "VOI", "VIVA_AEROBUS": "VIV"}[carrier]
            selected = observations[observations.source_system.eq(system)
                                    & observations.operator_icao.eq(operator)
                                    & observations.period_id.eq(key[3])
                                    & observations.origin_iata.eq(key[1])
                                    & observations.dest_iata.eq(key[2])]
            value = selected.departures.sum(min_count=1)
            if pd.isna(value) or abs(value - component["departures"]) > .01:
                raise ValueError(f"{label} component count differs from authoritative Gold")
            hashes = sorted(set(selected.source_hash.dropna().astype(str))) if "source_hash" in selected else []
            match_component_hashes(component, hashes)
            return None, "Regular-service comparability unverified; excluded from comparable numerator"
        raise ValueError("Observed component source lacks an authoritative Gold resolver")
    if route.get("flight_components"):
        raise ValueError("Split flight_components before comparing observed regular flights")
    if "BTS T-100" in source:
        pairs = [counts.get((entity, month, route["market_key"]), (0, 0)) for month in months]
        if abs(sum(pair[0] for pair in pairs) - route["departures"]) > .51:
            raise ValueError(f"BTS map/Gold count mismatch for {entity}/{route['market_key']}/{months}")
        return sum(pair[1] for pair in pairs), "BTS scheduled classes F/G; nonscheduled L/P excluded from comparable numerator"
    return None, "Regular-service comparability unverified; excluded from comparable numerator"


def audit(site: Path, official: dict, gold: Path, *, independent_map_periods: bool = False) -> list[dict]:
    base = site / "data/v1/flights"
    metadata = json.loads((base / "quarters.json").read_text())
    financial = {r["period_id"] for r in metadata["quarters"]}
    counts = bts_index(gold)
    component_counts = None
    observations = pd.read_parquet(gold / "fact_international_route_observations.parquet")
    observations["market_key"] = observations.apply(
        lambda row: "<>".join(sorted((str(row.origin_iata), str(row.dest_iata)))), axis=1)
    quarters = sorted({f"{month[:4]}Q{(int(month[5:]) - 1) // 3 + 1}" for _, _, month in official})
    result = []
    for entity in ENTITIES:
        folder = base if entity == "AEROMEXICO" else base / "entities" / entity
        for scope in ("domestic", "international"):
            documents = {p.stem: json.loads(p.read_text()) for p in (folder / scope).glob("*.json")}
            for quarter in quarters:
                expected = period_months(quarter)
                rows = defaultdict(list)
                if scope == "domestic":
                    for month in expected:
                        for route in documents.get(month, {}).get("routes", []):
                            for kind, part, represented in flight_parts(route, documents[month], month):
                                rows[kind].append((part, represented))
                    native = documents.get(quarter, {})
                    for route in native.get("routes", []):
                        for kind, part, represented in flight_parts(route, native, quarter):
                            if kind != "estimated":
                                rows[kind].append((part, represented))
                else:
                    network = documents.get(quarter, {})
                    for route in network.get("routes", []):
                        for kind, part, represented in flight_parts(route, network, quarter):
                            rows[kind].append((part, represented))
                full_denom = denominator(official, entity, scope, expected)
                for kind in KINDS:
                    selected = rows[kind]
                    months = sorted({month for _, represented in selected for month in represented})
                    comparable, definitions, comparable_sources = 0.0, set(), 0
                    if kind == "observed":
                        for route, represented in selected:
                            if route.get("_flight_component") and "BTS T-100" in route.get("source_label", ""):
                                if component_counts is None:
                                    component_counts = bts_component_index(gold)
                            value, definition = regular_observed(
                                route, represented, entity, counts, observations, component_counts=component_counts)
                            if value is not None:
                                comparable += value
                                comparable_sources += 1
                            definitions.add(definition)
                    month_denom = denominator(official, entity, scope, months)
                    reason = ("Observed minimum share of official regular operations; no claim of full network capture"
                              if kind == "observed" else
                              "Programmed is not performed" if kind == "scheduled" else
                              "Estimated frequencies are not observed flight coverage" if kind == "estimated" else
                              "Market attribution does not establish carrier operations")
                    result.append({
                        "entity": entity, "scope": scope, "quarter": quarter, "kind": kind,
                        "map_flights": sum(route["departures"] for route, _ in selected) if selected else None,
                        "mapped_route_records": len({route.get("_audit_record", (route["market_key"], tuple(represented)))
                                                     for route, represented in selected}), "represented_months": "|".join(months),
                        "map_source_labels": "|".join(sorted({route.get("source_label", "") for route, _ in selected})),
                        "pending_calendar_months": "|".join(month for month in expected if month not in months),
                        "period_selectable": bool(selected) and (independent_map_periods or quarter in financial or quarter in documents),
                        "official_regular_quarter_flights": full_denom,
                        "official_regular_represented_month_flights": month_denom,
                        "comparable_observed_regular_flights": comparable if comparable_sources else None,
                        "observed_minimum_quarter_pct": 100 * comparable / full_denom
                            if comparable_sources and full_denom and comparable <= full_denom + .51 else None,
                        "observed_share_represented_months_pct": 100 * comparable / month_denom
                            if comparable_sources and month_denom and comparable <= month_denom + .51 else None,
                        "estimated_coverage_pct": None, "programmed_coverage_pct": None,
                        "definition": reason, "comparability_notes": "|".join(sorted(definitions)),
                        "coverage_status": "source totals inconsistent" if full_denom and comparable > full_denom + .51 else
                            "no map figure" if not selected else
                            "partial official denominator" if full_denom is None else "bounded comparable universe",
                    })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--site", type=Path, default=ROOT / "site")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--independent-map-periods", action="store_true",
                        help="The audited preview implements the separate map-period selector")
    args = parser.parse_args()
    official, sources = load_official(args.private_root)
    report = audit(args.site, official, ROOT / "data/gold", independent_map_periods=args.independent_map_periods)
    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(report).to_csv(args.out / "quarterly-flight-coverage.csv", index=False)
    (args.out / "sources.json").write_text(json.dumps({"schema_version": 1, "official_sources": sources,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "public_input_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in [
            "data/gold/fact_route_traffic.parquet", "data/gold/dim_route.parquet",
            "data/gold/fact_international_route_observations.parquet", "src/dashboard/map_periods.py", "uv.lock"]},
        "map_input_sha256": {p.relative_to(args.site).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in sorted((args.site / "data/v1/flights").rglob("*.json"))},
        "independent_map_periods": args.independent_map_periods,
        "zero_provider_calls": True, "no_model_activated": True}, ensure_ascii=False, indent=2) + "\n")
    print(f"Coverage matrix: {len(report)} rows; no APIs, source refresh, model fit or activation")


if __name__ == "__main__":
    main()
