"""Offline AFAC/seed/AICM feasibility checks; never exports or activates a model.

Run from the repository root with --private-root pointing to the authorized
private backup. Results belong under ignored analysis_runs/research/.
No provider client, credentials, network request or source update is used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
TRAIN, TEST = "2026M04", "2026M05"


def afac_profile() -> dict:
    ref = ROOT / "data/reference"
    routes = pd.read_csv(ref / "afac_od_nacional_regular.csv")
    passengers = pd.read_csv(ref / "afac_carrier_domestic.csv")
    flights = pd.read_csv(ref / "afac_carrier_flights_domestic.csv")
    totals = routes.groupby("period_id")[["vuelos", "pasajeros"]].sum()
    totals["carrier_passengers"] = passengers.groupby("period_id").pasajeros.sum()
    totals["carrier_flights"] = flights.groupby("period_id").vuelos.sum()
    totals["flight_margin_difference"] = totals.vuelos - totals.carrier_flights
    totals["passenger_margin_difference"] = totals.pasajeros - totals.carrier_passengers
    selected = totals.loc[["2026M04", "2026M05", "2026M06", "2026M07"]]
    shares = passengers[passengers.period_id.eq("2026M06")].merge(
        flights[flights.period_id.eq("2026M06")], on=["period_id", "carrier_name"], how="outer"
    )
    shares["passenger_share"] = shares.pasajeros / shares.pasajeros.sum()
    shares["flight_share"] = shares.vuelos / shares.vuelos.sum()
    return {
        "grain": "month x directional city-pair, all airlines; separate month x airline margins",
        "current_passenger_estimator_margin": "passengers, not operations",
        "totals": selected.reset_index().to_dict("records"),
        "shares": shares[["carrier_name", "passenger_share", "flight_share"]].to_dict("records"),
        "new_flight_estimator_activated": False,
    }


def monthly_brand_comparison(private: Path) -> dict:
    slots_path = private / "snapshot/data/silver/domestic_slots/aicm_amx_assigned_flight_days.parquet"
    slots = pd.read_parquet(slots_path)
    key = ["flight_date", "origin_iata", "dest_iata", "flight_number", "flight_suffix", "assigned_time_utc"]
    duplicates = int(slots.duplicated(key).sum())
    slots = slots.drop_duplicates(key)
    months = []
    for period, planned in slots.groupby("period_id"):
        path = private / f"derived/aerodatabox/{period}/route_carrier_flight_counts_{period}.parquet"
        if not path.is_file():
            continue
        capture = pd.read_parquet(path)
        capture = capture[capture.carrier_key.isin(["AEROMEXICO", "AEROMEXICO_CONNECT"])]
        capture = capture[capture.origin_iata.eq("MEX") | capture.dest_iata.eq("MEX")]
        pair = ["origin_iata", "dest_iata"]
        a = planned.groupby(pair).size().rename("slots")
        b = capture.groupby(pair).flights.sum().rename("expanded_seed")
        common = pd.concat([a, b], axis=1).dropna()
        months.append({
            "period": period, "slot_directions": len(a), "seed_directions": len(b),
            "common_directions": len(common), "slot_total": int(a.sum()),
            "slots_on_common_directions": int(common.slots.sum()),
            "expanded_seed_on_common_directions": float(common.expanded_seed.sum()),
            "absolute_count_difference_on_common_directions": float((common.slots-common.expanded_seed).abs().sum()),
        })
    return {
        "months": months, "slot_duplicates_removed": duplicates,
        "flight_identity_match_rate": None,
        "reason": "ADB retains monthly aggregates, without date, time, flight number or per-flight status",
        "alignment": "same labelled month, airport and direction; AM slot holder versus AMX+Connect brand proxy",
        "timezone_and_operating_carrier_exact_match": False,
        "cancellations": "ADB adapter excluded explicit cancellations; retained aggregates cannot reclassify each flight",
        "codeshares": "adapter excluded IsCodeshared; Unknown is not proved unique and cannot be deduplicated again",
        "interpretation": "count discrepancy, never a percentage of matching or performed flights",
    }


def international_status_profile(private: Path) -> list[dict]:
    result = []
    for path in sorted((private / "derived/aerodatabox_international").glob("*/international_capture_route_operator_*.parquet")):
        frame = pd.read_parquet(path)
        weight = float(frame.flights.sum())
        result.append({
            "period": path.parent.name, "frequency_weight": weight,
            "incomplete_status_weight": float(frame.status_incomplete.sum()),
            "unknown_codeshare_weight": float(frame.codeshare_unknown.sum()),
            "incomplete_status_fraction": float(frame.status_incomplete.sum()) / weight if weight else None,
        })
    return result


def out_of_sample_proxy(private: Path) -> dict:
    """April calibration, May official BTS truth; no May carrier cells fitted.

    AICM AM slots are a brand proxy feature, not proof of an AMX operation.
    AFAC May all-carrier margins are available inputs for retrospective
    disaggregation; this is not forecasting an unpublished month.
    """
    gold, ref = ROOT / "data/gold", ROOT / "data/reference"
    dims = pd.read_parquet(gold / "dim_route.parquet")
    traffic = pd.read_parquet(gold / "fact_route_traffic.parquet")
    traffic = traffic[
        traffic.carrier_key.eq("AEROMEXICO") & traffic.period_id.isin([TRAIN, TEST])
        & traffic.service_class.eq("F") & traffic.source_system.eq("bts_t100")
    ]
    traffic = traffic.merge(dims, on="route_key", validate="many_to_one")
    traffic = traffic[traffic.is_transborder_us & (traffic.origin_iata.eq("MEX") | traffic.dest_iata.eq("MEX"))]
    truth = traffic.groupby(["period_id", "origin_iata", "dest_iata"]).departures_performed.sum(min_count=1)
    slot = pd.read_parquet(gold / "fact_aicm_international_scheduled_route_movements.parquet")
    slot = slot.groupby(["period_id", "origin_iata", "dest_iata"]).scheduled_movements.sum()
    cities = pd.read_csv(ref / "afac_international_city_iata_crosswalk.csv")
    # Exclude multi-airport AFAC city labels: do not split a city marginal into
    # airport cells with an unsupported allocation.
    unique = cities.groupby("afac_city").airport_iata.nunique().eq(1)
    unique_cities = set(unique[unique].index)
    airport_city = cities.set_index("airport_iata").afac_city.to_dict()
    seed = pd.read_parquet(private / f"derived/aerodatabox_international/{TRAIN}/international_seed_{TRAIN}.parquet")
    share = seed[seed.carrier_key.eq("AEROMEXICO")].groupby("route_key").weight.sum() / seed.groupby("route_key").weight.sum()
    od = pd.read_csv(ref / "afac_od_internacional_regular.csv")
    od["route_key"] = od.origen + "-" + od.destino
    od = od[od.period_id.eq(TEST)].groupby("route_key").vuelos.sum()
    rows = []
    training_cells = len(truth.loc[[TRAIN]])
    for (_, origin, dest), train_truth in truth.loc[[TRAIN]].items():
        origin_city, dest_city = airport_city.get(origin), airport_city.get(dest)
        if origin_city not in unique_cities or dest_city not in unique_cities:
            continue
        key, train_key, test_key = f"{origin_city}-{dest_city}", (TRAIN, origin, dest), (TEST, origin, dest)
        if test_key not in truth.index or train_key not in slot.index or test_key not in slot.index:
            continue
        if key not in share.index or key not in od.index or slot.loc[train_key] <= 0:
            continue
        rows.append({"train_truth": float(train_truth), "train_slots": float(slot.loc[train_key]),
                     "truth": float(truth.loc[test_key]), "test_slots": float(slot.loc[test_key]),
                     "frozen_seed_afac": float(share.loc[key] * od.loc[key])})
    if not rows:
        return {"train": TRAIN, "test": TEST, "eligible_cells": 0, "conclusion": "No comparable unambiguous cells"}
    frame = pd.DataFrame(rows)
    scale = float(frame.train_truth.sum() / frame.train_slots.sum())
    frame["aicm_calibrated"] = scale * frame.test_slots
    frame["fixed_half_blend"] = .5 * frame.frozen_seed_afac + .5 * frame.aicm_calibrated
    metrics = {}
    for model in ["frozen_seed_afac", "aicm_calibrated", "fixed_half_blend"]:
        error = (frame[model] - frame.truth).abs()
        metrics[model] = {"mae_direction_month": float(error.mean()),
                          "wape": float(error.sum() / frame.truth.sum()),
                          "estimated_total": float(frame[model].sum())}
    return {"train": TRAIN, "test": TEST, "training_candidate_cells": training_cells,
            "eligible_cells": len(frame), "bts_performed_test_total": float(frame.truth.sum()),
            "april_only_calibration": scale, "metrics": metrics,
            "limits": ["retrospective temporal split, not a prospectively untouched validation campaign",
                       "one held-out month", "AMX MEX-US only", "multi-airport city labels excluded",
                       "AICM brand/slot proxy is not an operating-carrier match", "no flight identity match",
                       "AFAC target-month aggregate operations are inputs, never carrier-route target cells",
                       "no inference for unseeded new routes, closures, other airports or future months"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=ROOT / "analysis_runs/research/afac-flights-20261015.json")
    args = parser.parse_args()
    out = args.out.resolve()
    if out.is_relative_to(ROOT) and not out.is_relative_to(ROOT / "analysis_runs/research"):
        raise ValueError("Private research output must stay under ignored analysis_runs/research")
    result = {"schema_version": 1, "provider_calls": 0, "model_activated": False,
              "afac": afac_profile(), "aicm_adb": monthly_brand_comparison(args.private_root),
              "international_status": international_status_profile(args.private_root),
              "out_of_sample": out_of_sample_proxy(args.private_root)}
    result["script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["public_input_sha256"] = {
        rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in [
            "data/reference/afac_od_nacional_regular.csv", "data/reference/afac_carrier_domestic.csv",
            "data/reference/afac_carrier_flights_domestic.csv", "data/reference/afac_od_internacional_regular.csv",
            "data/reference/afac_international_city_iata_crosswalk.csv", "data/gold/fact_route_traffic.parquet",
            "data/gold/dim_route.parquet", "data/gold/fact_aicm_international_scheduled_route_movements.parquet",
        ]
    }
    result["private_input_sha256"] = {
        rel: hashlib.sha256((args.private_root / rel).read_bytes()).hexdigest() for rel in [
            "derived/aerodatabox_international/2026M04/international_seed_2026M04.parquet",
            "snapshot/data/silver/domestic_slots/aicm_amx_assigned_flight_days.parquet",
            *[f"derived/aerodatabox/{period}/route_carrier_flight_counts_{period}.parquet"
              for period in ["2026M04", "2026M05", "2026M06"]],
        ]
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(f"Offline checks saved: {out}; provider calls: 0; no model activated")


if __name__ == "__main__":
    main()
