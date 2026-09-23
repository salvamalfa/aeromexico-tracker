"""The review page must surface every compromise, and never leak markup."""

from __future__ import annotations

import pandas as pd

from src.analytics.international_review import one_way_routes, render, route_review


def _frames():
    estimate = pd.DataFrame(
        [
            ("2026M04", "MEXICO-MADRID", "AEROMEXICO", 19_000.0, True, False),
            ("2026M04", "MEXICO-MADRID", "AEROMEXICO_GROUP", 19_000.0, None, None),
            ("2026M04", "MEXICO-MADRID", "SIN_ASIGNAR", 400.0, True, False),
            ("2026M04", "MEXICO-<b>X</b>", "SIN_ASIGNAR", 2.0, False, False),
            ("2026M04", "MEXICO-<b>X</b>", "AEROMEXICO", 500.0, False, False),
            ("2026M04", "MEXICO-<b>X</b>", "IBERIA", 500.0, False, False),
            ("2026M04", "MEXICO-<b>X</b>", "AEROMEXICO_GROUP", 500.0, None, None),
        ],
        columns=["period_id", "route_key", "carrier_key", "passengers_estimated",
                 "is_single_operator_seed", "is_pooled_family"],
    )
    totals = pd.DataFrame(
        [("2026M04", "MEXICO-MADRID", 19_012.0), ("2026M04", "MADRID-MEXICO", 18_000.0),
         ("2026M04", "MEXICO-<b>X</b>", 1_000.0)],
        columns=["period_id", "route_key", "passengers"],
    )
    diagnostics = pd.DataFrame([("2026M04", "IBERIA 40")], columns=["period_id", "capped_carriers"])
    backtest = pd.DataFrame(columns=["period_id", "route_key", "carrier_key", "passengers_observed",
                                     "passengers_estimated", "error"])
    return estimate, backtest, totals, diagnostics


def test_every_compromise_on_a_route_is_flagged() -> None:
    estimate, backtest, totals, diagnostics = _frames()

    routes = route_review(estimate, backtest, totals, diagnostics, period_id="2026M04").set_index("route_key")

    assert set(routes.loc["MEXICO-MADRID", "flags"]) == {
        "un solo operador en la semilla", "sentido opuesto sin semilla", "pasajeros sin asignar",
    }
    assert routes.loc["MEXICO-<b>X</b>", "flags"] == ["aerolinea topada en la ruta"]


def test_the_page_escapes_what_it_prints() -> None:
    estimate, backtest, totals, diagnostics = _frames()
    routes = route_review(estimate, backtest, totals, diagnostics, period_id="2026M04")
    seed = estimate[estimate["carrier_key"] != "AEROMEXICO_GROUP"]
    summary = {
        "acceptance": {"2026M04": {"verdict": "review", "acceptance_version": "v1",
                                   "route_passenger_coverage": 0.99, "carrier_passenger_coverage": 0.98,
                                   "findings": [{"code": "x", "severity": "review", "detail": "<script>", "value": 1}]}},
        "fit": [{"period_id": "2026M04", "converged": True, "passengers_capped": 40.0,
                 "passengers_unallocated": 12.0, "capped_carriers": "IBERIA 40", "reason": ""}],
    }
    families = pd.DataFrame(columns=["carrier_key", "fit_key", "fit_label", "reason"])

    page = render(period_id="2026M04", summary=summary, routes=routes,
                  one_way=one_way_routes(seed, totals, period_id="2026M04"),
                  backtest=backtest, families=families)

    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "<b>X</b>" not in page
    assert "MADRID-MEXICO" in page  # the missing direction is listed
    assert "http" not in page  # self-contained, nothing remote
