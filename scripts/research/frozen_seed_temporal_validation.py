"""Offline held-out-month diagnostic of one frozen flight-share seed.

Uses target-month all-carrier AFAC totals as inputs and independent BTS
performed flights as targets. This is retrospective disaggregation, not an
unpublished-month forecast, national validation, or model activation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from src.source_updates.collection import safe_workspace

CARRIERS = {"AEROMEXICO", "AEROMEXICO_CONNECT", "VIVA_AEROBUS", "VOLARIS"}
HOLDOUTS = ["2026M05", "2026M06", "2026M07"]


def metrics(frame):
    total = float(frame.truth.sum())
    delta = frame.estimate - frame.truth
    positive = frame.truth.gt(0)
    ape = delta[positive].abs() / frame.loc[positive, "truth"]
    return {
        "cells": len(frame),
        "observed_departures": total,
        "estimated_departures": float(frame.estimate.sum()),
        "wape": float(delta.abs().sum() / total) if total else None,
        "signed_bias": float(delta.sum() / total) if total else None,
        "p90_absolute_percentage_error": float(ape.quantile(0.9)) if len(ape) else None,
    }


def build(seed_path, bts_path, afac_path, crosswalk_path, out):
    out = safe_workspace(out)
    if out.exists():
        raise ValueError("Use a new immutable research result path")
    paths = [seed_path, bts_path, afac_path, crosswalk_path, Path(__file__)]
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    seed = pd.read_parquet(seed_path)
    if set(seed.period_id) != {"2026M04"} or seed.weight.lt(0).any():
        raise ValueError("Use exactly the retained April seed, without target-month inputs")
    denominator = seed.groupby("route_key").weight.sum()
    shares = seed.groupby(["route_key", "carrier_key"]).weight.sum()
    shares = shares / shares.index.get_level_values("route_key").map(denominator)
    truth = pd.read_parquet(bts_path)
    truth = truth[
        truth.period_id.isin(HOLDOUTS)
        & truth.carrier_key.isin(CARRIERS)
        & truth["class"].eq("F")
        & (
            (truth.origin_country.eq("MX") & truth.dest_country.eq("US"))
            | (truth.origin_country.eq("US") & truth.dest_country.eq("MX"))
        )
    ]
    key = ["period_id", "carrier_key", "origin", "dest"]
    truth = truth.groupby(key).departures_performed.sum().rename("truth").reset_index()
    crosswalk = pd.read_csv(crosswalk_path)
    unique = crosswalk.groupby("afac_city").airport_iata.nunique().eq(1)
    unambiguous = set(unique[unique].index)
    airport_city = crosswalk.set_index("airport_iata").afac_city.to_dict()
    afac = pd.read_parquet(afac_path)
    afac = afac[
        afac.margin_scope.eq("directed_city_pair_all_carriers")
        & afac.market.eq("international")
        & afac.metric_key.eq("flights_as_reported")
    ]
    od = afac.groupby(["period_id", "origin_city_as_reported", "destination_city_as_reported"]).value.sum()
    rows, excluded = [], []
    for row in truth.to_dict("records"):
        origin, dest = airport_city.get(row["origin"]), airport_city.get(row["dest"])
        route = f"{origin}-{dest}"
        share_key = route, row["carrier_key"]
        od_key = row["period_id"], origin, dest
        if origin not in unambiguous or dest not in unambiguous:
            reason = "unmapped_or_multi_airport_AFAC_city"
        elif share_key not in shares.index or denominator.get(route, 0) <= 0:
            reason = "operator_route_without_frozen_seed_support"
        elif od_key not in od.index:
            reason = "no_target_month_AFAC_route_margin"
        else:
            row["estimate"] = float(shares.loc[share_key] * od.loc[od_key])
            rows.append(row)
            continue
        excluded.append({**row, "reason": reason})
    evaluated = pd.DataFrame(rows)
    cohort_key = ["carrier_key", "origin", "dest"]
    month_counts = evaluated.groupby(cohort_key).period_id.nunique()
    common_keys = set(month_counts[month_counts.eq(len(HOLDOUTS))].index)
    common = evaluated[
        evaluated.apply(lambda row: tuple(row[key] for key in cohort_key) in common_keys, axis=1)
    ]
    result = {
        "status": "offline_retrospective_diagnostic_not_activated",
        "seed_month": "2026M04",
        "holdouts": HOLDOUTS,
        "input_sha256": hashes,
        "scope": "scheduled_passenger_class_F_MX_US_operator_direction_month",
        "all_selected_observed_cells": len(truth),
        "all_selected_observed_departures": float(truth.truth.sum()),
        "evaluated": metrics(evaluated),
        "constant_cohort": {
            "operator_direction_cells": len(common_keys),
            "by_month": {period: metrics(group) for period, group in common.groupby("period_id")},
            "excludes_missing_operator_months": True,
        },
        "by_month": {period: metrics(group) for period, group in evaluated.groupby("period_id")},
        "by_operator": {operator: metrics(group) for operator, group in evaluated.groupby("carrier_key")},
        "by_month_operator": [
            {"period": period, "operator": operator, **metrics(group)}
            for (period, operator), group in evaluated.groupby(["period_id", "carrier_key"])
        ],
        "excluded": excluded,
        "evaluated_cells": rows,
        "missing_reporting_operator_months": [
            {"period": period, "operator": carrier}
            for period in HOLDOUTS
            for carrier in sorted(CARRIERS)
            if truth[truth.period_id.eq(period) & truth.carrier_key.eq(carrier)].empty
        ],
        "limits": [
            "No target-month operator-route observation used to fit shares or choose settings",
            "AFAC target-month all-carrier totals are inputs; this does not forecast an unpublished month",
            "Current revised AFAC and BTS editions, not a historical real-time information set",
            "Unambiguous common support only; missing source cells are not manufactured zeros",
            "No score for predicted cells absent from source: absence is not demonstrated non-operation",
            "April seed and crosswalk development were not prospectively blinded to all BTS information",
            "Monthly error changes do not isolate a causal seed-age effect from market or sample changes",
            "US temporal diagnostic does not validate national routes or Europe, Asia, South America",
            "Does not validate an April seed aged to September or routes with no retained seed support",
        ],
        "activation": "none",
        "approval": "not_created",
        "publication": "not_authorized",
    }
    if hashes != {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}:
        raise ValueError("Research inputs changed during diagnostic")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("seed", "bts", "afac", "crosswalk", "out"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    result = build(args.seed, args.bts, args.afac, args.crosswalk, args.out)
    print(
        json.dumps(
            {
                k: result[k]
                for k in (
                    "status",
                    "all_selected_observed_cells",
                    "all_selected_observed_departures",
                    "evaluated",
                    "by_month",
                    "by_operator",
                    "missing_reporting_operator_months",
                )
            },
            ensure_ascii=False,
        )
    )
