from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analytics.route_carrier import (
    InfeasibleMarginsError,
    UnmappedSeedError,
    backtest_against_t100,
    build_seed_from_flights,
    estimate_route_carrier,
    fit_ipf,
    load_afac_domestic_margins,
    load_carrier_crosswalk,
    load_city_crosswalk,
    load_t100_panel,
)


TRUTH = np.array(
    [
        [900.0, 300.0, 0.0],
        [200.0, 500.0, 150.0],
        [0.0, 0.0, 400.0],
    ]
)


def _margins(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return matrix.sum(axis=1), matrix.sum(axis=0)


def test_fit_recovers_the_matrix_when_the_seed_already_is_the_answer() -> None:
    rows, columns = _margins(TRUTH)

    result = fit_ipf(TRUTH, rows, columns)

    assert result.converged
    assert np.allclose(result.matrix, TRUTH)


def test_fit_reproduces_both_published_margins() -> None:
    seed = np.array([[5.0, 4.0, 0.0], [3.0, 3.0, 1.0], [0.0, 0.0, 2.0]])
    rows, columns = _margins(TRUTH)

    result = fit_ipf(seed, rows, columns)

    assert result.converged
    assert np.allclose(result.matrix.sum(axis=1), rows)
    assert np.allclose(result.matrix.sum(axis=0), columns)


def test_fit_ignores_per_carrier_gauge_because_a_column_scaling_cancels() -> None:
    """This is why flight counts work as well as seats: gauge is column scaling."""

    seed = np.array([[5.0, 4.0, 0.0], [3.0, 3.0, 1.0], [0.0, 0.0, 2.0]])
    rows, columns = _margins(TRUTH)
    rescaled = seed * np.array([180.0, 220.0, 99.0])[None, :]

    baseline = fit_ipf(seed, rows, columns)
    scaled = fit_ipf(rescaled, rows, columns)

    assert np.allclose(baseline.matrix, scaled.matrix)


def test_fit_ignores_per_route_coverage_because_a_row_scaling_cancels() -> None:
    """This is why an ADS-B feed may miss flights, as long as it misses evenly."""

    seed = np.array([[5.0, 4.0, 0.0], [3.0, 3.0, 1.0], [0.0, 0.0, 2.0]])
    rows, columns = _margins(TRUTH)
    thinned = seed * np.array([0.7, 1.0, 0.35])[:, None]

    baseline = fit_ipf(seed, rows, columns)
    partial = fit_ipf(thinned, rows, columns)

    assert np.allclose(baseline.matrix, partial.matrix)


def test_fit_never_invents_service_a_carrier_does_not_offer() -> None:
    seed = np.array([[5.0, 4.0, 0.0], [3.0, 3.0, 1.0], [0.0, 0.0, 2.0]])
    rows, columns = _margins(TRUTH)

    result = fit_ipf(seed, rows, columns)

    assert result.matrix[0, 2] == 0.0
    assert result.matrix[2, 0] == 0.0
    assert result.matrix[2, 1] == 0.0


def test_single_carrier_route_is_recovered_exactly() -> None:
    seed = np.array([[5.0, 4.0, 0.0], [3.0, 3.0, 1.0], [0.0, 0.0, 2.0]])
    rows, columns = _margins(TRUTH)

    result = fit_ipf(seed, rows, columns)

    assert result.matrix[2, 2] == pytest.approx(TRUTH[2, 2])


def test_margins_that_disagree_are_reconciled_onto_the_route_total() -> None:
    """AFAC's two publications differ by a few dozen passengers per quarter."""

    seed = np.ones((2, 2))
    rows = np.array([100.0, 100.0])
    columns = np.array([90.0, 90.0])

    result = fit_ipf(seed, rows, columns)

    assert result.column_scale == pytest.approx(200.0 / 180.0)
    assert result.matrix.sum() == pytest.approx(200.0)
    assert np.allclose(result.matrix.sum(axis=1), rows)


def test_a_route_with_no_supply_at_all_is_reported_not_silently_split() -> None:
    seed = np.array([[1.0, 1.0], [0.0, 0.0]])
    rows = np.array([50.0, 50.0])
    columns = np.array([50.0, 50.0])

    with pytest.raises(InfeasibleMarginsError, match="route"):
        fit_ipf(seed, rows, columns)


def test_a_carrier_that_appears_on_no_route_is_reported() -> None:
    seed = np.array([[1.0, 0.0], [1.0, 0.0]])
    rows = np.array([50.0, 50.0])
    columns = np.array([50.0, 50.0])

    with pytest.raises(InfeasibleMarginsError, match="carrier"):
        fit_ipf(seed, rows, columns)


def test_zero_targets_leave_empty_lines() -> None:
    seed = np.array([[1.0, 1.0], [1.0, 1.0]])
    rows = np.array([100.0, 0.0])
    columns = np.array([60.0, 40.0])

    result = fit_ipf(seed, rows, columns)

    assert result.converged
    assert np.allclose(result.matrix[1], 0.0)


@pytest.mark.parametrize(
    ("seed", "rows", "columns"),
    [
        (np.ones((2, 2)), np.array([1.0]), np.array([1.0, 1.0])),
        (np.ones(4), np.array([1.0, 1.0]), np.array([1.0, 1.0])),
        (np.array([[-1.0, 1.0], [1.0, 1.0]]), np.array([1.0, 1.0]), np.array([1.0, 1.0])),
    ],
)
def test_malformed_inputs_raise_before_fitting(
    seed: np.ndarray, rows: np.ndarray, columns: np.ndarray
) -> None:
    with pytest.raises(ValueError):
        fit_ipf(seed, rows, columns)


def _tidy_fixture() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    seed = pd.DataFrame(
        [
            ("2025M01", "MEX-CUN", "AEROMEXICO", 5.0),
            ("2025M01", "MEX-CUN", "VOLARIS", 4.0),
            ("2025M01", "MEX-MTY", "AEROMEXICO", 3.0),
            ("2025M01", "TIJ-UPN", "VOLARIS", 2.0),
        ],
        columns=["period_id", "route_key", "carrier_key", "weight"],
    )
    route_totals = pd.DataFrame(
        [
            ("2025M01", "MEX-CUN", 1000.0),
            ("2025M01", "MEX-MTY", 400.0),
            ("2025M01", "TIJ-UPN", 300.0),
        ],
        columns=["period_id", "route_key", "passengers"],
    )
    carrier_totals = pd.DataFrame(
        [
            ("2025M01", "AEROMEXICO", 1000.0),
            ("2025M01", "VOLARIS", 700.0),
        ],
        columns=["period_id", "carrier_key", "passengers"],
    )
    return seed, route_totals, carrier_totals


def test_estimate_returns_tidy_rows_that_honour_the_route_totals() -> None:
    seed, route_totals, carrier_totals = _tidy_fixture()

    estimate, diagnostics = estimate_route_carrier(seed, route_totals, carrier_totals)

    per_route = estimate.groupby("route_key")["passengers_estimated"].sum()
    assert per_route["MEX-CUN"] == pytest.approx(1000.0)
    assert per_route["MEX-MTY"] == pytest.approx(400.0)
    assert per_route["TIJ-UPN"] == pytest.approx(300.0)
    assert diagnostics.loc[0, "converged"]
    assert diagnostics.loc[0, "competitive_routes"] == 1


def test_estimate_flags_single_carrier_routes_as_exact() -> None:
    seed, route_totals, carrier_totals = _tidy_fixture()

    estimate, _ = estimate_route_carrier(seed, route_totals, carrier_totals)

    exact = estimate.set_index("route_key")["is_exact"]
    assert bool(exact["TIJ-UPN"]) is True
    assert bool(exact["MEX-MTY"]) is True
    assert not exact["MEX-CUN"].any()


def test_estimate_never_reports_a_carrier_outside_its_own_network() -> None:
    seed, route_totals, carrier_totals = _tidy_fixture()

    estimate, _ = estimate_route_carrier(seed, route_totals, carrier_totals)

    pairs = set(zip(estimate["route_key"], estimate["carrier_key"], strict=True))
    assert ("TIJ-UPN", "AEROMEXICO") not in pairs
    assert ("MEX-MTY", "VOLARIS") not in pairs


def test_estimate_requires_the_documented_seed_columns() -> None:
    _, route_totals, carrier_totals = _tidy_fixture()
    seed = pd.DataFrame({"period_id": ["2025M01"], "route_key": ["MEX-CUN"]})

    with pytest.raises(ValueError, match="carrier_key"):
        estimate_route_carrier(seed, route_totals, carrier_totals)


# --------------------------------------------------------------------------
# Measured accuracy against a market where the true split is published
# --------------------------------------------------------------------------

def test_transborder_panel_is_available_for_validation() -> None:
    panel = load_t100_panel(period_prefix="2025")

    assert not panel.empty
    assert panel["period_id"].nunique() == 12
    assert {"passengers", "seats", "departures"} <= set(panel.columns)


@pytest.mark.parametrize(
    ("seed_metric", "share_ceiling", "passenger_ceiling"),
    [("seats", 2.0, 6.0), ("departures", 2.5, 7.5)],
)
def test_estimator_stays_within_its_measured_accuracy_envelope(
    seed_metric: str, share_ceiling: float, passenger_ceiling: float
) -> None:
    """Guards the headline accuracy claim against silent regressions.

    Ceilings sit above the September 2026 measurement (seats 1.40 pp / 4.21 %,
    departures 1.98 pp / 5.96 %) with room for T-100 restatements, and well
    below the naive seat-share split the estimator has to beat.
    """

    summary = backtest_against_t100(seed_metric=seed_metric)

    assert len(summary) == 12
    assert summary["share_mae_pp"].mean() < share_ceiling
    assert summary["passenger_error_pct"].mean() < passenger_ceiling


def test_fitting_both_margins_beats_splitting_by_supply_alone() -> None:
    """The airline marginal is what absorbs the load-factor gap between carriers."""

    panel = load_t100_panel(period_prefix="2025")
    panel = panel[panel["period_id"] == "2025M01"]
    seats = panel.pivot_table(
        index="route_key", columns="carrier_key", values="seats", aggfunc="sum", fill_value=0.0
    )
    truth = (
        panel.pivot_table(
            index="route_key", columns="carrier_key", values="passengers", aggfunc="sum",
            fill_value=0.0,
        )
        .reindex(index=seats.index, columns=seats.columns)
        .fillna(0.0)
    )
    truth_values = truth.to_numpy()
    seat_values = seats.to_numpy()
    rows, columns = _margins(truth_values)

    supply_only = seat_values * np.divide(
        rows, seat_values.sum(axis=1), out=np.zeros_like(rows), where=seat_values.sum(axis=1) > 0
    )[:, None]
    fitted = fit_ipf(seat_values, rows, columns).matrix

    competitive = (seat_values > 0).sum(axis=1) >= 2
    naive_error = np.abs(truth_values - supply_only)[competitive].sum()
    fitted_error = np.abs(truth_values - fitted)[competitive].sum()

    assert fitted_error < naive_error


# --------------------------------------------------------------------------
# The domestic margins the estimator will be pointed at
# --------------------------------------------------------------------------

def test_both_afac_margins_describe_the_same_quarter() -> None:
    route_totals, carrier_totals = load_afac_domestic_margins()

    assert sorted(route_totals["period_id"].unique()) == ["2025M01", "2025M02", "2025M03"]
    assert sorted(carrier_totals["period_id"].unique()) == ["2025M01", "2025M02", "2025M03"]


def test_the_two_published_margins_agree_and_so_a_joint_table_exists_upstream() -> None:
    """The premise of the whole estimator: both files are views of one cube."""

    route_totals, carrier_totals = load_afac_domestic_margins()

    route_sum = route_totals["passengers"].sum()
    carrier_sum = carrier_totals["passengers"].sum()

    assert route_sum == 14_799_004
    assert carrier_sum == 14_799_050
    assert abs(route_sum - carrier_sum) <= 50
    assert abs(route_sum - carrier_sum) / carrier_sum < 1e-5


def test_domestic_margins_are_ready_to_receive_a_seed() -> None:
    """Everything but the seed is in place; this pins the contract it must meet."""

    route_totals, carrier_totals = load_afac_domestic_margins()

    assert "MEXICO-CANCUN" in set(route_totals["route_key"])
    assert "TIJUANA-URUAPAN" in set(route_totals["route_key"])
    assert "VOLARIS" in set(carrier_totals["carrier_key"])
    assert (route_totals["passengers"] >= 0).all()
    assert (carrier_totals["passengers"] > 0).all()


# --------------------------------------------------------------------------
# Turning a provider's flight counts into a seed the margins can be fitted to
# --------------------------------------------------------------------------

def _flights_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("2025M01", "MEX", "CUN", "AEROMEXICO", 560),
            ("2025M01", "MEX", "CUN", "VIVA_AEROBUS", 190),
            ("2025M01", "MEX", "CUN", "VOLARIS", 137),
            ("2025M01", "TIJ", "UPN", "VOLARIS", 41),
            ("2025M01", "NLU", "TIJ", "VIVA_AEROBUS", 60),
            ("2025M01", "BJX", "MTY", "VOLARIS", 0),
        ],
        columns=list(FLIGHT_COLUMNS_FOR_TEST),
    )


FLIGHT_COLUMNS_FOR_TEST = ("period_id", "origin_iata", "dest_iata", "carrier_key", "flights")


def test_every_afac_city_has_an_airport_code() -> None:
    route_totals, _ = load_afac_domestic_margins()
    cities = load_city_crosswalk()

    named = set()
    for route_key in route_totals["route_key"]:
        named.update(route_key.split("-", 1) if route_key.count("-") == 1 else [])

    assert len(cities) == 52
    assert named <= set(cities.values())


def test_the_two_metropolitan_airports_stay_distinct() -> None:
    """MEXICO is Benito Juárez and SANTA LUCÍA is AIFA; collapsing them is wrong."""

    cities = load_city_crosswalk()

    assert cities["MEX"] == "MEXICO"
    assert cities["NLU"] == "SANTA LUCÍA"
    assert cities["BJX"] == "DEL BAJIO"


def test_every_afac_carrier_name_maps_to_a_project_key() -> None:
    crosswalk = load_carrier_crosswalk()
    margins = pd.read_csv("data/reference/afac_carrier_domestic_2025q1.csv")

    assert set(margins["carrier_name"]) <= set(crosswalk)
    assert crosswalk["Aeroméxico Connect (Aerolitoral)"] == "AEROMEXICO_CONNECT"


def test_seed_is_rekeyed_into_the_afac_city_vocabulary() -> None:
    seed = build_seed_from_flights(_flights_fixture())

    assert set(seed.columns) == {"period_id", "route_key", "carrier_key", "weight"}
    assert "MEXICO-CANCUN" in set(seed["route_key"])
    assert "SANTA LUCÍA-TIJUANA" in set(seed["route_key"])


def test_seed_drops_routes_a_carrier_did_not_fly() -> None:
    seed = build_seed_from_flights(_flights_fixture())

    assert "DEL BAJIO-MONTERREY" not in set(seed["route_key"])


def test_seed_rejects_an_airport_it_cannot_place() -> None:
    flights = _flights_fixture()
    flights.loc[len(flights)] = ("2025M01", "MEX", "LAX", "AEROMEXICO", 136)

    with pytest.raises(UnmappedSeedError, match="LAX"):
        build_seed_from_flights(flights)


def test_a_provider_seed_plugs_straight_into_the_published_margins() -> None:
    """End to end: flights in, passengers by route and carrier out."""

    route_totals, carrier_totals = load_afac_domestic_margins()
    seed = build_seed_from_flights(_flights_fixture())

    estimate, diagnostics = estimate_route_carrier(seed, route_totals, carrier_totals)

    assert diagnostics.loc[0, "converged"]
    mex_cun = estimate[estimate["route_key"] == "MEXICO-CANCUN"]
    assert set(mex_cun["carrier_key"]) == {"AEROMEXICO", "VIVA_AEROBUS", "VOLARIS"}
    # Convergence is relative to the grand total, so a single route may land a
    # fraction of a passenger away; within one passenger is the meaningful test.
    assert mex_cun["passengers_estimated"].sum() == pytest.approx(142_919, abs=1.0)
