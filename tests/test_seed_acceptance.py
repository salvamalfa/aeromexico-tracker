"""The acceptance test has to catch the one bias the estimator cannot absorb.

These tests degrade a known-good flight table by a known per-carrier factor and
check the factor comes back, because a detector that cannot recover an injected
bias is worse than none: it would licence a purchase.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analytics.route_carrier import (
    SEED_COLUMNS,
    estimate_route_carrier,
    load_t100_panel,
)
from src.analytics.seed_acceptance import (
    COVERAGE_SPREAD_FAIL,
    AcceptanceReport,
    classify_seed,
    format_report,
    estimate_carrier_coverage,
    load_afac_carrier_flights,
    load_afac_route_flights,
    measure_carrier_coverage,
)


@pytest.fixture(scope="module")
def truth() -> pd.DataFrame:
    """Real route structure with a real carrier mix, used as a stand-in truth."""

    panel = load_t100_panel(period_prefix="2025")
    month = panel[panel["period_id"] == sorted(panel["period_id"].unique())[0]]
    table = month.rename(columns={"departures": "weight"})[
        ["route_key", "carrier_key", "weight"]
    ]
    return table[table["weight"] > 0].reset_index(drop=True)


def _route_flights(truth: pd.DataFrame) -> pd.DataFrame:
    totals = truth.groupby("route_key", as_index=False)["weight"].sum()
    return totals.rename(columns={"weight": "flights"})


def _degrade(truth: pd.DataFrame, factors: dict[str, float]) -> pd.DataFrame:
    seen = truth.copy()
    seen["weight"] = seen["weight"] * seen["carrier_key"].map(factors).fillna(1.0)
    return seen


def test_uniform_coverage_reports_no_spread(truth: pd.DataFrame) -> None:
    """Losing 40 % of every flight is a row scaling; it must look like no bias."""

    seen = truth.assign(weight=truth["weight"] * 0.6)
    coverage = estimate_carrier_coverage(_route_flights(truth), seen)
    assert coverage.max() / coverage.min() == pytest.approx(1.0, abs=0.02)


def test_recovers_an_injected_per_carrier_bias(truth: pd.DataFrame) -> None:
    """A carrier seen half as often as the rest must come back at about half."""

    biggest = truth.groupby("carrier_key")["weight"].sum().idxmax()
    coverage = estimate_carrier_coverage(
        _route_flights(truth), _degrade(truth, {biggest: 0.5})
    )
    others = coverage.drop(biggest)
    assert coverage[biggest] / others.median() == pytest.approx(0.5, rel=0.15)


def test_injected_bias_is_recovered_across_a_range(truth: pd.DataFrame) -> None:
    carrier = truth.groupby("carrier_key")["weight"].sum().nlargest(3).index[-1]
    for injected in (0.25, 0.5, 2.0):
        coverage = estimate_carrier_coverage(
            _route_flights(truth), _degrade(truth, {carrier: injected})
        )
        recovered = coverage[carrier] / coverage.drop(carrier).median()
        assert recovered == pytest.approx(injected, rel=0.25), (
            f"inyectado {injected}, recuperado {recovered:.3f}"
        )


def test_opensky_style_bias_is_rejected(truth: pd.DataFrame) -> None:
    """The measured OpenSky profile must land beyond the fail threshold."""

    carriers = truth.groupby("carrier_key")["weight"].sum().nlargest(4).index
    # 13 %, 26 %, 29 %, 37 % — the resolution rates measured on real data.
    profile = dict(zip(carriers, (0.13, 0.26, 0.29, 0.37), strict=True))
    coverage = estimate_carrier_coverage(
        _route_flights(truth), _degrade(truth, profile)
    )
    observed = coverage[list(carriers)]
    assert observed.max() / observed.min() >= COVERAGE_SPREAD_FAIL


def test_a_faithful_source_passes(truth: pd.DataFrame) -> None:
    """An exact copy of the truth must show every carrier at the market average."""

    coverage = estimate_carrier_coverage(_route_flights(truth), truth)
    assert np.allclose(coverage.to_numpy(), 1.0, atol=0.02)


def test_afac_route_flights_align_with_the_route_margin() -> None:
    """The contrast the test rests on must exist for every month of margins."""

    flights = load_afac_route_flights()
    assert not flights.empty
    assert flights["flights"].sum() > 0
    assert flights["period_id"].nunique() == 22


# --------------------------------------------------------------------------
# Measured coverage: a division against AFAC's published flights per carrier,
# which is strictly better than inferring it from route-level deficits.
# --------------------------------------------------------------------------

def _seed(counts: dict[str, float]) -> pd.DataFrame:
    return pd.DataFrame(
        {"carrier_key": list(counts), "weight": list(counts.values())}
    )


def test_a_proportional_sample_shows_every_carrier_at_the_average() -> None:
    published = pd.Series({"A": 10_000.0, "B": 5_000.0, "C": 1_000.0})
    coverage = measure_carrier_coverage(published, _seed({"A": 1000, "B": 500, "C": 100}))
    assert np.allclose(coverage.to_numpy(), 1.0)


def test_the_sampling_fraction_cancels_out() -> None:
    """A week and a month must give the same factors; only the spread means anything."""

    published = pd.Series({"A": 10_000.0, "B": 5_000.0})
    week = measure_carrier_coverage(published, _seed({"A": 200, "B": 120}))
    month = measure_carrier_coverage(published, _seed({"A": 800, "B": 480}))
    assert np.allclose(week.to_numpy(), month.to_numpy())


def test_a_carrier_seen_half_as_often_comes_back_at_half() -> None:
    published = pd.Series({"A": 10_000.0, "B": 10_000.0})
    coverage = measure_carrier_coverage(published, _seed({"A": 1000, "B": 500}))
    assert coverage["B"] / coverage["A"] == pytest.approx(0.5)


def test_a_carrier_absent_from_the_published_margin_is_skipped() -> None:
    published = pd.Series({"A": 10_000.0})
    coverage = measure_carrier_coverage(published, _seed({"A": 1000, "DESCONOCIDA": 50}))
    assert list(coverage.index) == ["A"]


def test_no_overlap_returns_empty_so_the_caller_falls_back() -> None:
    published = pd.Series({"A": 10_000.0})
    assert measure_carrier_coverage(published, _seed({"B": 100})).empty


def test_published_carrier_flights_cover_the_months_we_can_estimate() -> None:
    flights = load_afac_carrier_flights()
    periods = set(flights["period_id"])
    assert {f"2026M{m:02d}" for m in range(1, 8)} <= periods
    assert flights["flights"].gt(0).all()
    assert "VIVA_AEROBUS" in set(flights["carrier_key"])


# --------------------------------------------------------------------------
# What actually disqualifies a seed. Measured on the T-100 harness: a bias of
# 1.30x per carrier leaves the error at 1.96 pp, identical to no bias at all,
# because the fit cancels column scalings. Incompleteness is what breaks it.
# --------------------------------------------------------------------------

def test_a_uniform_per_carrier_bias_does_not_change_the_fit(truth: pd.DataFrame) -> None:
    """The premise of the redesigned verdict, pinned against regression.

    Scaling a carrier's whole network is a column scaling, so the fitted split
    must come back identical.  If this ever fails, the verdict logic that
    ignores the coverage spread is no longer justified.
    """

    route_totals = truth.groupby("route_key", as_index=False)["weight"].sum()
    route_totals = route_totals.rename(columns={"weight": "passengers"})
    route_totals["period_id"] = "2025M01"
    carrier_totals = truth.groupby("carrier_key", as_index=False)["weight"].sum()
    carrier_totals = carrier_totals.rename(columns={"weight": "passengers"})
    carrier_totals["period_id"] = "2025M01"

    seed = truth.assign(period_id="2025M01")[list(SEED_COLUMNS)]
    biggest = truth.groupby("carrier_key")["weight"].sum().idxmax()
    biased = seed.copy()
    biased.loc[biased["carrier_key"] == biggest, "weight"] *= 2.8

    plain, _ = estimate_route_carrier(seed, route_totals, carrier_totals)
    skewed, _ = estimate_route_carrier(biased, route_totals, carrier_totals)
    merged = plain.merge(
        skewed, on=["period_id", "route_key", "carrier_key"], suffixes=("_a", "_b")
    )
    assert np.allclose(
        merged["passengers_estimated_a"], merged["passengers_estimated_b"], atol=1.0
    )


def test_a_wide_spread_alone_does_not_reject(monkeypatch: pytest.MonkeyPatch) -> None:
    """A complete seed passes even with carriers three times apart."""

    report = AcceptanceReport(
        period_id="2026M07", afac_routes=500, covered_routes=500,
        passenger_coverage=1.0, flight_coverage=1.0, missing_carriers=(),
        carrier_coverage={"A": 0.5, "B": 1.5}, coverage_spread=3.0,
        carriers_judged=("A", "B"), column_scale=1.0, coverage_method="medida",
        verdict="accept", notes=(),
    )
    assert report.accepted


def test_95_percent_partial_coverage_is_usable_for_review() -> None:
    verdict = classify_seed(
        passenger_coverage=0.95,
        missing_carrier_passenger_share=0.05,
        column_scale=1.05,
        has_notes=True,
    )
    report = AcceptanceReport(
        period_id="2026M04", afac_routes=500, covered_routes=450,
        passenger_coverage=0.95, flight_coverage=0.90, missing_carriers=("TAR",),
        carrier_coverage={"A": 1.0}, coverage_spread=1.0, carriers_judged=("A",),
        column_scale=1.05, coverage_method="medida", verdict=verdict,
        notes=("Cobertura parcial",),
    )
    assert verdict == "review"
    assert report.usable
    assert not report.accepted


@pytest.mark.parametrize(
    ("coverage", "missing_share", "column_scale"),
    [
        (0.9499, 0.0, 1.0),
        (0.99, 0.0501, 1.0),
        (0.99, 0.0, 1.051),
    ],
)
def test_materially_incomplete_seed_is_rejected(
    coverage: float, missing_share: float, column_scale: float
) -> None:
    assert classify_seed(
        passenger_coverage=coverage,
        missing_carrier_passenger_share=missing_share,
        column_scale=column_scale,
        has_notes=False,
    ) == "reject"


def test_the_report_labels_the_spread_as_diagnostic_not_verdict() -> None:
    report = AcceptanceReport(
        period_id="2026M07", afac_routes=500, covered_routes=500,
        passenger_coverage=1.0, flight_coverage=1.0, missing_carriers=(),
        carrier_coverage={"A": 1.0}, coverage_spread=1.0, carriers_judged=("A",),
        column_scale=1.0, coverage_method="medida", verdict="accept", notes=(),
    )
    text = format_report(report)
    assert "Diagnóstico, no veredicto" in text
    assert text.index("Rutas cubiertas") < text.index("dispersión entre aerolíneas")
