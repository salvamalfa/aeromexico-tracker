"""Audit selectable map flights against AFAC regular operations, without fitting.

Private CLI: --snapshot LABEL SITE GOLD (repeat) --private-root PATH --out PATH.
Observed + estimated is representation, not observed coverage. Scheduling and
attribution are reported separately and never advance the 95% target. Legacy
quarterly exports without monthly detail are not allocated across months.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import pandas as pd

from scripts.research.flight_coverage import (
    ENTITIES,
    bts_index,
    denominator,
    flight_kind,
    load_official,
    regular_observed,
    route_months,
)
from src.dashboard.map_periods import period_months

KINDS = ("observed", "estimated", "scheduled", "attributed")


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sum_known(values):
    """An explicit zero is known; no numerical observations is N/D."""
    numbers = [float(value) for value in values if finite(value)]
    return sum(numbers) if numbers else None


def percent(value, base):
    return 100 * value / base if value is not None and base is not None and base > 0 else None


def allowed_carriers(entity):
    return set(ENTITIES[entity]) | ({"AEROMEXICO_GROUP"} if entity == "AEROMEXICO" else set())


def route_values(route, entity, period, network, counts, observations):
    """Validate exported components; never reweight or resolve source conflicts."""
    totals = {kind: None for kind in KINDS}
    strict, notes = [], set()
    components = route.get("flight_components", [])
    identities = []
    if components:
        seen, operated = set(), set()
        for cell in components:
            key = tuple(cell[k] for k in ("carrier_key", "origin_iata", "destination_iata", "period_id"))
            if key[0] not in allowed_carriers(entity):
                raise ValueError(f"Foreign operator in {entity}: {key[0]}")
            if key[3] not in period_months(period):
                raise ValueError("Component outside requested calendar period")
            if "<>".join(sorted(key[1:3])) != route["market_key"]:
                raise ValueError("Component direction differs from map market")
            kind, value = cell["kind"], cell["departures"]
            if kind not in KINDS or not finite(value) or value < 0:
                raise ValueError("Invalid flight component")
            identity = (*key, kind)
            if identity in seen:
                raise ValueError("Duplicate exported flight component")
            seen.add(identity)
            identities.append(identity)
            if kind in ("observed", "estimated"):
                if key in operated:
                    raise ValueError("Overlapping observed/estimated cell")
                operated.add(key)
            totals[kind] = (totals[kind] or 0) + value
            if kind == "observed":
                source = cell.get("source_label", "")
                classes = cell.get("service_class_departures")
                if "T-100" in source and classes:
                    if (
                        any(not finite(v) or v < 0 for v in classes.values())
                        or abs(sum(classes.values()) - value) > 0.01
                    ):
                        raise ValueError("BTS service classes do not reconcile to component")
                    strict.append(sum(classes.get(k, 0) for k in ("F", "G")))
                    notes.add("BTS F/G regular; L/P excluded")
                elif "Aerocivil" in source:
                    strict.append(value)
                    notes.add("Aerocivil regular service")
                else:
                    notes.add("Observed service class unconfirmed; excluded from strict numerator")
        displayed = sum_known(totals[k] for k in ("observed", "estimated", "attributed"))
        if displayed is None:
            displayed = totals["scheduled"]
        if not finite(route.get("departures")) or abs(displayed - route["departures"]) > 0.01:
            raise ValueError("Map departures differ from component sum")
    elif (kind := flight_kind(route)) is not None:
        totals[kind] = float(route["departures"])
        if kind == "observed":
            months = route_months(
                route, network, period if "Q" in period else f"{period[:4]}Q{(int(period[5:]) - 1) // 3 + 1}"
            )
            value, note = regular_observed(route, months, entity, counts, observations)
            if value is not None:
                strict.append(value)
            notes.add(note)
    return totals, sum_known(strict), notes, identities


def load_networks(site, entity, scope):
    base = site / "data/v1/flights"
    if entity != "AEROMEXICO":
        base /= f"entities/{entity}"
    return {path.stem: json.loads(path.read_text()) for path in sorted((base / scope).glob("*.json"))}


def select_network(documents, scope, period):
    """Domestic estimates and official domestic layers are independent views."""
    if scope == "international":
        return documents.get(period), None
    if "M" in period:
        quarter = f"{period[:4]}Q{(int(period[5:]) - 1) // 3 + 1}"
        native = documents.get(quarter)
        filtered = None
        if native is not None:
            selected = []
            for route in native.get("routes", []):
                components = [c for c in route.get("flight_components", []) if c["period_id"] == period]
                monthly = [c for c in route.get("monthly", []) if c["period_id"] == period]
                if components or monthly:
                    active = [c for c in components if c["kind"] != "scheduled"] or components
                    value = sum_known(c.get("departures") for c in (active or monthly))
                    selected.append(
                        {**route, "departures": value, "monthly": monthly, "flight_components": components}
                    )
            if selected:
                filtered = {**native, "routes": selected, "observed_months": [period]}
        return documents.get(period), filtered
    months = period_months(period)
    if not all(month in documents for month in months):
        return None, documents.get(period)
    grouped = {}
    for month in months:
        for route in documents[month].get("routes", []):
            market = route["market_key"]
            if market not in grouped:
                grouped[market] = {
                    **route,
                    "departures": None,
                    "monthly": [],
                    "directions": [],
                    "flight_components": [],
                }
            target = grouped[market]
            target["departures"] = sum_known([target["departures"], route.get("departures")])
            target["monthly"].extend(route.get("monthly", []))
            target["flight_components"].extend(route.get("flight_components", []))
    return {"routes": list(grouped.values()), "observed_months": months}, documents.get(period)


def summarize_network(network, entity, period, counts, observations):
    fields = {f"{kind}_flights": None for kind in KINDS}
    if network is None:
        return {
            **fields,
            "strict_observed_regular_flights": None,
            "all_exported_routes": None,
            "all_selectable_routes": None,
            "quantified_routes": None,
            "routes_with_unknown_flights": None,
            "initial_top12_routes": None,
            "initial_top12_represented_flights": None,
            "initial_top12_displayed_flights": None,
            "comparability_notes": "Monthly/quarterly export unavailable; no temporal allocation",
            "source_labels": "",
            "estimator_versions": "",
            "component_source_hashes": "",
        }
    routes = network.get("routes", [])
    values, strict, notes, seen = {}, [], set(), set()
    markets = [route["market_key"] for route in routes]
    if len(markets) != len(set(markets)):
        raise ValueError("Duplicate selectable market")
    for route in routes:
        totals, comparable, explanations, identities = route_values(
            route, entity, period, network, counts, observations
        )
        if seen.intersection(identities):
            raise ValueError("Duplicate component across selectable routes")
        seen.update(identities)
        values[route["market_key"]] = totals
        strict.append(comparable)
        notes.update(explanations)
    for kind in KINDS:
        fields[f"{kind}_flights"] = sum_known(value[kind] for value in values.values())
    quantified = [route for route in routes if finite(route.get("departures"))]
    top = sorted(quantified, key=lambda route: (-(route.get("departures") or 0), route["market_key"]))[:12]
    return {
        **fields,
        "strict_observed_regular_flights": sum_known(strict),
        "all_exported_routes": len(routes),
        "all_selectable_routes": len(quantified),
        "quantified_routes": len(quantified),
        "routes_with_unknown_flights": sum(not finite(route.get("departures")) for route in routes),
        "initial_top12_routes": len(top),
        "initial_top12_represented_flights": sum_known(
            values[r["market_key"]][k] for r in top for k in ("observed", "estimated")
        ),
        "initial_top12_displayed_flights": sum_known(r.get("departures") for r in top),
        "comparability_notes": " | ".join(sorted(notes)),
        "source_labels": " | ".join(
            sorted({c.get("source_label", "") for r in routes for c in (r.get("flight_components") or [r])})
        ),
        "estimator_versions": " | ".join(
            sorted(
                {
                    c["estimator_version"]
                    for r in routes
                    for c in r.get("flight_components", [])
                    if c.get("estimator_version")
                }
            )
        ),
        "component_source_hashes": " | ".join(
            sorted(
                {
                    h
                    for r in routes
                    for c in r.get("flight_components", [])
                    for h in c.get("source_hashes", [])
                }
            )
        ),
    }


def audit_snapshot(label, site, gold, official, periods):
    if not (site / "data/v1/flights/quarters.json").is_file():
        raise ValueError("Snapshot lacks exported flights metadata")
    counts = bts_index(gold)
    observations = pd.read_parquet(gold / "fact_international_route_observations.parquet")
    observations["market_key"] = observations.apply(
        lambda row: "<>".join(sorted((str(row.origin_iata), str(row.dest_iata)))), axis=1
    )
    result = []
    for entity in ENTITIES:
        for period in periods:
            scoped = []
            for scope in ("domestic", "international"):
                documents = load_networks(site, entity, scope)
                network, native = select_network(documents, scope, period)
                row = summarize_network(network, entity, period, counts, observations)
                native_summary = summarize_network(native, entity, period, counts, observations)
                row.update(
                    {
                        "snapshot": label,
                        "entity": entity,
                        "scope": scope,
                        "period_id": period,
                        "period_export_available": network is not None,
                        "official_regular_flights": denominator(
                            official, entity, scope, period_months(period)
                        ),
                        "native_scheduled_flights": native_summary["scheduled_flights"],
                        "native_attributed_flights": native_summary["attributed_flights"],
                    }
                )
                finalize(row)
                result.append(row)
                scoped.append(row)
            combined = {
                "snapshot": label,
                "entity": entity,
                "scope": "combined",
                "period_id": period,
                "period_export_available": all(r["period_export_available"] for r in scoped),
            }
            for field in (
                "official_regular_flights",
                *(f"{k}_flights" for k in KINDS),
                "strict_observed_regular_flights",
                "native_scheduled_flights",
                "native_attributed_flights",
            ):
                values = [row[field] for row in scoped]
                combined[field] = (
                    sum_known(values)
                    if field != "official_regular_flights" or all(v is not None for v in values)
                    else None
                )
            # A missing scope means no defensible combined representation total.
            if not combined["period_export_available"]:
                for kind in KINDS:
                    combined[f"{kind}_flights"] = None
                combined["strict_observed_regular_flights"] = None
            combined.update(
                {
                    "all_exported_routes": sum(r["all_exported_routes"] for r in scoped)
                    if combined["period_export_available"]
                    else None,
                    "all_selectable_routes": sum(r["all_selectable_routes"] for r in scoped)
                    if combined["period_export_available"]
                    else None,
                    "quantified_routes": sum(r["quantified_routes"] for r in scoped)
                    if combined["period_export_available"]
                    else None,
                    "routes_with_unknown_flights": sum(r["routes_with_unknown_flights"] for r in scoped)
                    if combined["period_export_available"]
                    else None,
                    "initial_top12_routes": None,
                    "initial_top12_represented_flights": None,
                    "initial_top12_displayed_flights": None,
                    "comparability_notes": "Two separate map scopes; no combined top-12 view. "
                    + " | ".join(r["comparability_notes"] for r in scoped),
                }
            )
            finalize(combined)
            result.append(combined)
    return result


def finalize(row):
    represented = sum_known([row["observed_flights"], row["estimated_flights"]])
    base = row["official_regular_flights"]
    row["represented_observed_plus_estimated_flights"] = represented
    row["representation_pct"] = percent(represented, base)
    row["strict_observed_regular_pct"] = percent(row["strict_observed_regular_flights"], base)
    regular_represented = sum_known([row["strict_observed_regular_flights"], row["estimated_flights"]])
    row["strict_regular_observed_plus_estimated_flights"] = regular_represented
    row["strict_regular_representation_pct"] = percent(regular_represented, base)
    row["target_95_required_flights"] = math.ceil(0.95 * base - 1e-9) if base is not None else None
    row["additional_flights_to_95"] = (
        max(0, row["target_95_required_flights"] - represented)
        if represented is not None and base is not None
        else None
    )
    row["additional_strict_regular_flights_to_95"] = (
        max(0, row["target_95_required_flights"] - regular_represented)
        if regular_represented is not None and base is not None
        else None
    )
    row["strict_regular_metric_definition"] = (
        "Regular-class observed + retained estimated flights / AFAC regular; "
        "nonregular/unconfirmed observations excluded; estimates remain estimates, "
        "not verified performed regular coverage; schedules/attribution excluded"
    )
    row["above_official_regular_total"] = represented is not None and base is not None and represented > base
    row["observed_nonregular_or_unconfirmed_flights"] = (
        row["observed_flights"] - (row["strict_observed_regular_flights"] or 0)
        if row["observed_flights"] is not None
        else None
    )
    row["estimate_quality_status"] = (
        "Retained estimates remain candidate; representation does not establish performed regular flights"
        if row["estimated_flights"] is not None
        else "No estimated flight figure"
    )
    row["metric_definition"] = (
        "Observed + estimated flights represented / AFAC regular; not observed coverage; "
        "schedules/attribution excluded"
    )


def add_baseline_deltas(rows):
    """Compare like calendar grains only; missing monthly exports remain N/D."""
    if not rows:
        return
    first = rows[0]["snapshot"]
    baseline = {(r["entity"], r["scope"], r["period_id"]): r for r in rows if r["snapshot"] == first}
    for row in rows:
        previous = baseline.get((row["entity"], row["scope"], row["period_id"]), {})
        row["baseline_snapshot"] = first
        for metric, column in (
            ("represented_observed_plus_estimated_flights", "delta_vs_baseline_flights"),
            ("representation_pct", "delta_vs_baseline_percentage_points"),
            ("strict_regular_observed_plus_estimated_flights", "delta_vs_baseline_strict_regular_flights"),
            ("strict_regular_representation_pct", "delta_vs_baseline_strict_regular_percentage_points"),
        ):
            value, old = row.get(metric), previous.get(metric)
            row[column] = value - old if value is not None and old is not None else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument(
        "--snapshot", nargs=3, action="append", required=True, metavar=("LABEL", "SITE", "GOLD")
    )
    parser.add_argument("--period", action="append", help="Repeat; default Apr, May, Jun and Q2 2026")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    periods = args.period or ["2026M04", "2026M05", "2026M06", "2026Q2"]
    # Outputs contain private candidate frequencies; keep outside any Git tree.
    for parent in (args.out.resolve(), *args.out.resolve().parents):
        if (parent / ".git").is_file() or (parent / ".git/HEAD").is_file():
            raise ValueError("Private audit output must remain outside a Git checkout")
    official, sources = load_official(args.private_root)
    rows, snapshots = [], {}
    for label, site_arg, gold_arg in args.snapshot:
        if label in snapshots:
            raise ValueError("Snapshot labels must be unique")
        site, gold = Path(site_arg), Path(gold_arg)
        rows.extend(audit_snapshot(label, site, gold, official, periods))
        snapshots[label] = {
            "map_sha256": {
                path.relative_to(site).as_posix(): digest(path)
                for path in sorted((site / "data/v1/flights").rglob("*.json"))
            },
            "gold_sha256": {
                name: digest(gold / name)
                for name in (
                    "fact_route_traffic.parquet",
                    "dim_route.parquet",
                    "fact_international_route_observations.parquet",
                )
            },
        }
    add_baseline_deltas(rows)
    args.out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(args.out / "flight-representation.csv", index=False)
    report = {
        "schema_version": 1,
        "private_candidate_report": True,
        "periods": periods,
        "rows": rows,
        "official_sources": sources,
        "snapshots": snapshots,
        "script_sha256": digest(Path(__file__)),
        "method_sha256": {
            name: digest(Path(__file__).resolve().parents[2] / name)
            for name in ("scripts/research/flight_coverage.py", "src/dashboard/map_periods.py")
        },
        "query_grain": (
            "snapshot/entity/scope/calendar period; component grain operator/directional route/month/kind"
        ),
        "target_numerator": (
            "observed + estimated; schedules and attribution separate; "
            "all selectable routes, never top12 only"
        ),
        "no_temporal_allocation": True,
        "zero_provider_calls": True,
        "zero_model_fits": True,
        "no_activation_or_publication": True,
    }
    (args.out / "flight-representation.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    )
    print(f"Private representation audit: {len(rows)} rows; no APIs, fitting or activation")


if __name__ == "__main__":
    main()
