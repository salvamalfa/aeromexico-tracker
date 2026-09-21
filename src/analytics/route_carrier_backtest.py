"""Measure the route-carrier estimator where the joint cell is actually published.

``backtest_against_t100`` in :mod:`src.analytics.route_carrier` already hides the
T-100 carrier split, rebuilds it from the two margins alone and reports one
weighted share error per month.  That single number is what produced the 1.98 pp
figure quoted throughout the stage reports, and quoting it alone is what makes it
misleading: it is a passenger-weighted average over a market of short transborder
routes, and it says nothing about where the error concentrates.

The question this module exists to answer is different and is the one that has to
be settled before the same estimator is pointed at Madrid, Seoul or Bogotá:
**how does the error behave as the market changes?**  A mean cannot answer that.
So the same hide-and-rebuild experiment is run once and then read along four
cuts that each stand in for something the international cube will have and the
domestic one does not:

- **by carrier**, because Aeroméxico's own error is what the dashboard shows,
  and an average over 58 carriers can hide it;
- **by number of competitors on the route**, because a duopoly and a six-carrier
  route are different estimation problems and the international network has both;
- **by market size**, because a passenger-weighted mean is dominated by the
  largest routes and the thin ones are where a dashboard cell is most wrong;
- **by great-circle distance**, because the honest objection to reusing a
  transborder error for Europe or Asia is that no T-100 route is that long, and
  the only way to show what distance does to the error is to measure it.

Nothing here changes the estimator.  It consumes the same seed contract, calls
the same :func:`~src.analytics.route_carrier.estimate_route_carrier`, and only
reports.  No API units are involved: T-100 is already in Gold.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.analytics.route_carrier import (
    SEED_COLUMNS,
    T100_SEED_METRICS,
    estimate_route_carrier,
    load_t100_panel,
)
from src.config import PATHS


BACKTEST_VERSION = "route_carrier_backtest_v1"

EARTH_RADIUS_KM = 6371.0088

# Bands chosen so the boundaries mean something operationally rather than being
# round numbers: a regional jet leg, a narrowbody transcontinental leg, and the
# longest transborder markets.  The point of the table they produce is the gap
# at the end: MEX-MAD is about 9,050 km and MEX-NRT about 11,300 km, so every
# band here sits below the routes the international cube most needs.
DISTANCE_BANDS_KM = (0.0, 1_500.0, 2_500.0, 3_500.0, np.inf)
DISTANCE_LABELS = ("<1,500 km", "1,500-2,500 km", "2,500-3,500 km", ">3,500 km")

# Quartiles rather than deciles: with a few hundred competitive routes a month,
# deciles put too few routes in a cell for its error to mean anything.
SIZE_QUANTILES = (0.0, 0.25, 0.5, 0.75, 1.0)
SIZE_LABELS = ("Q1 mas pequenas", "Q2", "Q3", "Q4 mas grandes")


def great_circle_km(
    lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series
) -> pd.Series:
    """Haversine distance in kilometres, vectorised over aligned series."""

    phi1, phi2 = np.radians(lat1.astype(float)), np.radians(lat2.astype(float))
    delta_phi = phi2 - phi1
    delta_lambda = np.radians(lon2.astype(float) - lon1.astype(float))
    chord = (
        np.sin(delta_phi / 2) ** 2
        + np.cos(phi1) * np.cos(phi2) * np.sin(delta_lambda / 2) ** 2
    )
    return pd.Series(
        2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(np.clip(chord, 0.0, 1.0))),
        index=lat1.index,
    )


def route_distances(route_keys: pd.Series, gold_dir: Path | None = None) -> pd.Series:
    """Great-circle distance for ``ORIGIN-DEST`` IATA keys, NaN where unknown.

    A missing coordinate stays missing.  A route whose distance cannot be
    computed is reported under its own band rather than being folded into a
    neighbouring one, because guessing the band would quietly manufacture the
    very relationship this module is trying to measure.
    """

    gold = gold_dir or PATHS.gold
    airports = pd.read_parquet(
        gold / "dim_airport.parquet", columns=["airport_iata", "latitude", "longitude"]
    ).dropna(subset=["airport_iata"]).drop_duplicates("airport_iata").set_index("airport_iata")

    split = route_keys.astype(str).str.split("-", n=1, expand=True)
    frame = pd.DataFrame({"origin": split[0], "dest": split[1]}, index=route_keys.index)
    for side in ("origin", "dest"):
        frame[f"{side}_lat"] = frame[side].map(airports["latitude"])
        frame[f"{side}_lon"] = frame[side].map(airports["longitude"])
    distance = great_circle_km(
        frame["origin_lat"], frame["origin_lon"], frame["dest_lat"], frame["dest_lon"]
    )
    return distance.where(frame[["origin_lat", "dest_lat"]].notna().all(axis=1))


def rebuild_from_margins(
    panel: pd.DataFrame, *, seed_metric: str = "departures"
) -> pd.DataFrame:
    """Hide the published split, rebuild it, and return truth beside estimate.

    The experiment is exactly the one the production estimator faces: the only
    inputs are the two margins the panel implies and a seed of supply.  The
    joint cell is never shown to the fit.
    """

    if seed_metric not in T100_SEED_METRICS:
        raise ValueError(f"seed_metric must be one of {sorted(T100_SEED_METRICS)}")
    missing = {"period_id", "route_key", "carrier_key", "passengers"} - set(panel.columns)
    if missing:
        raise ValueError(f"panel is missing required column(s): {', '.join(sorted(missing))}")

    seed = panel.rename(columns={seed_metric: "weight"})[list(SEED_COLUMNS)]
    route_totals = panel.groupby(["period_id", "route_key"], as_index=False)["passengers"].sum()
    carrier_totals = panel.groupby(["period_id", "carrier_key"], as_index=False)["passengers"].sum()

    estimate, diagnostics = estimate_route_carrier(seed, route_totals, carrier_totals)
    if not diagnostics.empty and not diagnostics["converged"].all():
        unconverged = diagnostics.loc[~diagnostics["converged"], "period_id"].tolist()
        raise RuntimeError(f"IPF did not converge for period(s): {unconverged}")

    merged = panel.merge(
        estimate[["period_id", "route_key", "carrier_key", "passengers_estimated"]],
        on=["period_id", "route_key", "carrier_key"],
        how="left",
    )
    merged["passengers_estimated"] = merged["passengers_estimated"].fillna(0.0)
    merged = merged.merge(
        route_totals.rename(columns={"passengers": "route_passengers"}),
        on=["period_id", "route_key"],
    )
    carriers_on_route = (
        panel.groupby(["period_id", "route_key"])["carrier_key"]
        .nunique()
        .rename("carriers_on_route")
        .reset_index()
    )
    merged = merged.merge(carriers_on_route, on=["period_id", "route_key"])

    merged["true_share"] = merged["passengers"] / merged["route_passengers"]
    merged["estimated_share"] = merged["passengers_estimated"] / merged["route_passengers"]
    merged["share_error_pp"] = 100 * (merged["true_share"] - merged["estimated_share"]).abs()
    merged["passenger_error"] = (merged["passengers"] - merged["passengers_estimated"]).abs()
    merged["diagnostics_converged"] = True
    return merged


def _summarise(group: pd.DataFrame) -> pd.Series:
    """Both a passenger-weighted and an unweighted read of the same cells.

    The weighted figure is what a national total is made of; the unweighted one
    is what a reader sees when they open a single thin route.  Reporting only
    the first is what makes 1.98 pp sound like a guarantee.
    """

    weights = group["route_passengers"]
    return pd.Series(
        {
            "observations": int(len(group)),
            "routes": int(group["route_key"].nunique()),
            "passengers": float(group["passengers"].sum()),
            "share_mae_pp_weighted": float(np.average(group["share_error_pp"], weights=weights)),
            "share_mae_pp_unweighted": float(group["share_error_pp"].mean()),
            "share_p90_pp": float(group["share_error_pp"].quantile(0.90)),
            "share_max_pp": float(group["share_error_pp"].max()),
            "passenger_error_pct": float(
                100 * group["passenger_error"].sum() / group["passengers"].sum()
            )
            if group["passengers"].sum() > 0
            else float("nan"),
        }
    )


def stratified_backtest(
    *,
    period_prefix: str = "2025",
    seed_metric: str = "departures",
    min_carriers: int = 2,
    gold_dir: Path | None = None,
    panel: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Run the hide-and-rebuild experiment once and read it along four cuts.

    Single-carrier routes are excluded from every cut: the fit recovers them by
    construction, so including them would pull every average towards zero and
    flatter the estimator exactly where it is doing no work.
    """

    if panel is None:
        panel = load_t100_panel(period_prefix=period_prefix, gold_dir=gold_dir)
    if panel.empty:
        raise ValueError(f"No T-100 rows found for period prefix {period_prefix!r}")

    rebuilt = rebuild_from_margins(panel, seed_metric=seed_metric)
    competitive = rebuilt[rebuilt["carriers_on_route"] >= min_carriers].copy()
    if competitive.empty:
        raise ValueError("No competitive routes available for the backtest")

    competitive["distance_km"] = route_distances(competitive["route_key"], gold_dir=gold_dir)
    competitive["distance_band"] = pd.cut(
        competitive["distance_km"], bins=list(DISTANCE_BANDS_KM), labels=list(DISTANCE_LABELS),
        right=False,
    ).astype(object).where(competitive["distance_km"].notna(), "distancia desconocida")

    route_size = (
        competitive.groupby(["period_id", "route_key"])["route_passengers"].first().reset_index()
    )
    route_size["size_band"] = route_size.groupby("period_id")["route_passengers"].transform(
        lambda values: pd.qcut(
            values.rank(method="first"), q=list(SIZE_QUANTILES), labels=list(SIZE_LABELS)
        ).astype(object)
    )
    competitive = competitive.merge(
        route_size[["period_id", "route_key", "size_band"]], on=["period_id", "route_key"]
    )

    competitive["competition_band"] = np.where(
        competitive["carriers_on_route"] >= 4,
        "4 o mas operadores",
        np.where(competitive["carriers_on_route"] == 3, "3 operadores", "2 operadores"),
    )

    cuts = {
        "por_periodo": "period_id",
        "por_operador": "carrier_key",
        "por_competencia": "competition_band",
        "por_tamano": "size_band",
        "por_distancia": "distance_band",
    }
    report: dict[str, pd.DataFrame] = {}
    for name, column in cuts.items():
        report[name] = (
            competitive.groupby(column, dropna=False)[
                [
                    "route_key",
                    "share_error_pp",
                    "passenger_error",
                    "passengers",
                    "route_passengers",
                ]
            ]
            .apply(_summarise, include_groups=False)
            .reset_index()
            .sort_values("passengers", ascending=False)
            .reset_index(drop=True)
        )

    overall = _summarise(competitive).to_frame().T
    overall.insert(0, "seed_metric", seed_metric)
    overall.insert(0, "period_prefix", period_prefix)
    overall.insert(0, "backtest_version", BACKTEST_VERSION)
    report["global"] = overall
    report["celdas"] = competitive
    return report


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - manual entry point
    import argparse

    parser = argparse.ArgumentParser(prog="python -m src.analytics.route_carrier_backtest")
    parser.add_argument("--period-prefix", default="2025")
    parser.add_argument("--seed-metric", default="departures", choices=sorted(T100_SEED_METRICS))
    args = parser.parse_args(argv)

    report = stratified_backtest(
        period_prefix=args.period_prefix, seed_metric=args.seed_metric
    )
    for name in ("global", "por_operador", "por_competencia", "por_tamano", "por_distancia"):
        frame = report[name]
        if name == "por_operador":
            frame = frame.head(12)
        print(f"\n=== {name} ===")
        print(frame.to_string(index=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
