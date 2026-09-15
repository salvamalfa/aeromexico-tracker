"""The acceptance test has to catch the one bias the estimator cannot absorb.

These tests degrade a known-good flight table by a known per-carrier factor and
check the factor comes back, because a detector that cannot recover an injected
bias is worse than none: it would licence a purchase.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analytics.route_carrier import load_t100_panel
from src.analytics.seed_acceptance import (
    COVERAGE_SPREAD_FAIL,
    estimate_carrier_coverage,
    load_afac_route_flights,
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
