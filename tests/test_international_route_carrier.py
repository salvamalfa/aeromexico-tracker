"""The gate has to refuse for the right reason, not merely refuse.

A gate that rejects everything is as useless as one that accepts everything:
the operator needs to know *which* property failed to decide whether a partial
fit is still worth having. So each failure mode gets a test that triggers that
one finding and leaves the others alone.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analytics.route_carrier import SEED_COLUMNS
from src.analytics.international_route_carrier import (
    UNSPLIT_AEROMEXICO,
    VERDICT_ACCEPT,
    VERDICT_REJECT,
    VERDICT_REVIEW,
    CityLabelCollisionError,
    afac_route_flights,
    ambiguous_operator_codes,
    assess_international_seed,
    build_international_margins,
    build_international_seed,
    carrier_lookup,
    city_lookup,
    group_aeromexico,
    observed_cells_to_exclude,
)


CITIES = pd.DataFrame(
    [
        ("MEXICO", "Mexico", "MEX", "domestic_crosswalk", 0.0),
        ("MADRID", "España", "MAD", "city_exact", 0.0),
        ("BOGOTA", "Colombia", "BOG", "city_exact", 0.0),
    ],
    columns=["afac_city", "afac_country", "airport_iata", "match_method", "city_spread_km"],
)

CARRIERS = pd.DataFrame(
    [
        ("Aeroméxico (Aerovías de México)", "national", "AEROMEXICO", "AM", "AMX", "resolved", ""),
        ("Aeroméxico Connect (Aerolitoral)", "national", "AEROMEXICO_CONNECT", "5D", "SLI", "resolved", ""),
        ("Iberia (Iberia Líneas Aéreas de España)", "foreign", "IBERIA", "IB", "IBE", "resolved", ""),
        ("Avianca (Aerovías del Continente Americano)", "foreign", "AVIANCA", "AV", "AVA", "probable", ""),
        ("Orbest", "foreign", "ORBEST", "", "", "unresolved", ""),
    ],
    columns=["afac_carrier_name", "carrier_block", "carrier_key", "iata", "icao", "confidence", "evidence"],
)


def _capture(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=[
            "period_id", "origin_iata", "dest_iata", "operator_key",
            "operator_iata", "operator_icao", "flights",
            "codeshare_unknown", "status_incomplete",
        ],
    )


def _margins(route_rows: list[tuple], carrier_rows: list[tuple]):
    routes = pd.DataFrame(
        route_rows,
        columns=["period_id", "origen", "pais_origen", "destino", "pais_destino", "vuelos", "pasajeros"],
    )
    carriers = pd.DataFrame(carrier_rows, columns=["period_id", "carrier_name", "carrier_block", "pasajeros"])
    return routes, carriers


def _balanced():
    """One month where everything lines up: both directions, full coverage."""

    capture = _capture([
        ("2026M05", "MEX", "MAD", "AEROMEXICO", "AM", "AMX", 60.0, 0.0, 0.0),
        ("2026M05", "MAD", "MEX", "AEROMEXICO", "AM", "AMX", 60.0, 0.0, 0.0),
        ("2026M05", "MEX", "MAD", "IATA:IB", "IB", "IBE", 40.0, 0.0, 0.0),
        ("2026M05", "MAD", "MEX", "IATA:IB", "IB", "IBE", 40.0, 0.0, 0.0),
    ])
    routes, carriers = _margins(
        [
            ("2026M05", "MEXICO", "Mexico", "MADRID", "España", 100, 30_000),
            ("2026M05", "MADRID", "España", "MEXICO", "Mexico", 100, 30_000),
        ],
        [
            ("2026M05", "Aeroméxico (Aerovías de México)", "national", 36_000),
            ("2026M05", "Iberia (Iberia Líneas Aéreas de España)", "foreign", 24_000),
        ],
    )
    return capture, routes, carriers


def _run(capture, routes, carriers, *, period_id="2026M05"):
    seed, rejected = build_international_seed(capture, CITIES, CARRIERS)
    route_totals, carrier_totals = build_international_margins(routes, carriers, CARRIERS)
    return seed, assess_international_seed(
        capture, seed, rejected, route_totals, carrier_totals,
        afac_route_flights(routes), CARRIERS, period_id=period_id,
    )


def test_a_clean_capture_is_accepted() -> None:
    seed, report = _run(*_balanced())

    assert report.verdict == VERDICT_ACCEPT, [str(f) for f in report.findings]
    assert report.route_passenger_coverage == pytest.approx(1.0)
    assert report.carrier_passenger_coverage == pytest.approx(1.0)
    assert report.column_scale == pytest.approx(1.0)
    assert set(seed["route_key"]) == {"MEXICO-MADRID", "MADRID-MEXICO"}


def test_route_keys_use_the_afac_city_vocabulary_not_iata() -> None:
    seed, _ = _run(*_balanced())

    assert "MEX-MAD" not in set(seed["route_key"])
    assert "MEXICO-MADRID" in set(seed["route_key"])


def test_a_duplicated_leg_is_rejected_before_it_doubles_a_share() -> None:
    capture, routes, carriers = _balanced()
    capture = pd.concat([capture, capture.iloc[[0]]], ignore_index=True)

    _, report = _run(capture, routes, carriers)

    assert report.verdict == VERDICT_REJECT
    assert any(f.code == "duplicados" for f in report.findings)


def test_a_market_captured_in_one_direction_only_is_flagged() -> None:
    capture, routes, carriers = _balanced()
    capture = capture[capture["origin_iata"] != "MAD"]

    _, report = _run(capture, routes, carriers)

    codes = {f.code for f in report.findings}
    assert "direcciones_perdidas" in codes
    assert report.verdict in {VERDICT_REVIEW, VERDICT_REJECT}


def test_an_unsplit_aeromexico_flight_is_kept_out_and_counted() -> None:
    capture, routes, carriers = _balanced()
    capture.loc[len(capture)] = (
        "2026M05", "MEX", "BOG", UNSPLIT_AEROMEXICO, "AM", "AMX", 10.0, 0.0, 0.0
    )

    seed, report = _run(capture, routes, carriers)

    assert "MEXICO-BOGOTA" not in set(seed["route_key"])
    assert any(f.code == "aeromexico_sin_separar" for f in report.findings)


def test_an_operator_without_a_reviewed_entry_never_joins_a_neighbour() -> None:
    capture, routes, carriers = _balanced()
    capture.loc[len(capture)] = (
        "2026M05", "MEX", "MAD", "IATA:ZZ", "ZZ", "ZZZ", 25.0, 0.0, 0.0
    )

    seed, report = _run(capture, routes, carriers)

    assert set(seed["carrier_key"]) == {"AEROMEXICO", "IBERIA"}
    assert any(f.code == "operadores_sin_revisar" for f in report.findings)


def test_a_code_two_carriers_claim_is_reported_not_resolved() -> None:
    clashing = pd.concat([
        CARRIERS,
        pd.DataFrame([("Mexicana", "national", "MEXICANA_NUEVA", "AM", "MXA", "probable", "")],
                     columns=CARRIERS.columns),
    ], ignore_index=True)

    assert ambiguous_operator_codes(clashing) == {"AM": {"AEROMEXICO", "MEXICANA_NUEVA"}}
    assert "AM" not in carrier_lookup(clashing)


def test_unresolved_codeshare_above_the_reject_threshold_blocks_the_fit() -> None:
    capture, routes, carriers = _balanced()
    capture["codeshare_unknown"] = capture["flights"] * 0.6

    _, report = _run(capture, routes, carriers)

    assert report.verdict == VERDICT_REJECT
    assert report.unknown_codeshare_share == pytest.approx(0.6)
    assert any(f.code == "codeshare_sin_resolver" and f.severity == "reject" for f in report.findings)


def test_a_modest_codeshare_share_is_a_review_not_a_refusal() -> None:
    capture, routes, carriers = _balanced()
    capture["codeshare_unknown"] = capture["flights"] * 0.18  # el valor medido en el sondeo

    _, report = _run(capture, routes, carriers)

    assert report.verdict == VERDICT_REVIEW
    assert any(f.code == "codeshare_sin_resolver" and f.severity == "review" for f in report.findings)


def test_insufficient_route_coverage_is_refused() -> None:
    capture, routes, carriers = _balanced()
    routes.loc[len(routes)] = ("2026M05", "MEXICO", "Mexico", "BOGOTA", "Colombia", 90, 40_000)

    _, report = _run(capture, routes, carriers)

    assert report.verdict == VERDICT_REJECT
    assert any(f.code == "cobertura_rutas" and f.severity == "reject" for f in report.findings)


def test_incompatible_margins_are_refused() -> None:
    capture, routes, carriers = _balanced()
    carriers.loc[carriers["carrier_name"].str.startswith("Iberia"), "pasajeros"] = 5_000

    _, report = _run(capture, routes, carriers)

    assert any(f.code == "margenes_incompatibles" for f in report.findings)
    assert report.verdict == VERDICT_REJECT


def test_a_small_uncovered_route_is_a_partial_fit_not_a_refusal() -> None:
    """The approved rule: coverage at or above 95% may be fitted, disclosed."""

    capture, routes, carriers = _balanced()
    seed, rejected = build_international_seed(capture, CITIES, CARRIERS)
    route_totals, carrier_totals = build_international_margins(routes, carriers, CARRIERS)
    route_totals.loc[len(route_totals)] = ("2026M05", "MEXICO-BOGOTA", 1_000)

    report = assess_international_seed(
        capture, seed, rejected, route_totals, carrier_totals,
        afac_route_flights(routes), CARRIERS, period_id="2026M05",
    )

    coverage = next(f for f in report.findings if f.code == "cobertura_rutas")
    assert coverage.severity == "review"
    assert report.route_passenger_coverage == pytest.approx(60_000 / 61_000)
    assert report.verdict == VERDICT_REVIEW


def test_a_carrier_with_passengers_and_no_route_is_caught_before_the_fit() -> None:
    """The estimator would raise InfeasibleMarginsError; the gate says so first."""

    capture, routes, carriers = _balanced()
    seed, rejected = build_international_seed(capture, CITIES, CARRIERS)
    route_totals, carrier_totals = build_international_margins(routes, carriers, CARRIERS)
    # Avianca publica pasajeros pero la semilla no la vio en ninguna ruta.
    carrier_totals.loc[len(carrier_totals)] = ("2026M05", "AVIANCA", 500)
    seed_with_avianca = pd.concat(
        [seed, pd.DataFrame([{
            "period_id": "2026M05", "route_key": "MEXICO-MADRID",
            "carrier_key": "AVIANCA", "weight": 0.0,
            "codeshare_unknown": 0.0, "status_incomplete": 0.0,
        }])],
        ignore_index=True,
    )

    report = assess_international_seed(
        capture, seed_with_avianca, rejected, route_totals, carrier_totals,
        afac_route_flights(routes), CARRIERS, period_id="2026M05",
    )

    assert any(f.code == "soporte_inviable_aerolineas" for f in report.findings)
    assert report.verdict == VERDICT_REJECT


def test_more_seed_flights_than_afac_publishes_is_flagged_as_schedule() -> None:
    capture, routes, carriers = _balanced()
    routes["vuelos"] = 10  # AFAC publica menos vuelos de los que trae la semilla

    _, report = _run(capture, routes, carriers)

    codes = {f.code for f in report.findings}
    assert "vuelos_por_encima_de_afac" in codes
    assert "razon_vuelos_semilla_afac" in codes


def test_a_status_that_does_not_say_the_flight_flew_is_noted() -> None:
    capture, routes, carriers = _balanced()
    capture["status_incomplete"] = capture["flights"]

    _, report = _run(capture, routes, carriers)

    note = next(f for f in report.findings if f.code == "estado_no_operado")
    assert note.severity == "note"
    assert report.verdict == VERDICT_ACCEPT


def test_an_airport_with_no_afac_city_is_dropped_with_a_reason() -> None:
    capture, routes, carriers = _balanced()
    capture.loc[len(capture)] = ("2026M05", "MEX", "ZZZ", "IATA:IB", "IB", "IBE", 5.0, 0.0, 0.0)

    seed, rejected = build_international_seed(capture, CITIES, CARRIERS)

    assert "aeropuerto sin ciudad AFAC" in set(rejected["rejection_reason"])
    assert len(seed) == 4


def test_a_city_label_two_countries_share_is_refused() -> None:
    colliding = pd.concat([
        CITIES,
        pd.DataFrame([("MADRID", "Estados Unidos", "MAF", "city_exact", 0.0)], columns=CITIES.columns),
    ], ignore_index=True)

    with pytest.raises(CityLabelCollisionError, match="MADRID"):
        city_lookup(colliding)


def test_group_aeromexico_adds_after_the_fit_and_keeps_the_subsidiaries() -> None:
    estimate = pd.DataFrame(
        [
            ("2026M05", "MEXICO-MADRID", "AEROMEXICO", 18_000.0),
            ("2026M05", "MEXICO-MADRID", "AEROMEXICO_CONNECT", 2_000.0),
            ("2026M05", "MEXICO-MADRID", "IBERIA", 10_000.0),
        ],
        columns=["period_id", "route_key", "carrier_key", "passengers_estimated"],
    )

    grouped = group_aeromexico(estimate)
    total = grouped[grouped["carrier_key"] == "AEROMEXICO_GROUP"]

    assert total["passengers_estimated"].iloc[0] == pytest.approx(20_000.0)
    assert {"AEROMEXICO", "AEROMEXICO_CONNECT"} <= set(grouped["carrier_key"])
    # El total del grupo no incluye a terceros.
    assert 10_000.0 not in set(total["passengers_estimated"])


def test_observed_cells_are_marked_so_they_are_never_summed_with_estimates() -> None:
    estimate = pd.DataFrame(
        [
            ("2026M05", "MEXICO-LOS ANGELES", "AEROMEXICO", 50_000.0),
            ("2026M05", "MEXICO-MADRID", "AEROMEXICO", 18_000.0),
        ],
        columns=["period_id", "route_key", "carrier_key", "passengers_estimated"],
    )
    observed = pd.DataFrame(
        [("2026M05", "MEXICO-LOS ANGELES", "AEROMEXICO")],
        columns=["period_id", "route_key", "carrier_key"],
    )

    marked = observed_cells_to_exclude(estimate, observed)

    assert list(marked["display_source"]) == ["observed_t100", "estimated"]


def test_an_empty_capture_is_refused_rather_than_fitted() -> None:
    capture, routes, carriers = _balanced()
    empty = capture.iloc[0:0]

    _, report = _run(empty, routes, carriers)

    assert report.verdict == VERDICT_REJECT
    assert any(f.code == "sin_semilla" for f in report.findings)


def test_a_major_airport_the_city_crosswalk_misses_is_refused() -> None:
    """Paris once resolved to Le Bourget, so CDG's flights fell out of the seed."""

    capture, routes, carriers = _balanced()
    missing = _capture([
        ("2026M05", "MEX", "TOJ", "AEROMEXICO", "AM", "AMX", 10.0, 0.0, 0.0),
    ])
    seed, report = _run(pd.concat([capture, missing], ignore_index=True), routes, carriers)

    finding = next(f for f in report.findings if f.code == "aeropuertos_sin_ciudad")
    assert finding.severity == "reject"
    assert "TOJ" in finding.detail and "MEX" not in finding.detail.split(":")[-1]
    assert report.verdict == VERDICT_REJECT


def test_the_sweep_seed_file_is_read_into_the_capture_contract() -> None:
    from src.analytics.international_route_carrier import capture_from_sweep

    sweep = pd.DataFrame(
        [
            ("2026M04", "MEX", "MAD", "AEROMEXICO", 5.0, 0.0, 0.0),
            ("2026M04", "MEX", "MAD", "IATA:IB", 5.0, 0.0, 0.0),
            ("2026M04", "MEX", "IST", "ICAO:THY", 5.0, 0.0, 0.0),
        ],
        columns=["period_id", "origin_iata", "dest_iata", "operator_key",
                 "flights", "codeshare_unknown", "status_incomplete"],
    )

    capture = capture_from_sweep([sweep])

    assert list(capture["operator_iata"]) == ["", "IB", ""]
    assert list(capture["operator_icao"]) == ["", "", "THY"]


def test_the_backtest_counts_an_observed_cell_the_fit_left_empty_as_error() -> None:
    from src.analytics.international_route_carrier import summarise_backtest, t100_backtest

    estimate = pd.DataFrame(
        [
            ("2026M04", "MEXICO-MADRID", "AEROMEXICO", 900.0),
            ("2026M04", "MEXICO-MADRID", "AEROMEXICO_GROUP", 900.0),
        ],
        columns=["period_id", "route_key", "carrier_key", "passengers_estimated"],
    )
    observed = pd.DataFrame(
        [
            ("2026M04", "MEXICO-MADRID", "AEROMEXICO", 1_000.0),
            ("2026M04", "MEXICO-MADRID", "IBERIA", 500.0),
        ],
        columns=["period_id", "route_key", "carrier_key", "passengers_observed"],
    )

    cells = t100_backtest(estimate, observed)
    summary = summarise_backtest(cells)

    assert len(cells) == 2  # the group row is never compared with an observation
    assert summary["cells_missing_from_fit"] == 1
    assert summary["weighted_abs_error"] == pytest.approx((100 + 500) / 1_500)


def test_sensitivity_refits_without_guessed_operating_status() -> None:
    from src.analytics.international_route_carrier import codeshare_sensitivity

    capture, routes, carriers = _balanced()
    capture.loc[capture["operator_key"] == "IATA:IB", "codeshare_unknown"] = 20.0
    seed, _ = build_international_seed(capture, CITIES, CARRIERS)
    route_totals, carrier_totals = build_international_margins(routes, carriers, CARRIERS)

    no_families = pd.DataFrame(columns=["carrier_key", "fit_key", "fit_label", "reason"])
    compared = codeshare_sensitivity(seed, route_totals, carrier_totals, no_families)

    assert {"passengers_estimated", "passengers_estimated_declared_only"} <= set(compared.columns)
    total = compared.groupby("period_id")[
        ["passengers_estimated", "passengers_estimated_declared_only"]
    ].sum()
    assert total.iloc[0, 0] == pytest.approx(60_000)
    assert total.iloc[0, 1] == pytest.approx(60_000)


def test_an_unresolved_carrier_key_from_the_adapter_never_enters_the_seed() -> None:
    """Aerus reached the seed through the adapter's key while its margin was
    withheld as unresolved, leaving MONTERREY-BROWNSVILLE with no feasible fit."""

    capture, _, _ = _balanced()
    orbest = _capture([("2026M05", "MEX", "BOG", "ORBEST", "", "", 4.0, 0.0, 0.0)])
    seed, rejected = build_international_seed(
        pd.concat([capture, orbest], ignore_index=True), CITIES, CARRIERS
    )

    assert "ORBEST" not in set(seed["carrier_key"])
    assert list(rejected["rejection_reason"]) == ["operador sin carrier_key revisado"]


def test_a_route_served_only_by_a_carrier_without_margin_is_caught_before_the_fit() -> None:
    capture, routes, carriers = _balanced()
    capture = pd.concat([capture, _capture([
        ("2026M05", "MEX", "BOG", "IATA:AV", "AV", "AVA", 10.0, 0.0, 0.0),
        ("2026M05", "BOG", "MEX", "IATA:AV", "AV", "AVA", 10.0, 0.0, 0.0),
    ])], ignore_index=True)
    routes = pd.concat([routes, pd.DataFrame(
        [("2026M05", "MEXICO", "Mexico", "BOGOTA", "Colombia", 10, 300),
         ("2026M05", "BOGOTA", "Colombia", "MEXICO", "Mexico", 10, 300)],
        columns=routes.columns,
    )], ignore_index=True)

    _, report = _run(capture, routes, carriers)  # Avianca publishes no passengers

    finding = next(f for f in report.findings if f.code == "soporte_inviable_rutas")
    assert finding.severity == "reject" and "MEXICO-BOGOTA" in finding.detail


FAMILIES = pd.DataFrame(
    [("AVIANCA", "AVIANCA_GROUP", "Grupo Avianca", "codigo AV"),
     ("LACSA", "AVIANCA_GROUP", "Grupo Avianca", "codigo AV")],
    columns=["carrier_key", "fit_key", "fit_label", "reason"],
)


def _fit_frames():
    seed = pd.DataFrame(
        [
            ("2026M04", "MEXICO-MADRID", "AEROMEXICO", 60.0),
            ("2026M04", "MEXICO-MADRID", "IBERIA", 40.0),
            ("2026M04", "MEXICO-BOGOTA", "AVIANCA", 30.0),
            ("2026M04", "MEXICO-BOGOTA", "AEROMEXICO", 30.0),
        ],
        columns=list(SEED_COLUMNS),
    )
    routes = pd.DataFrame(
        [("2026M04", "MEXICO-MADRID", 30_000.0), ("2026M04", "MEXICO-BOGOTA", 12_000.0)],
        columns=["period_id", "route_key", "passengers"],
    )
    carriers = pd.DataFrame(
        [("2026M04", "AEROMEXICO", 24_000.0), ("2026M04", "IBERIA", 12_000.0),
         ("2026M04", "AVIANCA", 3_000.0), ("2026M04", "LACSA", 3_000.0)],
        columns=["period_id", "carrier_key", "passengers"],
    )
    return seed, routes, carriers


def test_carriers_the_seed_cannot_separate_are_fitted_as_their_family() -> None:
    """Lacsa flies under AV: alone it has no supply, pooled it has Avianca's."""

    from src.analytics.international_route_carrier import fit_international

    estimate, diagnostics = fit_international(*_fit_frames(), FAMILIES)

    assert "LACSA" not in set(estimate["carrier_key"])
    pooled = estimate[estimate["carrier_key"] == "AVIANCA_GROUP"]
    assert pooled["passengers_estimated"].sum() == pytest.approx(6_000, rel=1e-4)
    assert pooled["is_pooled_family"].all()
    assert bool(diagnostics["converged"].iloc[0])


def test_a_margin_larger_than_its_routes_is_capped_and_reported_not_spread() -> None:
    from src.analytics.international_route_carrier import UNALLOCATED, fit_international

    seed, routes, carriers = _fit_frames()
    carriers.loc[carriers["carrier_key"] == "IBERIA", "passengers"] = 40_000.0
    carriers = carriers[carriers["carrier_key"] != "AEROMEXICO"]

    estimate, diagnostics = fit_international(seed, routes, carriers, FAMILIES)
    row = diagnostics.iloc[0]

    # MADRID holds only 30,000, and the cap stays just inside that bound.
    assert row["passengers_capped"] == pytest.approx(40_000 - 30_000 * 0.995)
    assert bool(row["converged"])
    assert "IBERIA" in row["capped_carriers"]
    assert estimate.groupby("route_key")["passengers_estimated"].sum().to_dict() == pytest.approx(
        {"MEXICO-MADRID": 30_000, "MEXICO-BOGOTA": 12_000}, rel=1e-4
    )
    assert UNALLOCATED in set(estimate["carrier_key"])


def test_aeromexico_is_never_pooled() -> None:
    from src.analytics.international_route_carrier import load_carrier_families

    families = load_carrier_families()

    assert not set(families["carrier_key"]) & {"AEROMEXICO", "AEROMEXICO_CONNECT"}
    assert not families["carrier_key"].duplicated().any()


def test_one_pair_from_two_passes_is_fine_when_one_side_is_a_through_flight() -> None:
    from src.analytics.international_route_carrier import capture_from_sweep

    columns = ["period_id", "origin_iata", "dest_iata", "operator_key", "flights",
               "codeshare_unknown", "status_incomplete", "through_flights"]
    direct = pd.DataFrame([("2026M05", "MEX", "MAD", "AEROMEXICO", 60.0, 0.0, 0.0, 0.0),
                           ("2026M05", "MAD", "MEX", "AEROMEXICO", 60.0, 0.0, 0.0, 0.0),
                           ("2026M05", "MEX", "MAD", "IATA:IB", 40.0, 0.0, 0.0, 0.0),
                           ("2026M05", "MAD", "MEX", "IATA:IB", 40.0, 0.0, 0.0, 0.0)], columns=columns)
    through = pd.DataFrame([("2026M05", "MEX", "MAD", "AEROMEXICO", 5.0, 0.0, 0.0, 5.0)], columns=columns)
    _, routes, carriers = _balanced()

    _, fine = _run(capture_from_sweep([direct, through]), routes, carriers)
    _, twice = _run(capture_from_sweep([direct, direct]), routes, carriers)

    assert "duplicados" not in {f.code for f in fine.findings}
    assert "duplicados" in {f.code for f in twice.findings}


def test_a_hyphenated_city_label_is_reversed_correctly() -> None:
    from src.analytics.international_route_carrier import reverse_route_key

    known = {"DALLAS-FORT WORTH-CANCUN", "CANCUN-DALLAS-FORT WORTH"}

    assert reverse_route_key("CANCUN-DALLAS-FORT WORTH", known) == "DALLAS-FORT WORTH-CANCUN"
    assert reverse_route_key("DALLAS-FORT WORTH-CANCUN", known) == "CANCUN-DALLAS-FORT WORTH"
    assert reverse_route_key("CANCUN-MADRID", known) is None
