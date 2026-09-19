"""Estimate passengers by route and carrier through iterative proportional fitting.

AFAC publishes two marginals of the same microdata cube and never the cell:
the origin-destination workbook gives passengers per route, the airline
workbook gives passengers per carrier.  Neither identifies the joint
distribution on its own, so the split has to be estimated from a seed matrix
that carries the *structure* of supply (flights or seats per route and
carrier) and is then fitted to both published marginals.

Iterative proportional fitting is the right tool because of what it ignores.
Scaling a whole row or a whole column of the seed leaves the fitted result
unchanged, so a carrier's average gauge and a route's ADS-B coverage gap both
cancel out; only the *relative* structure within a route survives.  The fit is
the maximum-entropy estimate consistent with both marginals.

Accuracy is measured, not asserted: :func:`backtest_against_t100` hides the
carrier split of the US DOT T-100 data already in gold, rebuilds it from the
two marginals alone, and reports the error.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from src.config import PATHS


ESTIMATOR_VERSION = "route_carrier_ipf_v1"
# Sparse seeds make the fit converge slowly: a carrier whose network barely
# overlaps the rest of the market propagates its correction a few routes per
# sweep, and the transborder panel needs ~1,500 sweeps.  The cap is set well
# above that because each sweep is two vectorised scalings.
DEFAULT_MAX_ITERATIONS = 5_000
# Tolerance is relative to the grand total: an absolute passenger threshold
# would sit below float64 resolution on margins of tens of millions.  1e-8 of
# a three-million-passenger market is three hundredths of one passenger.
DEFAULT_TOLERANCE = 1e-8

# Columns a seed table must carry.  A seed row says "this carrier offered this
# much supply on this route in this period"; the unit is irrelevant because IPF
# is invariant to per-row and per-column scaling.
SEED_COLUMNS = ("period_id", "route_key", "carrier_key", "weight")


class InfeasibleMarginsError(ValueError):
    """A marginal demands passengers where the seed offers no supply at all."""


@dataclass(frozen=True, slots=True)
class IpfResult:
    """A fitted matrix plus everything needed to judge whether to trust it."""

    matrix: np.ndarray
    iterations: int
    converged: bool
    max_row_deviation: float
    max_col_deviation: float
    column_scale: float

    @property
    def is_usable(self) -> bool:
        return self.converged


def fit_ipf(
    seed: np.ndarray,
    row_targets: np.ndarray,
    column_targets: np.ndarray,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    tolerance: float = DEFAULT_TOLERANCE,
) -> IpfResult:
    """Fit ``seed`` to both marginals, preserving its zeros and its structure.

    Zeros in the seed are structural: a carrier that offered nothing on a route
    is never handed passengers.  The two marginals rarely sum to the same total
    (AFAC's own publications differ by a few dozen passengers per quarter), so
    the column targets are rescaled to the row total and the factor is reported
    rather than hidden.
    """

    seed = np.asarray(seed, dtype=float)
    row_targets = np.asarray(row_targets, dtype=float)
    column_targets = np.asarray(column_targets, dtype=float)

    if seed.ndim != 2:
        raise ValueError(f"Seed must be two-dimensional, got shape {seed.shape}")
    if seed.shape != (row_targets.size, column_targets.size):
        raise ValueError(
            f"Seed shape {seed.shape} does not match margins "
            f"({row_targets.size}, {column_targets.size})"
        )
    if np.any(seed < 0) or np.any(row_targets < 0) or np.any(column_targets < 0):
        raise ValueError("Seed and margins must be non-negative")
    if not np.isfinite(seed).all():
        raise ValueError("Seed contains non-finite values")

    row_total = float(row_targets.sum())
    column_total = float(column_targets.sum())
    if row_total <= 0 or column_total <= 0:
        raise ValueError("Both margins must carry a positive total")

    column_scale = row_total / column_total
    column_targets = column_targets * column_scale

    _assert_feasible(seed, row_targets, column_targets)

    matrix = np.where(seed > 0, seed, 0.0)
    # Rows and columns whose target is zero carry no passengers at all.
    matrix[row_targets == 0, :] = 0.0
    matrix[:, column_targets == 0] = 0.0

    iterations = 0
    row_deviation = column_deviation = float("inf")
    for iterations in range(1, max_iterations + 1):
        matrix = _scale_axis(matrix, row_targets, axis=1)
        matrix = _scale_axis(matrix, column_targets, axis=0)
        row_deviation = float(np.max(np.abs(matrix.sum(axis=1) - row_targets)))
        column_deviation = float(np.max(np.abs(matrix.sum(axis=0) - column_targets)))
        if max(row_deviation, column_deviation) / row_total <= tolerance:
            break

    return IpfResult(
        matrix=matrix,
        iterations=iterations,
        converged=max(row_deviation, column_deviation) / row_total <= tolerance,
        max_row_deviation=row_deviation,
        max_col_deviation=column_deviation,
        column_scale=column_scale,
    )


def _scale_axis(matrix: np.ndarray, targets: np.ndarray, *, axis: int) -> np.ndarray:
    """Scale each line along ``axis`` so it sums to its target."""

    sums = matrix.sum(axis=axis)
    factors = np.divide(targets, sums, out=np.zeros_like(targets), where=sums > 0)
    return matrix * (factors[:, None] if axis == 1 else factors[None, :])


def _assert_feasible(
    seed: np.ndarray, row_targets: np.ndarray, column_targets: np.ndarray
) -> None:
    empty_rows = np.flatnonzero((seed.sum(axis=1) == 0) & (row_targets > 0))
    if empty_rows.size:
        raise InfeasibleMarginsError(
            f"{empty_rows.size} route(s) expect passengers but no carrier offers "
            f"supply; first offending index {int(empty_rows[0])}"
        )
    empty_columns = np.flatnonzero((seed.sum(axis=0) == 0) & (column_targets > 0))
    if empty_columns.size:
        raise InfeasibleMarginsError(
            f"{empty_columns.size} carrier(s) expect passengers but appear on no "
            f"route; first offending index {int(empty_columns[0])}"
        )


def estimate_route_carrier(
    seed: pd.DataFrame,
    route_totals: pd.DataFrame,
    carrier_totals: pd.DataFrame,
    *,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
    tolerance: float = DEFAULT_TOLERANCE,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split each period's route totals across carriers.

    ``seed`` carries :data:`SEED_COLUMNS`; ``route_totals`` carries
    ``period_id, route_key, passengers``; ``carrier_totals`` carries
    ``period_id, carrier_key, passengers``.  Returns the tidy estimate and a
    per-period diagnostics frame — never one without the other, because an
    estimate whose fit did not converge must not be read as a number.
    """

    _require_columns(seed, SEED_COLUMNS, "seed")
    _require_columns(route_totals, ("period_id", "route_key", "passengers"), "route_totals")
    _require_columns(carrier_totals, ("period_id", "carrier_key", "passengers"), "carrier_totals")

    estimates: list[pd.DataFrame] = []
    diagnostics: list[dict[str, object]] = []

    for period_id in sorted(set(route_totals["period_id"]) & set(carrier_totals["period_id"])):
        period_seed = seed[seed["period_id"] == period_id]
        if period_seed.empty:
            diagnostics.append(_diagnostic_row(period_id, reason="no_seed"))
            continue

        rows = route_totals[route_totals["period_id"] == period_id]
        columns = carrier_totals[carrier_totals["period_id"] == period_id]
        # Only routes and carriers present in the seed can receive passengers.
        rows = rows[rows["route_key"].isin(period_seed["route_key"])]
        columns = columns[columns["carrier_key"].isin(period_seed["carrier_key"])]
        if rows.empty or columns.empty:
            diagnostics.append(_diagnostic_row(period_id, reason="no_overlap"))
            continue

        route_index = pd.Index(sorted(rows["route_key"].unique()), name="route_key")
        carrier_index = pd.Index(sorted(columns["carrier_key"].unique()), name="carrier_key")
        matrix_seed = (
            period_seed.pivot_table(
                index="route_key", columns="carrier_key", values="weight", aggfunc="sum",
                fill_value=0.0,
            )
            .reindex(index=route_index, columns=carrier_index)
            .fillna(0.0)
        )
        row_targets = rows.groupby("route_key")["passengers"].sum().reindex(route_index).fillna(0.0)
        column_targets = (
            columns.groupby("carrier_key")["passengers"].sum().reindex(carrier_index).fillna(0.0)
        )

        result = fit_ipf(
            matrix_seed.to_numpy(),
            row_targets.to_numpy(),
            column_targets.to_numpy(),
            max_iterations=max_iterations,
            tolerance=tolerance,
        )
        # A route served by a single carrier needs no estimation: the published
        # route total *is* that carrier's figure.
        carriers_per_route = (matrix_seed > 0).sum(axis=1)

        tidy = (
            pd.DataFrame(result.matrix, index=route_index, columns=carrier_index)
            .stack()
            .rename("passengers_estimated")
            .reset_index()
        )
        tidy = tidy[tidy["passengers_estimated"] > 0].copy()
        tidy["period_id"] = period_id
        tidy["is_exact"] = tidy["route_key"].map(carriers_per_route).eq(1)
        tidy["estimator_version"] = ESTIMATOR_VERSION
        estimates.append(tidy)

        diagnostics.append(
            _diagnostic_row(
                period_id,
                routes=int(route_index.size),
                carriers=int(carrier_index.size),
                competitive_routes=int((carriers_per_route >= 2).sum()),
                iterations=result.iterations,
                converged=result.converged,
                max_row_deviation=result.max_row_deviation,
                max_col_deviation=result.max_col_deviation,
                column_scale=result.column_scale,
            )
        )

    columns = [
        "period_id", "route_key", "carrier_key", "passengers_estimated",
        "is_exact", "estimator_version",
    ]
    estimate_frame = (
        pd.concat(estimates, ignore_index=True)[columns]
        if estimates
        else pd.DataFrame(columns=columns)
    )
    return estimate_frame, pd.DataFrame(diagnostics)


def _diagnostic_row(period_id: str, **fields: object) -> dict[str, object]:
    row: dict[str, object] = {
        "period_id": period_id, "routes": 0, "carriers": 0, "competitive_routes": 0,
        "iterations": 0, "converged": False, "max_row_deviation": float("nan"),
        "max_col_deviation": float("nan"), "column_scale": float("nan"), "reason": "",
    }
    row.update(fields)
    return row


def _require_columns(frame: pd.DataFrame, columns: tuple[str, ...], name: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"{name} is missing required column(s): {', '.join(missing)}")


# --------------------------------------------------------------------------
# Domestic margins, ready for a seed
# --------------------------------------------------------------------------

# AFAC keys routes by city, not airport: "MEXICO", "SANTA LUCÍA", "DEL BAJIO".
# A seed adapter must emit route keys in this same vocabulary.
ROUTE_MARGIN_FILE = "afac_od_nacional_regular.csv"
CARRIER_MARGIN_FILE = "afac_carrier_domestic.csv"
CITY_CROSSWALK_FILE = "afac_city_iata_crosswalk.csv"
CARRIER_CROSSWALK_FILE = "afac_carrier_crosswalk.csv"

# A seed provider hands over flights keyed by airport; the margins are keyed by
# AFAC city.  These two columns are what a provider table must carry.
FLIGHT_COLUMNS = ("period_id", "origin_iata", "dest_iata", "carrier_key", "flights")


class UnmappedSeedError(ValueError):
    """A seed row names an airport or carrier absent from the crosswalks."""


def _reference_dir(reference_dir: Path | None) -> Path:
    return reference_dir or (PATHS.data / "reference")


def load_city_crosswalk(reference_dir: Path | None = None) -> dict[str, str]:
    """IATA code to AFAC city name, the vocabulary the margins are keyed by."""

    table = pd.read_csv(_reference_dir(reference_dir) / CITY_CROSSWALK_FILE)
    return dict(zip(table["airport_iata"], table["afac_city"], strict=True))


def load_carrier_crosswalk(reference_dir: Path | None = None) -> dict[str, str]:
    """AFAC carrier name to the project's carrier_key."""

    table = pd.read_csv(_reference_dir(reference_dir) / CARRIER_CROSSWALK_FILE)
    return dict(zip(table["afac_carrier_name"], table["carrier_key"], strict=True))


def build_seed_from_flights(
    flights: pd.DataFrame, *, reference_dir: Path | None = None
) -> pd.DataFrame:
    """Turn a provider's flight counts into a seed keyed like the AFAC margins.

    Flight counts are all a provider has to supply: the fit is invariant to
    scaling any row or column, so aircraft gauge and uneven coverage cancel.
    What cannot be recovered is which carrier flies a route and how often
    relative to its rivals — that is the whole reason a seed is needed.
    """

    _require_columns(flights, FLIGHT_COLUMNS, "flights")
    cities = load_city_crosswalk(reference_dir)

    unmapped = (
        set(flights["origin_iata"]) | set(flights["dest_iata"])
    ) - set(cities)
    if unmapped:
        raise UnmappedSeedError(
            "Airport(s) absent from the AFAC city crosswalk: "
            + ", ".join(sorted(unmapped))
        )

    seed = flights.copy()
    seed["route_key"] = (
        seed["origin_iata"].map(cities) + "-" + seed["dest_iata"].map(cities)
    )
    seed = seed.rename(columns={"flights": "weight"})
    seed = seed[seed["weight"] > 0]
    return (
        seed.groupby(["period_id", "route_key", "carrier_key"], as_index=False)["weight"]
        .sum()
        .loc[:, list(SEED_COLUMNS)]
    )


def load_afac_domestic_margins(
    reference_dir: Path | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load the two AFAC marginals for scheduled domestic service.

    Route totals come from the origin-destination workbook, carrier totals from
    the airline statistics.  The two are published separately and never
    crossed; that they agree to a few dozen passengers per quarter is the
    evidence that a joint table exists upstream.
    """

    reference = _reference_dir(reference_dir)

    routes = pd.read_csv(reference / ROUTE_MARGIN_FILE)
    routes["route_key"] = routes["origen"].str.strip() + "-" + routes["destino"].str.strip()
    route_totals = (
        routes.rename(columns={"pasajeros": "passengers"})
        .groupby(["period_id", "route_key"], as_index=False)["passengers"]
        .sum()
    )

    carriers = pd.read_csv(reference / CARRIER_MARGIN_FILE)
    crosswalk = load_carrier_crosswalk(reference_dir)
    unmapped = set(carriers["carrier_name"]) - set(crosswalk)
    if unmapped:
        raise UnmappedSeedError(
            "AFAC carrier name(s) absent from the crosswalk: " + ", ".join(sorted(unmapped))
        )
    carriers["carrier_key"] = carriers["carrier_name"].map(crosswalk)
    carrier_totals = (
        carriers.rename(columns={"pasajeros": "passengers"})
        .groupby(["period_id", "carrier_key"], as_index=False)["passengers"]
        .sum()
    )
    return route_totals, carrier_totals


# --------------------------------------------------------------------------
# Validation harness
# --------------------------------------------------------------------------

T100_SEED_METRICS = {"seats", "departures"}


def load_t100_panel(
    period_prefix: str = "2025", gold_dir: Path | None = None
) -> pd.DataFrame:
    """Read the transborder T-100 panel already materialised in gold."""

    gold = gold_dir or PATHS.gold
    query = """
        SELECT f.period_id,
               r.origin_iata || '-' || r.dest_iata AS route_key,
               f.carrier_key,
               SUM(f.passengers)            AS passengers,
               SUM(f.seats)                 AS seats,
               SUM(f.departures_performed)  AS departures
        FROM read_parquet(?) f
        JOIN read_parquet(?) r USING (route_key)
        WHERE f.period_id LIKE ?
          AND r.is_transborder_us
          AND f.seats > 0
          AND f.departures_performed > 0
        GROUP BY 1, 2, 3
        HAVING SUM(f.passengers) > 0
    """
    connection = duckdb.connect()
    try:
        return connection.execute(
            query,
            [
                str(gold / "fact_route_traffic.parquet"),
                str(gold / "dim_route.parquet"),
                f"{period_prefix}%",
            ],
        ).df()
    finally:
        connection.close()


def backtest_against_t100(
    *,
    period_prefix: str = "2025",
    seed_metric: str = "departures",
    min_carriers: int = 2,
    gold_dir: Path | None = None,
) -> pd.DataFrame:
    """Measure the estimator against a market where the true split is published.

    The carrier split is hidden, the two marginals AFAC would publish are
    derived from it, the split is rebuilt from the seed, and the rebuilt figures
    are compared against the truth.  Error is reported on competitive routes
    only: a single-carrier route is recovered exactly by construction and would
    flatter the average.
    """

    if seed_metric not in T100_SEED_METRICS:
        raise ValueError(f"seed_metric must be one of {sorted(T100_SEED_METRICS)}")

    panel = load_t100_panel(period_prefix=period_prefix, gold_dir=gold_dir)
    if panel.empty:
        raise ValueError(f"No T-100 rows found for period prefix {period_prefix!r}")

    seed = panel.rename(columns={seed_metric: "weight"})[list(SEED_COLUMNS)]
    route_totals = (
        panel.groupby(["period_id", "route_key"], as_index=False)["passengers"].sum()
    )
    carrier_totals = (
        panel.groupby(["period_id", "carrier_key"], as_index=False)["passengers"].sum()
    )

    estimate, diagnostics = estimate_route_carrier(seed, route_totals, carrier_totals)
    if not diagnostics.empty and not diagnostics["converged"].all():
        unconverged = diagnostics.loc[~diagnostics["converged"], "period_id"].tolist()
        raise RuntimeError(f"IPF did not converge for period(s): {unconverged}")

    merged = panel.merge(
        estimate, on=["period_id", "route_key", "carrier_key"], how="left"
    )
    merged["passengers_estimated"] = merged["passengers_estimated"].fillna(0.0)
    merged = merged.merge(
        route_totals.rename(columns={"passengers": "route_passengers"}),
        on=["period_id", "route_key"],
    )

    carriers_on_route = (
        panel.groupby(["period_id", "route_key"])["carrier_key"].nunique()
        .rename("carriers_on_route").reset_index()
    )
    merged = merged.merge(carriers_on_route, on=["period_id", "route_key"])
    competitive = merged[merged["carriers_on_route"] >= min_carriers].copy()
    if competitive.empty:
        raise ValueError("No competitive routes available for the backtest")

    competitive["true_share"] = competitive["passengers"] / competitive["route_passengers"]
    competitive["estimated_share"] = (
        competitive["passengers_estimated"] / competitive["route_passengers"]
    )
    competitive["share_error"] = (competitive["true_share"] - competitive["estimated_share"]).abs()
    competitive["passenger_error"] = (
        competitive["passengers"] - competitive["passengers_estimated"]
    ).abs()

    def _summarise(group: pd.DataFrame) -> pd.Series:
        weights = group["route_passengers"]
        return pd.Series(
            {
                "routes": int(group["route_key"].nunique()),
                "observations": int(len(group)),
                "share_mae_pp": float(
                    100 * np.average(group["share_error"], weights=weights)
                ),
                "passenger_error_pct": float(
                    100 * group["passenger_error"].sum() / group["passengers"].sum()
                ),
            }
        )

    summary = (
        competitive.groupby("period_id")[
            ["route_key", "share_error", "passenger_error", "passengers", "route_passengers"]
        ]
        .apply(_summarise, include_groups=False)
        .reset_index()
    )
    summary.insert(1, "seed_metric", seed_metric)
    return summary


def main() -> int:
    """Print the measured accuracy of the estimator for each seed quality."""

    for seed_metric in ("seats", "departures"):
        summary = backtest_against_t100(seed_metric=seed_metric)
        print(
            f"seed={seed_metric:10s} "
            f"share_mae={summary['share_mae_pp'].mean():5.2f} pp  "
            f"passenger_error={summary['passenger_error_pct'].mean():5.2f} %  "
            f"({int(summary['routes'].mean())} competitive routes/month)"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
