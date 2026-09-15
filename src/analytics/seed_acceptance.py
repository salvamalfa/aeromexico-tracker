"""Judge a candidate seed source before paying for a subscription to it.

The OpenSky pilot burned 540 API credits and several hours to reach a verdict
that AFAC's own publications could have delivered in an afternoon.  The reason
is that the fit tolerates almost everything a cheap data source gets wrong, and
fails on exactly one thing:

- **Missing flights, evenly.**  Harmless.  A uniform deficit on a route is a row
  scaling, and iterative proportional fitting is invariant to row scaling.
- **Wrong units.**  Harmless.  Flights instead of seats is a column scaling.
- **Missing more flights of one carrier than of its rival, on the same route.**
  Fatal, and invisible in every summary statistic a provider advertises.

So the acceptance test has to measure that last quantity specifically.  It can,
without any ground truth, because AFAC publishes flights per route alongside
passengers per route.  If a source covered every carrier equally, the ratio of
its flight count to AFAC's would be the same constant on every route.  It is not
— and how it varies across routes with different carrier mixes is what identifies
a per-carrier coverage factor.

:func:`estimate_carrier_coverage` recovers those factors; the spread between the
largest and the smallest is the number that decides whether to buy.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.analytics.route_carrier import (
    ROUTE_MARGIN_FILE,
    build_seed_from_flights,
    estimate_route_carrier,
    load_afac_domestic_margins,
)
from src.config import PATHS


ACCEPTANCE_VERSION = "seed_acceptance_v1"

# A source whose carriers differ by less than this factor is usable: the residual
# it leaves is below the estimator's own measured error of ~2 pp.
COVERAGE_SPREAD_PASS = 1.15
# Above this the split is not worth publishing.  OpenSky sat at 2.8.
COVERAGE_SPREAD_FAIL = 1.50
# `column_scale` this far from 1 means the seed misses part of some carrier's
# network, which silently corrupts the split even when everything else looks fine.
COLUMN_SCALE_TOLERANCE = 0.05

_DEBIAS_SWEEPS = 50
_DEBIAS_TOLERANCE = 1e-10


@dataclass(frozen=True, slots=True)
class AcceptanceReport:
    """Everything needed to accept or reject a seed source, and why."""

    period_id: str
    afac_routes: int
    covered_routes: int
    passenger_coverage: float
    flight_coverage: float
    missing_carriers: tuple[str, ...]
    carrier_coverage: dict[str, float]
    coverage_spread: float
    column_scale: float
    verdict: str
    notes: tuple[str, ...]

    @property
    def accepted(self) -> bool:
        return self.verdict == "accept"


def load_afac_route_flights(reference_dir: Path | None = None) -> pd.DataFrame:
    """Flights per route and month, the free contrast the whole test rests on."""

    reference = reference_dir or (PATHS.data / "reference")
    routes = pd.read_csv(reference / ROUTE_MARGIN_FILE)
    routes["route_key"] = (
        routes["origen"].str.strip() + "-" + routes["destino"].str.strip()
    )
    return (
        routes.rename(columns={"vuelos": "flights"})
        .groupby(["period_id", "route_key"], as_index=False)["flights"]
        .sum()
    )


def estimate_carrier_coverage(
    route_flights: pd.DataFrame,
    candidate: pd.DataFrame,
    *,
    weights: pd.Series | None = None,
) -> pd.Series:
    """Recover each carrier's coverage factor relative to the market average.

    The candidate reports ``c[i,k] = f[k] * t[i,k]`` where ``t`` is the true
    flight count and ``f[k]`` the fraction of carrier *k*'s flights the source
    sees.  Only the route sums of ``t`` are known, from AFAC.  Writing the
    observed ratio on route *i* as

        r[i] = sum_k c[i,k] / sum_k t[i,k] = sum_k f[k] * s[i,k]

    with ``s`` the *true* share of carrier *k* on route *i*, gives a linear
    system in ``f`` — except that ``s`` is unknown too.  It is recovered by
    alternating: hold the shares, solve for ``f`` by weighted least squares;
    hold ``f``, divide it out of the observed shares to de-bias them.  Routes
    with different carrier mixes are what make the system identifiable, and a
    real network has plenty of those.

    The result is normalised to a passenger-weighted mean of 1, because only
    ratios between carriers are identifiable — a factor common to every carrier
    is a global scaling the fit cancels anyway.
    """

    observed = candidate.pivot_table(
        index="route_key", columns="carrier_key", values="weight",
        aggfunc="sum", fill_value=0.0,
    )
    truth = route_flights.set_index("route_key")["flights"]
    common = observed.index.intersection(truth.index[truth > 0])
    observed = observed.loc[common]
    truth = truth.loc[common]
    if observed.empty or observed.shape[1] == 0:
        return pd.Series(dtype=float)

    carriers = list(observed.columns)
    obs = observed.to_numpy(dtype=float)
    totals = truth.to_numpy(dtype=float)
    ratio = obs.sum(axis=1) / totals

    if weights is None:
        w = totals.copy()
    else:
        w = weights.reindex(common).fillna(0.0).to_numpy(dtype=float)
    w = np.where(np.isfinite(w) & (w > 0), w, 0.0)
    if not w.any():
        w = np.ones_like(totals)

    factors = np.ones(len(carriers))
    for _ in range(_DEBIAS_SWEEPS):
        # De-bias the observed mix into an estimate of the true share matrix.
        unbiased = obs / factors
        row_sums = unbiased.sum(axis=1)
        shares = np.divide(
            unbiased, row_sums[:, None],
            out=np.zeros_like(unbiased), where=row_sums[:, None] > 0,
        )
        # Weighted least squares for the coverage factors, clipped at zero: a
        # negative coverage is not a thing the data can mean.
        sw = shares * np.sqrt(w)[:, None]
        solution, *_ = np.linalg.lstsq(sw, ratio * np.sqrt(w), rcond=None)
        solution = np.clip(solution, 1e-9, None)
        if np.max(np.abs(solution - factors)) <= _DEBIAS_TOLERANCE:
            factors = solution
            break
        factors = solution

    # Normalise: only the ratios between carriers carry meaning.
    exposure = (obs / factors).sum(axis=0)
    mean = float(np.average(factors, weights=exposure)) if exposure.sum() > 0 else 1.0
    return pd.Series(factors / mean, index=carriers, name="coverage_factor")


def assess_seed(
    flights: pd.DataFrame,
    period_id: str,
    *,
    reference_dir: Path | None = None,
) -> AcceptanceReport:
    """Score one month of a candidate source against what AFAC already publishes."""

    seed = build_seed_from_flights(flights, reference_dir=reference_dir)
    seed = seed[seed["period_id"] == period_id]
    if seed.empty:
        raise ValueError(f"The candidate carries no flights for {period_id}")

    route_totals, carrier_totals = load_afac_domestic_margins(reference_dir)
    route_totals = route_totals[route_totals["period_id"] == period_id]
    carrier_totals = carrier_totals[carrier_totals["period_id"] == period_id]
    route_flights = load_afac_route_flights(reference_dir)
    route_flights = route_flights[route_flights["period_id"] == period_id]

    flown = route_totals[route_totals["passengers"] > 0]
    covered = flown["route_key"].isin(set(seed["route_key"]))
    passenger_coverage = (
        float(flown.loc[covered, "passengers"].sum() / flown["passengers"].sum())
        if flown["passengers"].sum() > 0 else 0.0
    )

    afac_flights = float(route_flights["flights"].sum())
    flight_coverage = float(seed["weight"].sum() / afac_flights) if afac_flights else 0.0

    missing = tuple(sorted(
        set(carrier_totals.loc[carrier_totals["passengers"] > 0, "carrier_key"])
        - set(seed["carrier_key"])
    ))

    coverage = estimate_carrier_coverage(
        route_flights, seed,
        weights=flown.set_index("route_key")["passengers"],
    )
    spread = (
        float(coverage.max() / coverage.min())
        if not coverage.empty and coverage.min() > 0 else float("inf")
    )

    # The fit itself reports whether each carrier's whole network made it in.
    column_scale = float("nan")
    notes: list[str] = []
    try:
        _, diagnostics = estimate_route_carrier(seed, route_totals, carrier_totals)
        if not diagnostics.empty:
            column_scale = float(diagnostics["column_scale"].iloc[0])
    except Exception as exc:  # noqa: BLE001 - a refused fit is itself a verdict
        notes.append(f"El ajuste no corre con esta semilla: {type(exc).__name__}: {exc}")

    if missing:
        notes.append(f"Aerolíneas ausentes de la semilla: {', '.join(missing)}")
    if np.isfinite(column_scale) and abs(column_scale - 1.0) > COLUMN_SCALE_TOLERANCE:
        notes.append(
            f"column_scale = {column_scale:.3f}: la semilla no cubre la red completa "
            "de alguna aerolínea"
        )
    if passenger_coverage < 0.95:
        notes.append(
            f"La semilla solo alcanza el {passenger_coverage:.1%} de los pasajeros"
        )

    if missing or not np.isfinite(spread) or spread >= COVERAGE_SPREAD_FAIL:
        verdict = "reject"
    elif spread > COVERAGE_SPREAD_PASS or notes:
        verdict = "review"
    else:
        verdict = "accept"

    return AcceptanceReport(
        period_id=period_id,
        afac_routes=int(len(flown)),
        covered_routes=int(covered.sum()),
        passenger_coverage=passenger_coverage,
        flight_coverage=flight_coverage,
        missing_carriers=missing,
        carrier_coverage=coverage.round(4).to_dict(),
        coverage_spread=spread,
        column_scale=column_scale,
        verdict=verdict,
        notes=tuple(notes),
    )


def format_report(report: AcceptanceReport) -> str:
    """Render the report the way it should be read: the spread first."""

    lines = [
        f"Prueba de aceptación de semilla — {report.period_id}",
        f"  Veredicto: {report.verdict.upper()}",
        f"  Dispersión de cobertura entre aerolíneas: {report.coverage_spread:.2f}x "
        f"(pasa <{COVERAGE_SPREAD_PASS}, reprueba >={COVERAGE_SPREAD_FAIL})",
        f"  Rutas cubiertas: {report.covered_routes} de {report.afac_routes} "
        f"({report.passenger_coverage:.1%} de los pasajeros)",
        f"  Vuelos vistos vs AFAC: {report.flight_coverage:.1%}  "
        f"(un déficit parejo no importa)",
        f"  column_scale: {report.column_scale:.3f}",
        "  Factor de cobertura por aerolínea (1.00 = promedio del mercado):",
    ]
    for carrier, factor in sorted(
        report.carrier_coverage.items(), key=lambda kv: kv[1]
    ):
        lines.append(f"    {carrier:<24} {factor:.2f}")
    lines.extend(f"  ! {note}" for note in report.notes)
    return "\n".join(lines)
