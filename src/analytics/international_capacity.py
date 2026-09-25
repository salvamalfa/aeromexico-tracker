"""Derive monthly seat capacity for Aeromexico's international routes.

This is the international sibling of the private domestic derivation
(``aeromexico-tracker-data/scripts/derive_aerodatabox_capacity.py``): it maps
each captured flight's AeroDataBox aircraft model to the seat configuration
versioned in ``data/reference/aeromexico_aircraft_seat_capacity.csv`` and
aggregates to monthly route x direction x carrier cells.  Departures, not
passengers, are the unit of the capacity calculation; the passenger estimate
itself lives in :mod:`src.analytics.international_gold` and is never touched
here.

The leg definition matches
:func:`src.analytics.international_route_carrier.build_international_seed`
exactly, so that this table's ``departures_estimated`` reconciles with the
passenger Gold table's ``departures_estimated`` for Aerovías and Aeroméxico
Connect: both start from :func:`~src.analytics.international_route_carrier.
capture_from_sweep` plus :func:`~src.analytics.international_route_carrier.
add_foreign_through_support`, and both keep only legs whose origin and
destination airport map to an AFAC city.  What differs is the grain: the
passenger Gold table publishes one row per fitted *city* route (occasionally
collapsed onto a single dominant airport pair), while this table publishes
every captured airport pair directly, so a handful of low-volume pairs can
appear here without a passenger estimate.  That is expected, not an error,
and is reported by the CLI.

Nothing here calls AeroDataBox or reads a raw provider response: the input is
the already-aggregated, month-scaled ``flights`` column of the transient
silver sweep parquet files, and the output never carries a registration,
flight number, timestamp or aircraft-model count by route.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import pandas as pd

from src.analytics.international_route_carrier import (
    add_foreign_through_support,
    capture_from_sweep,
    city_lookup,
)

# Only Grupo Aeroméxico's own two carrier keys carry a seat configuration;
# a foreign or pooled carrier is out of scope for this table.
SUPPORTED_CARRIERS = {"AEROMEXICO", "AEROMEXICO_CONNECT"}
CAPACITY_ACCEPTANCE = 0.95
CAPACITY_METHOD = "captured_schedule_x_operator_aircraft_configuration_v1"
SEAT_REFERENCE_FILE = "aeromexico_aircraft_seat_capacity.csv"
CITY_CROSSWALK_FILE = "afac_international_city_iata_crosswalk.csv"
FOREIGN_THROUGH_FILE = "afac_international_foreign_through_flights.csv"

OUTPUT_COLUMNS = (
    "period_id",
    "market_key",
    "origin_iata",
    "destination_iata",
    "carrier_key",
    "departures_estimated",
    "seats_estimated",
    "seats_estimated_low",
    "seats_estimated_high",
    "aircraft_model_coverage",
    "capacity_usable",
    "capacity_method",
    "historically_eligible_at_2026_07_13",
)


def load_seat_reference(reference_dir: Path) -> dict[tuple[str, str], dict]:
    """``(raw_model, carrier_key) -> seat capacity row``, refusing a duplicate."""

    frame = pd.read_csv(reference_dir / SEAT_REFERENCE_FILE)
    required = {
        "canonical_model", "raw_model", "carrier_key", "seats_point",
        "seats_low", "seats_high",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"capacity reference lacks {sorted(missing)}")
    key = list(zip(frame["raw_model"], frame["carrier_key"]))
    if len(key) != len(set(key)):
        raise ValueError("capacity reference has a duplicate (raw_model, carrier_key)")
    return {k: row._asdict() for k, row in zip(key, frame.itertuples(index=False))}


def sweep_frames(period: str, silver_dir: Path) -> list[pd.DataFrame]:
    """Every transient sweep part for one month (``..._nucleo``, ``..._resto``, ...)."""

    paths = sorted(silver_dir.glob(f"aerodatabox_international_flights_{period}_*.parquet"))
    if not paths:
        raise FileNotFoundError(
            f"no transient AeroDataBox international sweep parquet for {period} in {silver_dir}"
        )
    return [pd.read_parquet(path) for path in paths]


def captured_legs(
    period: str,
    silver_dir: Path,
    cities: pd.DataFrame,
    foreign_through: pd.DataFrame,
) -> pd.DataFrame:
    """Aerovías/Connect legs in scope, with the same city filter as the seed.

    Mirrors :func:`~src.analytics.international_route_carrier.
    build_international_seed`'s acceptance of a leg: both endpoints must map
    to an AFAC city.  Own-carrier rows already carry a reviewed
    ``carrier_key`` (``AEROMEXICO`` or ``AEROMEXICO_CONNECT``) at capture
    time, so no operator-code lookup is needed here, unlike for a foreign
    carrier.
    """

    capture = add_foreign_through_support(
        capture_from_sweep(sweep_frames(period, silver_dir)), foreign_through
    )
    own = capture[capture["operator_key"].isin(SUPPORTED_CARRIERS)].copy()
    by_airport = city_lookup(cities)
    own["origin_city"] = own["origin_iata"].map(by_airport)
    own["dest_city"] = own["dest_iata"].map(by_airport)
    return own[own["origin_city"].notna() & own["dest_city"].notna()].reset_index(drop=True)


def derive_period(
    period: str,
    legs: pd.DataFrame,
    reference: dict[tuple[str, str], dict],
) -> tuple[pd.DataFrame, dict]:
    """One month's capacity rows, plus the model mix and unmapped-model report."""

    model_mix: Counter[tuple[str, str]] = Counter()
    unmapped: Counter[tuple[str, str]] = Counter()
    groups: dict[tuple[str, str, str], dict] = {}
    for row in legs.itertuples(index=False):
        key = (str(row.origin_iata), str(row.dest_iata), str(row.operator_key))
        group = groups.setdefault(
            key,
            {"candidate": 0.0, "mapped": 0.0, "seats": 0.0, "seats_low": 0.0, "seats_high": 0.0},
        )
        weight = float(row.flights)
        group["candidate"] += weight
        raw_model = str(row.aircraft_model or "").strip()
        model_mix[(raw_model, row.operator_key)] += weight
        capacity = reference.get((raw_model, row.operator_key))
        if capacity is None:
            unmapped[(raw_model, row.operator_key)] += weight
            continue
        group["mapped"] += weight
        group["seats"] += weight * float(capacity["seats_point"])
        group["seats_low"] += weight * float(capacity["seats_low"])
        group["seats_high"] += weight * float(capacity["seats_high"])

    rows = []
    for (origin, destination, carrier), values in sorted(groups.items()):
        candidate = values["candidate"]
        mapped = values["mapped"]
        coverage = mapped / candidate if candidate else 0.0
        usable = mapped > 0 and coverage >= CAPACITY_ACCEPTANCE
        rows.append(
            {
                "period_id": period,
                "market_key": "<>".join(sorted((origin, destination))),
                "origin_iata": origin,
                "destination_iata": destination,
                "carrier_key": carrier,
                "departures_estimated": mapped if usable else None,
                "seats_estimated": values["seats"] if usable else None,
                "seats_estimated_low": values["seats_low"] if usable else None,
                "seats_estimated_high": values["seats_high"] if usable else None,
                "aircraft_model_coverage": coverage,
                "capacity_usable": usable,
                "capacity_method": CAPACITY_METHOD,
                "historically_eligible_at_2026_07_13": False,
            }
        )
    frame = pd.DataFrame(rows, columns=list(OUTPUT_COLUMNS))
    candidate_total = sum(v["candidate"] for v in groups.values())
    mapped_total = sum(v["mapped"] for v in groups.values())
    report = {
        "period_id": period,
        "candidate_departures": candidate_total,
        "mapped_departures": mapped_total,
        "aircraft_model_coverage": mapped_total / candidate_total if candidate_total else 0.0,
        "usable_rows": int(frame["capacity_usable"].sum()) if len(frame) else 0,
        "rows": len(frame),
        "model_mix": dict(sorted(model_mix.items())),
        "unmapped_models": dict(sorted(unmapped.items())),
    }
    return frame, report


def derive(
    periods: list[str],
    *,
    silver_dir: Path,
    reference_dir: Path,
) -> tuple[pd.DataFrame, list[dict]]:
    reference = load_seat_reference(reference_dir)
    cities = pd.read_csv(reference_dir / CITY_CROSSWALK_FILE)
    foreign_through = pd.read_csv(reference_dir / FOREIGN_THROUGH_FILE)

    frames = []
    reports = []
    for period in periods:
        legs = captured_legs(period, silver_dir, cities, foreign_through)
        frame, report = derive_period(period, legs, reference)
        frames.append(frame)
        reports.append(report)
    combined = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=list(OUTPUT_COLUMNS))
    )
    if combined.duplicated(["period_id", "origin_iata", "destination_iata", "carrier_key"]).any():
        raise ValueError("duplicate monthly international route-carrier capacity rows")
    if not combined.empty and not combined["aircraft_model_coverage"].between(0, 1).all():
        raise ValueError("model coverage outside 0-1")
    if not combined.empty and not (
        combined.loc[combined["capacity_usable"], "aircraft_model_coverage"] >= CAPACITY_ACCEPTANCE
    ).all():
        raise ValueError("accepted capacity row below coverage threshold")
    return combined, reports


def main(argv: list[str] | None = None) -> int:
    from src.config import PATHS

    parser = argparse.ArgumentParser(prog="python -m src.analytics.international_capacity")
    parser.add_argument("periods", help="comma-separated months, e.g. 2026M04,2026M05")
    parser.add_argument(
        "--silver", type=Path, default=PATHS.silver / "aerodatabox_international",
        help="directory holding the transient sweep parquet files",
    )
    parser.add_argument(
        "--reference", type=Path, default=PATHS.data / "reference",
        help="directory holding the seat and crosswalk reference CSVs",
    )
    parser.add_argument(
        "--output", type=Path,
        default=PATHS.gold / "fact_aeromexico_international_capacity_estimate.parquet",
    )
    args = parser.parse_args(argv)
    periods = [period.strip() for period in args.periods.split(",") if period.strip()]

    frame, reports = derive(periods, silver_dir=args.silver, reference_dir=args.reference)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(args.output, index=False)

    own = frame[frame["carrier_key"].isin(SUPPORTED_CARRIERS)]
    print(
        f"Wrote {len(frame):,} monthly international route-carrier capacity rows "
        f"({int(own['capacity_usable'].sum())} usable) -> {args.output}"
    )
    for report in reports:
        print(
            f"{report['period_id']}: {report['aircraft_model_coverage']:.2%} model coverage; "
            f"{report['usable_rows']}/{report['rows']} route-direction-carrier cells usable "
            f"({report['candidate_departures']:,.0f} candidate departures)."
        )
        if report["unmapped_models"]:
            print("  modelos sin mapear (peso en vuelos): " + str(
                {f"{model} [{carrier}]": round(weight, 1)
                 for (model, carrier), weight in report["unmapped_models"].items()}
            ))
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
