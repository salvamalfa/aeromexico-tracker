"""The backtest has to be able to fail, or it is not measuring anything.

A harness that reports a small error whatever it is fed is worse than none: it
would license extending the estimator to Europe on the strength of a number
that never moved.  These tests check the two halves separately -- that a seed
carrying the truth is recovered, and that a seed carrying a *route-specific*
distortion is not -- and then that every stratification reports the cells it
was given rather than quietly dropping some.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analytics.route_carrier_backtest import (
    DISTANCE_LABELS,
    SIZE_LABELS,
    great_circle_km,
    rebuild_from_margins,
    stratified_backtest,
)


def _panel() -> pd.DataFrame:
    """Two months of a small market: four routes, three carriers, one monopoly."""

    rows = []
    truth = {
        ("MEX-LAX", "AEROMEXICO"): (12_000, 90),
        ("MEX-LAX", "DELTA"): (8_000, 60),
        ("MEX-LAX", "VOLARIS"): (4_000, 40),
        ("MEX-JFK", "AEROMEXICO"): (6_000, 45),
        ("MEX-JFK", "DELTA"): (9_000, 62),
        ("GDL-ORD", "VOLARIS"): (3_000, 30),
        ("GDL-ORD", "AEROMEXICO"): (1_000, 12),
        ("MTY-IAH", "AEROMEXICO"): (2_500, 28),
    }
    for period in ("2026M01", "2026M02"):
        for (route, carrier), (passengers, departures) in truth.items():
            rows.append(
                {
                    "period_id": period,
                    "route_key": route,
                    "carrier_key": carrier,
                    "passengers": float(passengers),
                    "seats": float(departures) * 150.0,
                    "departures": float(departures),
                }
            )
    return pd.DataFrame(rows)


def test_a_seed_that_is_the_answer_is_recovered_exactly() -> None:
    panel = _panel()
    seeded = panel.copy()
    seeded["departures"] = seeded["passengers"]

    rebuilt = rebuild_from_margins(seeded, seed_metric="departures")

    assert np.allclose(rebuilt["passengers_estimated"], rebuilt["passengers"])
    assert rebuilt["share_error_pp"].max() == pytest.approx(0.0, abs=1e-6)


def test_a_route_specific_distortion_survives_and_is_reported() -> None:
    """A per-route load-factor difference is exactly what IPF cannot cancel."""

    panel = _panel()
    distorted = panel.copy()
    heavy = (distorted["route_key"] == "MEX-LAX") & (distorted["carrier_key"] == "DELTA")
    distorted.loc[heavy, "departures"] *= 4

    rebuilt = rebuild_from_margins(distorted, seed_metric="departures")
    lax = rebuilt[rebuilt["route_key"] == "MEX-LAX"]

    assert lax["share_error_pp"].max() > 5.0


def test_a_row_or_column_scaling_is_cancelled_by_the_fit() -> None:
    """Gauge and coverage are scalings; only the interaction should survive."""

    panel = _panel()
    scaled = panel.copy()
    scaled.loc[scaled["carrier_key"] == "DELTA", "departures"] *= 7
    scaled.loc[scaled["route_key"] == "MEX-JFK", "departures"] *= 3

    baseline = rebuild_from_margins(panel, seed_metric="departures")
    rescaled = rebuild_from_margins(scaled, seed_metric="departures")

    assert np.allclose(
        baseline["passengers_estimated"].to_numpy(),
        rescaled["passengers_estimated"].to_numpy(),
    )


def test_the_monopoly_route_is_excluded_from_every_stratum() -> None:
    """MTY-IAH is recovered by construction and would flatter every average."""

    report = stratified_backtest(panel=_panel(), min_carriers=2)

    assert "MTY-IAH" not in set(report["celdas"]["route_key"])
    assert report["global"].loc[0, "routes"] == 3


def test_every_cell_lands_in_exactly_one_band_of_each_cut() -> None:
    report = stratified_backtest(panel=_panel(), min_carriers=2)
    cells = len(report["celdas"])

    for cut in ("por_periodo", "por_operador", "por_competencia", "por_tamano", "por_distancia"):
        assert report[cut]["observations"].sum() == cells, cut


def test_the_weighted_and_unweighted_reads_are_both_reported() -> None:
    """Reporting only the passenger-weighted mean is what made 1.98 pp sound safe."""

    report = stratified_backtest(panel=_panel(), min_carriers=2)
    overall = report["global"].iloc[0]

    for column in ("share_mae_pp_weighted", "share_mae_pp_unweighted", "share_p90_pp", "share_max_pp"):
        assert column in report["global"].columns
        assert np.isfinite(overall[column])


def test_an_unknown_distance_gets_its_own_band_instead_of_a_guess() -> None:
    panel = _panel().copy()
    panel["route_key"] = panel["route_key"].replace({"GDL-ORD": "GDL-ZZZ"})

    report = stratified_backtest(panel=panel, min_carriers=2)
    bands = set(report["por_distancia"]["distance_band"])

    assert "distancia desconocida" in bands
    assert bands <= set(DISTANCE_LABELS) | {"distancia desconocida"}


def test_size_bands_are_named_and_within_the_declared_set() -> None:
    report = stratified_backtest(panel=_panel(), min_carriers=2)

    assert set(report["por_tamano"]["size_band"]) <= set(SIZE_LABELS)


def test_a_seed_metric_outside_the_contract_is_refused() -> None:
    with pytest.raises(ValueError, match="seed_metric"):
        rebuild_from_margins(_panel(), seed_metric="passengers")


def test_a_panel_missing_the_joint_cell_cannot_be_backtested() -> None:
    panel = _panel().drop(columns=["passengers"])

    with pytest.raises(ValueError, match="missing required column"):
        rebuild_from_margins(panel)


def test_great_circle_matches_a_known_pair() -> None:
    """MEX-MAD is about 9,050 km; every T-100 band sits far below it."""

    distance = great_circle_km(
        pd.Series([19.4363]), pd.Series([-99.0721]),
        pd.Series([40.4936]), pd.Series([-3.5668]),
    )

    assert distance.iloc[0] == pytest.approx(9_050, rel=0.02)
