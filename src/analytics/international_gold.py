"""Build the international route × carrier estimate Gold table the dashboard reads.

The monthly fits of :mod:`src.analytics.international_route_carrier` key a
route by AFAC's city vocabulary (``MADRID-MEXICO``), because that is the grain
of the margins.  The dashboard keys a market by airport pair (``MAD<>MEX``).
The bridge is the capture itself: each carrier's estimate on a city route is
placed on the airport pair where the capture saw that carrier fly it, and on
the route's busiest pair when the carrier's own flights were pooled away.

The Gold table carries every fitted carrier, like its domestic counterpart,
and stays in the private data repository; the dashboard embeds only the
Aerovías and Connect rows.  Nothing here decides whether to publish.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from src.analytics.international_route_carrier import (
    FAMILY_FILE,
    UNALLOCATED,
    _pool,
    carrier_lookup,
    city_lookup,
)

GOLD_TABLE = "fact_route_carrier_international_estimate"
GROUP_KEY = "AEROMEXICO_GROUP"
# Share of Aerovías/Connect cells whose error against T-100 stayed within this
# band in April and May 2026 (136 cells, out of sample): 80 per cent.  The
# band is shown as the estimate's sensitivity range; it is measured, not
# assumed, and should be re-measured as T-100 months arrive.
ESTIMATE_BAND = 0.16
GOLD_COLUMNS = (
    "period_id", "market_key", "origin_iata", "destination_iata", "route_key",
    "carrier_key", "passengers_estimated", "passengers_estimated_low",
    "passengers_estimated_high", "departures_estimated", "is_single_operator_seed",
    "is_pooled_family", "display_source", "estimator_version",
)


def airport_pairs(
    capture: pd.DataFrame,
    cities: pd.DataFrame,
    carriers: pd.DataFrame,
    families: pd.DataFrame,
) -> pd.DataFrame:
    """Flights by city route, fitted carrier and airport pair, from the capture."""

    by_airport = city_lookup(cities)
    by_code = carrier_lookup(carriers)
    known = set(carriers.loc[carriers["confidence"].isin(("resolved", "probable")), "carrier_key"])
    frame = capture.copy()
    frame["origin_city"] = frame["origin_iata"].map(by_airport)
    frame["dest_city"] = frame["dest_iata"].map(by_airport)
    code = frame["operator_iata"].fillna("").str.upper().where(
        lambda column: column != "", frame["operator_icao"].fillna("").str.upper()
    )
    frame["carrier_key"] = frame["operator_key"].where(
        frame["operator_key"].isin(known), code.map(by_code)
    )
    frame = frame.dropna(subset=["origin_city", "dest_city", "carrier_key"])
    frame = _pool(frame, families)
    frame["route_key"] = frame["origin_city"] + "-" + frame["dest_city"]
    return (
        frame.groupby(["period_id", "route_key", "carrier_key", "origin_iata", "dest_iata"],
                      as_index=False)["flights"].sum()
    )


def build_gold(
    estimate: pd.DataFrame,
    capture: pd.DataFrame,
    cities: pd.DataFrame,
    carriers: pd.DataFrame,
    families: pd.DataFrame,
) -> pd.DataFrame:
    """One row per month, airport-pair direction and fitted carrier."""

    pairs = airport_pairs(capture, cities, carriers, families)
    fitted = estimate[~estimate["carrier_key"].isin({GROUP_KEY, UNALLOCATED})].copy()

    own = (pairs.sort_values("flights", ascending=False)
           .drop_duplicates(["period_id", "route_key", "carrier_key"]))
    busiest = (pairs.groupby(["period_id", "route_key", "origin_iata", "dest_iata"], as_index=False)
               ["flights"].sum().sort_values("flights", ascending=False)
               .drop_duplicates(["period_id", "route_key"]))
    placed = fitted.merge(
        own[["period_id", "route_key", "carrier_key", "origin_iata", "dest_iata", "flights"]],
        on=["period_id", "route_key", "carrier_key"], how="left",
    )
    missing = placed["origin_iata"].isna()
    if missing.any():
        fallback = placed.loc[missing, ["period_id", "route_key"]].merge(
            busiest[["period_id", "route_key", "origin_iata", "dest_iata"]],
            on=["period_id", "route_key"], how="left",
        )
        placed.loc[missing, "origin_iata"] = fallback["origin_iata"].to_numpy()
        placed.loc[missing, "dest_iata"] = fallback["dest_iata"].to_numpy()
    unplaced = placed["origin_iata"].isna()
    if unplaced.any():
        raise ValueError(
            "estimate rows with no captured airport pair: "
            + ", ".join(sorted(set(placed.loc[unplaced, "route_key"])))[:500]
        )

    gold = placed.rename(columns={"dest_iata": "destination_iata", "flights": "departures_estimated"})
    gold["market_key"] = [
        "<>".join(sorted((origin, destination)))
        for origin, destination in zip(gold["origin_iata"], gold["destination_iata"])
    ]
    gold["passengers_estimated_low"] = gold["passengers_estimated"] * (1 - ESTIMATE_BAND)
    gold["passengers_estimated_high"] = gold["passengers_estimated"] * (1 + ESTIMATE_BAND)
    gold["is_single_operator_seed"] = gold["is_single_operator_seed"].eq(True)
    gold["is_pooled_family"] = gold["is_pooled_family"].eq(True)
    gold["display_source"] = gold["display_source"].fillna("estimated")
    return gold.loc[:, list(GOLD_COLUMNS)].sort_values(
        ["period_id", "market_key", "origin_iata", "carrier_key"], ignore_index=True
    )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - manual entry
    from src.config import PATHS
    from src.ingest.afac.international_crosswalks import CARRIER_CROSSWALK_FILE, CITY_CROSSWALK_FILE

    parser = argparse.ArgumentParser(prog="python -m src.analytics.international_gold")
    parser.add_argument("periods", help="comma-separated months, e.g. 2026M04,2026M05")
    parser.add_argument("--input", type=Path, default=PATHS.silver / "international_route_carrier")
    parser.add_argument("--output", type=Path, default=PATHS.gold / f"{GOLD_TABLE}.parquet")
    args = parser.parse_args(argv)

    reference = PATHS.data / "reference"
    cities = pd.read_csv(reference / CITY_CROSSWALK_FILE)
    carriers = pd.read_csv(reference / CARRIER_CROSSWALK_FILE).fillna("")
    families = pd.read_csv(reference / FAMILY_FILE)
    parts = []
    for period in (p.strip() for p in args.periods.split(",") if p.strip()):
        parts.append(build_gold(
            pd.read_parquet(args.input / f"estimate_{period}.parquet"),
            pd.read_parquet(args.input / f"capture_{period}.parquet"),
            cities, carriers, families,
        ))
    gold = pd.concat(parts, ignore_index=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    gold.to_parquet(args.output, index=False)
    own = gold[gold["carrier_key"].isin({"AEROMEXICO", "AEROMEXICO_CONNECT"})]
    print(
        f"{len(gold):,} celdas ({len(own):,} de Aerovias/Connect en "
        f"{own['market_key'].nunique()} mercados) -> {args.output}"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
