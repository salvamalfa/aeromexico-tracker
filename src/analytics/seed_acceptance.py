"""Judge a candidate seed source before paying for a subscription to it.

The fit tolerates far more than it looks like it should, and that was measured
rather than assumed.  Injecting a known bias into the T-100 harness, where the
true split is published, gives:

===================================================  ======  ======  ======
Bias injected into the seed                           1.30x   2.00x   2.80x
===================================================  ======  ======  ======
Per carrier, even across that carrier's whole network  1.96    1.96    1.96
Per route, even across that route's operators          1.96    1.96    1.96
Per carrier *within* each route                        2.31    3.77    5.11
===================================================  ======  ======  ======

(weighted share error, in percentage points, against a 1.96 pp baseline)

The first two rows are row and column scalings, and iterative proportional
fitting cancels them exactly -- a source could see one carrier three times
better than another across the board and the fitted split would not move.  Only
the interaction survives, and it is not identifiable from the margins, because
that is the same non-identifiability the estimator exists to work around.

So this module does not pretend to measure the interaction.  It judges what it
can, which is what actually breaks a fit in practice:

- **A carrier missing from the seed.**  Its published national total then has
  nowhere to go, and the fit either refuses or forces those passengers onto
  whatever routes remain.
- **A route missing from the seed.**  The carriers that fly it get a structural
  zero and their passengers are pushed elsewhere.
- **A partial network**, which `column_scale` exposes: a seed covering part of
  a carrier's routes demands more passengers from them than they carry.

The per-carrier coverage factor is still reported, because it says something
useful about a source, but it is *diagnostic, not disqualifying* -- reading it
as a verdict was a mistake this module used to make.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from src.analytics.route_carrier import (
    ROUTE_MARGIN_FILE,
    load_carrier_crosswalk,
    build_seed_from_flights,
    estimate_route_carrier,
    load_afac_domestic_margins,
)
from src.config import PATHS


ACCEPTANCE_VERSION = "seed_acceptance_v3"

# Flights per carrier, which AFAC publishes only in the airline summary
# workbook.  Where it covers the period being judged, the coverage factor is a
# division rather than an inference.
CARRIER_FLIGHTS_FILE = "afac_carrier_flights_domestic.csv"

# Reference points for reading the reported spread.  They do not decide the
# verdict: a spread of this shape is a column scaling and the fit cancels it.
# Kept because a wide spread still says something about a source's behaviour.
COVERAGE_SPREAD_PASS = 1.15
COVERAGE_SPREAD_FAIL = 1.50
# `column_scale` this far from 1 means the seed misses part of some carrier's
# network, which silently corrupts the split even when everything else looks fine.
COLUMN_SCALE_TOLERANCE = 0.05
# Share of published passengers whose route must appear in the seed. A result
# at or above 95% is usable as a partial estimate when its uncovered universe
# remains explicit; it is not promoted to observed data or called complete.
ROUTE_COVERAGE_PASS = 0.95
ROUTE_COVERAGE_REJECT = 0.95
# A missing carrier remains outside the estimate. Permit partial use only while
# its published AFAC passengers fit inside the same uncovered-universe budget.
MISSING_CARRIER_SHARE_TOLERANCE = 0.05
# A carrier flying fewer than this many flights a month cannot be judged from a
# sampled seed: a handful of observations swings its ratio wildly, and one such
# carrier would otherwise decide the verdict for the whole source.  Aerus flies
# 438 flights a month; one sampled Tuesday caught nine of them.
MIN_FLIGHTS_TO_JUDGE = 1_000
# Below this share of the month, the measured ratio mixes coverage with
# day-of-week mix: business-heavy carriers over-represent on a weekday and
# leisure-heavy ones under-represent, which is sampling, not a coverage gap.
MIN_SAMPLE_FOR_CLEAN_MEASURE = 0.5

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
    carriers_judged: tuple[str, ...]
    column_scale: float
    coverage_method: str
    verdict: str
    notes: tuple[str, ...]
    missing_carrier_passenger_share: float = 0.0

    @property
    def accepted(self) -> bool:
        return self.verdict == "accept"

    @property
    def usable(self) -> bool:
        """Whether the seed may be fitted, including a disclosed partial fit."""

        return self.verdict in {"accept", "review"}


def classify_seed(
    *,
    passenger_coverage: float,
    missing_carrier_passenger_share: float,
    column_scale: float,
    has_notes: bool,
) -> str:
    """Return accept, review, or reject under the approved 95% partial-use rule."""

    fatal = (
        passenger_coverage < ROUTE_COVERAGE_REJECT
        or missing_carrier_passenger_share
        > MISSING_CARRIER_SHARE_TOLERANCE + 1e-12
        or not np.isfinite(column_scale)
        or abs(column_scale - 1.0) > COLUMN_SCALE_TOLERANCE + 1e-12
    )
    if fatal:
        return "reject"
    if (
        passenger_coverage < 1.0
        or missing_carrier_passenger_share > 0
        or has_notes
    ):
        return "review"
    return "accept"


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


def load_afac_carrier_flights(reference_dir: Path | None = None) -> pd.DataFrame:
    """Flights per carrier and month, keyed by ``carrier_key``.

    Returns an empty frame when the file is absent: the acceptance test falls
    back to inferring coverage, which is weaker but needs no extra source.
    """

    reference = reference_dir or (PATHS.data / "reference")
    path = reference / CARRIER_FLIGHTS_FILE
    if not path.exists():
        return pd.DataFrame(columns=["period_id", "carrier_key", "flights"])

    table = pd.read_csv(path)
    crosswalk = load_carrier_crosswalk(reference_dir)
    table["carrier_key"] = table["carrier_name"].map(crosswalk)
    return (
        table.dropna(subset=["carrier_key"])
        .rename(columns={"vuelos": "flights"})
        .groupby(["period_id", "carrier_key"], as_index=False)["flights"]
        .sum()
    )


def measure_carrier_coverage(
    published_flights: pd.Series, candidate: pd.DataFrame
) -> pd.Series:
    """Coverage per carrier as a plain ratio, normalised to a mean of one.

    The candidate may cover only part of the month -- a sampled week, say -- so
    the absolute ratio carries no meaning and only the spread between carriers
    does.  Normalising by the flight-weighted mean removes the sampling factor,
    which is a row scaling the fit would cancel anyway.
    """

    seen = candidate.groupby("carrier_key")["weight"].sum()
    common = seen.index.intersection(published_flights.index[published_flights > 0])
    if common.empty:
        return pd.Series(dtype=float)
    ratio = seen.loc[common] / published_flights.loc[common]
    mean = float(np.average(ratio, weights=published_flights.loc[common]))
    if not np.isfinite(mean) or mean <= 0:
        return pd.Series(dtype=float)
    return (ratio / mean).rename("coverage_factor")


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
    carrier_passengers = float(carrier_totals["passengers"].sum())
    missing_carrier_passenger_share = (
        float(
            carrier_totals.loc[
                carrier_totals["carrier_key"].isin(missing), "passengers"
            ].sum()
            / carrier_passengers
        )
        if carrier_passengers > 0
        else 0.0
    )

    # Prefer the division over the inference: where AFAC publishes flights per
    # carrier for this month, coverage is measured, not modelled.
    published = load_afac_carrier_flights(reference_dir)
    published = published[published["period_id"] == period_id].set_index("carrier_key")["flights"]
    coverage = measure_carrier_coverage(published, seed) if not published.empty else pd.Series(dtype=float)
    coverage_method = "medida"
    if coverage.empty:
        coverage_method = "inferida"
        coverage = estimate_carrier_coverage(
            route_flights, seed,
            weights=flown.set_index("route_key")["passengers"],
        )
    # Judge the spread on carriers big enough to measure; report the rest.
    judged = coverage
    if coverage_method == "medida" and not published.empty:
        big = published[published >= MIN_FLIGHTS_TO_JUDGE].index
        if not coverage.index.intersection(big).empty:
            judged = coverage.loc[coverage.index.intersection(big)]
    spread = (
        float(judged.max() / judged.min())
        if not judged.empty and judged.min() > 0 else float("inf")
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
        notes.append(
            f"Aerolíneas ausentes de la semilla: {', '.join(missing)} "
            f"({missing_carrier_passenger_share:.1%} de pasajeros AFAC)"
        )
    if np.isfinite(column_scale) and abs(column_scale - 1.0) > COLUMN_SCALE_TOLERANCE:
        notes.append(
            f"column_scale = {column_scale:.3f}: la semilla no cubre la red completa "
            "de alguna aerolínea"
        )
    small = sorted(set(coverage.index) - set(judged.index))
    if small:
        notes.append(
            "Excluidas del veredicto por volumen insuficiente para medirlas: "
            + ", ".join(small)
        )
    if coverage_method == "medida" and flight_coverage < MIN_SAMPLE_FOR_CLEAN_MEASURE:
        notes.append(
            f"La semilla cubre {flight_coverage:.1%} del mes, así que la dispersión "
            "mezcla cobertura con día de la semana; un mes completo la separa"
        )
    if passenger_coverage < 0.95:
        notes.append(
            f"La semilla solo alcanza el {passenger_coverage:.1%} de los pasajeros"
        )

    # What disqualifies a seed is material incompleteness, not the coverage
    # spread: the spread is a column effect and the fit cancels it. A partial
    # result inside the 5% budget remains REVIEW and carries its exclusions.
    verdict = classify_seed(
        passenger_coverage=passenger_coverage,
        missing_carrier_passenger_share=missing_carrier_passenger_share,
        column_scale=column_scale,
        has_notes=bool(notes),
    )

    return AcceptanceReport(
        period_id=period_id,
        afac_routes=int(len(flown)),
        covered_routes=int(covered.sum()),
        passenger_coverage=passenger_coverage,
        flight_coverage=flight_coverage,
        missing_carriers=missing,
        carrier_coverage=coverage.round(4).to_dict(),
        coverage_spread=spread,
        carriers_judged=tuple(judged.index),
        column_scale=column_scale,
        coverage_method=coverage_method,
        verdict=verdict,
        notes=tuple(notes),
        missing_carrier_passenger_share=missing_carrier_passenger_share,
    )


def format_report(report: AcceptanceReport) -> str:
    """Render the report the way it should be read: the spread first."""

    lines = [
        f"Prueba de aceptación de semilla — {report.period_id}",
        f"  Veredicto: {report.verdict.upper()}",
        f"  Rutas cubiertas: {report.covered_routes} de {report.afac_routes} "
        f"({report.passenger_coverage:.1%} de los pasajeros; "
        f"utilizable ≥{ROUTE_COVERAGE_PASS:.0%}, reprueba <{ROUTE_COVERAGE_REJECT:.0%})",
        f"  column_scale: {report.column_scale:.3f} "
        f"(tolerancia ±{COLUMN_SCALE_TOLERANCE:.0%})",
        "",
        "  Diagnóstico, no veredicto — el ajuste cancela un sesgo de esta forma:",
        f"    dispersión entre aerolíneas: {report.coverage_spread:.2f}x "
        f"({report.coverage_method} sobre {len(report.carriers_judged)})",
        f"    vuelos vistos vs AFAC: {report.flight_coverage:.1%}",
        "    factor por aerolínea (1.00 = promedio del mercado):",
    ]
    for carrier, factor in sorted(
        report.carrier_coverage.items(), key=lambda kv: kv[1]
    ):
        lines.append(f"      {carrier:<24} {factor:.2f}")
    lines.extend(f"  ! {note}" for note in report.notes)
    return "\n".join(lines)
