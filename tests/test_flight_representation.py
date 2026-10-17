"""Representation is not a proxy for observed coverage or flight scheduling."""

from copy import deepcopy

import pandas as pd
import pytest

from scripts.research.flight_representation import (
    finalize,
    route_values,
    select_network,
    sum_known,
    summarize_network,
)


def component(kind="observed", value=10, carrier="AEROMEXICO", month="2026M04", **extra):
    return dict(
        carrier_key=carrier,
        origin_iata="MEX",
        destination_iata="LAX",
        period_id=month,
        kind=kind,
        departures=value,
        source_label="Estados Unidos · BTS T-100",
        source_hashes=[],
        **extra,
    )


def route(components, market="LAX<>MEX"):
    active = [c for c in components if c["kind"] != "scheduled"] or components
    return dict(
        market_key=market, departures=sum(c["departures"] for c in active), flight_components=components
    )


def values(r):
    return route_values(r, "AEROMEXICO", "2026Q2", {}, {}, pd.DataFrame())


def test_mixed_components_keep_scheduling_and_service_classes_separate():
    r = route(
        [
            component(service_class_departures={"F": 8, "L": 2}),
            component("estimated", 4, month="2026M05"),
            component("scheduled", 30, month="2026M06"),
        ]
    )
    totals, strict, _, _ = values(r)
    assert totals == dict(observed=10, estimated=4, scheduled=30, attributed=None)
    assert strict == 8
    row = {
        **{f"{k}_flights": v for k, v in totals.items()},
        "strict_observed_regular_flights": strict,
        "official_regular_flights": 20,
    }
    finalize(row)
    assert row["representation_pct"] == 70
    assert row["strict_observed_regular_pct"] == 40
    assert row["additional_flights_to_95"] == 5


def test_explicit_zero_not_missing_and_no_clipping_or_scaling():
    assert sum_known([None, 0]) == 0
    assert sum_known([None]) is None
    r = route([component(value=0, service_class_departures={"F": 0})])
    assert values(r)[0]["observed"] == 0
    row = dict(
        observed_flights=21,
        estimated_flights=None,
        official_regular_flights=20,
        strict_observed_regular_flights=21,
    )
    finalize(row)
    assert row["representation_pct"] == 105
    assert row["above_official_regular_total"]


def test_connect_aggregates_as_group_without_foreign_volaris_subsidiaries():
    r = route([component(), component(value=7, carrier="AEROMEXICO_CONNECT")])
    assert values(r)[0]["observed"] == 17
    r["flight_components"][1]["carrier_key"] = "VOLARIS_COSTA_RICA"
    with pytest.raises(ValueError, match="Foreign operator"):
        values(r)


def test_duplicate_and_conflicting_cells_rejected_not_counted_twice():
    c = component()
    with pytest.raises(ValueError, match="Duplicate"):
        values(route([c, deepcopy(c)]))
    with pytest.raises(ValueError, match="Overlapping"):
        values(route([c, component("estimated")]))
    totals, _, _, _ = values(route([c, component("scheduled", 50)]))
    assert totals["observed"] == 10 and totals["scheduled"] == 50


def test_components_must_reconcile_market_period_classes_and_display():
    for change, message in [
        ({"period_id": "2026M07"}, "outside"),
        ({"destination_iata": "JFK"}, "direction"),
        ({"service_class_departures": {"F": 9}}, "reconcile"),
    ]:
        c = component()
        c.update(change)
        with pytest.raises(ValueError, match=message):
            values(route([c]))
    r = route([component()])
    r["departures"] += 1
    with pytest.raises(ValueError, match="component sum"):
        values(r)


def test_all_selectable_routes_are_not_initial_top12():
    routes = []
    for i in range(13):
        c = component(value=i)
        c["destination_iata"] = f"X{i:02d}"
        routes.append(route([c], market=f"MEX<>X{i:02d}"))
    result = summarize_network({"routes": routes}, "AEROMEXICO", "2026Q2", {}, pd.DataFrame())
    assert result["all_selectable_routes"] == 13
    assert result["initial_top12_routes"] == 12
    assert result["observed_flights"] == sum(range(13))
    # Replace the zero tail with one positive movement, preserving deterministic order.
    routes[0]["departures"] = 1
    routes[0]["flight_components"][0]["departures"] = 1
    result = summarize_network({"routes": routes}, "AEROMEXICO", "2026Q2", {}, pd.DataFrame())
    assert result["observed_flights"] == 79
    assert result["initial_top12_represented_flights"] == 78


def test_quarter_only_legacy_export_never_allocated_to_months():
    documents = {"2026Q2": {"routes": [route([component()])]}}
    assert select_network(documents, "international", "2026M06") == (None, None)
    unknown = summarize_network(None, "AEROMEXICO", "2026M06", {}, pd.DataFrame())
    assert unknown["observed_flights"] is None
    assert "no temporal allocation" in unknown["comparability_notes"]


def test_domestic_quarter_aggregates_estimate_months_keeps_native_separate():
    native = {"routes": [route([component("scheduled", 100)])]}
    documents = {"2026Q2": native}
    for month, value in zip(("2026M04", "2026M05", "2026M06"), (10, 20, 30), strict=True):
        documents[month] = {"routes": [route([component("estimated", value, month=month)])]}
    network, official = select_network(documents, "domestic", "2026Q2")
    assert official is native
    assert network["routes"][0]["departures"] == 60
    assert len(network["routes"][0]["flight_components"]) == 3


def test_native_monthly_schedule_uses_source_months_without_division():
    documents = {
        "2026Q2": {
            "routes": [
                route(
                    [
                        component("scheduled", 11, month="2026M04"),
                        component("scheduled", 29, month="2026M05"),
                    ]
                )
            ]
        },
        "2026M04": {"routes": []},
    }
    _, native = select_network(documents, "domestic", "2026M04")
    assert native["routes"][0]["departures"] == 11
    assert len(native["routes"][0]["flight_components"]) == 1
    assert select_network(documents, "domestic", "2026M06")[1] is None


def test_deltas_preserve_unavailable_monthly_baseline():
    from scripts.research.flight_representation import add_baseline_deltas

    rows = [
        dict(
            snapshot=label,
            entity="AEROMEXICO",
            scope="combined",
            period_id=period,
            represented_observed_plus_estimated_flights=value,
            representation_pct=pct,
        )
        for label, period, value, pct in [
            ("before", "2026Q2", 60, 60),
            ("before", "2026M06", None, None),
            ("after", "2026Q2", 90, 90),
            ("after", "2026M06", 30, 90),
        ]
    ]
    add_baseline_deltas(rows)
    assert rows[2]["delta_vs_baseline_flights"] == 30
    assert rows[2]["delta_vs_baseline_percentage_points"] == 30
    assert rows[3]["delta_vs_baseline_flights"] is None
