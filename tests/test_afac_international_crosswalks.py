"""A crosswalk fails silently or not at all, so its guards are the tests.

Mapping the wrong airport onto a city moves passengers between routes and
leaves no trace in any total. The two guards that make that detectable are a
refusal to accept airports too far apart to be one city, and a loud report of
margin names the crosswalk never mentions -- the second one having already
caught a nine-per-cent hole created by writing ``United Airlines`` where AFAC
publishes ``United Airlines, Inc.``.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.ingest.afac.international_crosswalks import (
    AmbiguousCityError,
    UnknownCountryError,
    build_city_crosswalk,
    carrier_coverage,
    carriers_missing_from_crosswalk,
    city_coverage,
    load_carrier_crosswalk,
    normalise_city,
    unresolved_carrier_weight,
)


def _routes(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        rows,
        columns=["period_id", "origen", "pais_origen", "destino", "pais_destino", "vuelos", "pasajeros"],
    )


def _airport_gold(tmp_path, rows: list[tuple]) -> None:
    frame = pd.DataFrame(
        rows,
        columns=["airport_iata", "city", "country", "type", "latitude", "longitude"],
    )
    (tmp_path / "gold").mkdir(parents=True, exist_ok=True)
    frame.to_parquet(tmp_path / "gold" / "dim_airport.parquet")


def _reference(tmp_path, overrides: list[tuple] = (), domestic: list[tuple] = ()) -> None:
    reference = tmp_path / "reference"
    reference.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        list(overrides) or [],
        columns=["afac_city", "afac_country", "action", "dim_city", "airport_iata", "note"],
    ).to_csv(reference / "afac_international_city_overrides.csv", index=False)
    pd.DataFrame(
        list(domestic) or [("MEXICO", "MEX")],
        columns=["afac_city", "airport_iata"],
    ).to_csv(reference / "afac_city_iata_crosswalk.csv", index=False)


def test_a_city_resolves_to_every_airport_that_serves_it(tmp_path) -> None:
    _airport_gold(tmp_path, [
        ("JFK", "New York", "US", "large_airport", 40.64, -73.78),
        ("LGA", "New York", "US", "large_airport", 40.78, -73.87),
    ])
    _reference(tmp_path, overrides=[("NUEVA YORK", "Estados Unidos", "map_city", "New York", "", "exonimo")])
    routes = _routes([("2026M05", "MEXICO", "Mexico", "NUEVA YORK", "Estados Unidos", 10, 1_000)])

    crosswalk, unresolved = build_city_crosswalk(
        routes, reference_dir=tmp_path / "reference", gold_dir=tmp_path / "gold"
    )

    assert set(crosswalk.loc[crosswalk["afac_city"] == "NUEVA YORK", "airport_iata"]) == {"JFK", "LGA"}
    assert unresolved.empty


def test_airports_too_far_apart_are_refused_rather_than_merged(tmp_path) -> None:
    """Las Vegas, Nevada and Las Vegas, New Mexico are 907 km apart."""

    _airport_gold(tmp_path, [
        ("LAS", "Las Vegas", "US", "large_airport", 36.08, -115.15),
        ("LVS", "Las Vegas", "US", "medium_airport", 35.65, -105.14),
        ("MEX", "Mexico City", "MX", "large_airport", 19.44, -99.07),
    ])
    _reference(tmp_path)
    routes = _routes([("2026M05", "MEXICO", "Mexico", "LAS VEGAS", "Estados Unidos", 10, 1_000)])

    with pytest.raises(AmbiguousCityError, match="LAS VEGAS"):
        build_city_crosswalk(
            routes, reference_dir=tmp_path / "reference", gold_dir=tmp_path / "gold"
        )


def test_an_excluded_homonym_lets_the_city_resolve(tmp_path) -> None:
    _airport_gold(tmp_path, [
        ("LAS", "Las Vegas", "US", "large_airport", 36.08, -115.15),
        ("LVS", "Las Vegas", "US", "medium_airport", 35.65, -105.14),
        ("MEX", "Mexico City", "MX", "large_airport", 19.44, -99.07),
    ])
    _reference(tmp_path, overrides=[("LAS VEGAS", "Estados Unidos", "exclude", "", "LVS", "New Mexico")])
    routes = _routes([("2026M05", "MEXICO", "Mexico", "LAS VEGAS", "Estados Unidos", 10, 1_000)])

    crosswalk, _ = build_city_crosswalk(
        routes, reference_dir=tmp_path / "reference", gold_dir=tmp_path / "gold"
    )

    assert set(crosswalk.loc[crosswalk["afac_city"] == "LAS VEGAS", "airport_iata"]) == {"LAS"}


def test_a_label_nothing_places_is_reported_not_guessed(tmp_path) -> None:
    _airport_gold(tmp_path, [("MEX", "Mexico City", "MX", "large_airport", 19.44, -99.07)])
    _reference(tmp_path)
    routes = _routes([("2026M05", "MEXICO", "Mexico", "TIMBUKTU", "Estados Unidos", 10, 1_000)])

    crosswalk, unresolved = build_city_crosswalk(
        routes, reference_dir=tmp_path / "reference", gold_dir=tmp_path / "gold"
    )

    assert list(unresolved["afac_city"]) == ["TIMBUKTU"]
    assert "TIMBUKTU" not in set(crosswalk["afac_city"])


def test_an_unknown_country_label_stops_the_build(tmp_path) -> None:
    _airport_gold(tmp_path, [("MEX", "Mexico City", "MX", "large_airport", 19.44, -99.07)])
    _reference(tmp_path)
    routes = _routes([("2026M05", "MEXICO", "Mexico", "NARNIA", "Narnia", 10, 1_000)])

    with pytest.raises(UnknownCountryError, match="Narnia"):
        build_city_crosswalk(
            routes, reference_dir=tmp_path / "reference", gold_dir=tmp_path / "gold"
        )


def test_a_route_counts_as_covered_only_when_both_ends_resolve() -> None:
    routes = _routes([
        ("2026M05", "MEXICO", "Mexico", "MADRID", "España", 100, 30_000),
        ("2026M05", "MEXICO", "Mexico", "TIMBUKTU", "Estados Unidos", 10, 1_000),
    ])
    crosswalk = pd.DataFrame(
        [("MEXICO", "Mexico", "MEX"), ("MADRID", "España", "MAD")],
        columns=["afac_city", "afac_country", "airport_iata"],
    )

    report = city_coverage(routes, crosswalk)[0]

    assert report.routes_covered == 1 and report.routes_total == 2
    assert report.passenger_share == pytest.approx(30_000 / 31_000)
    assert report.flight_share == pytest.approx(100 / 110)


def test_a_margin_name_absent_from_the_crosswalk_is_reported_loudly() -> None:
    """The failure that hid nine per cent of the market behind a missing suffix."""

    margin = pd.DataFrame(
        [("2026M05", "United Airlines, Inc.", "foreign", 500_000),
         ("2026M05", "Iberia", "foreign", 50_000)],
        columns=["period_id", "carrier_name", "carrier_block", "pasajeros"],
    )
    crosswalk = pd.DataFrame(
        [("United Airlines", "UNITED", "UA", "UAL", "resolved"),
         ("Iberia", "IBERIA", "IB", "IBE", "resolved")],
        columns=["afac_carrier_name", "carrier_key", "iata", "icao", "confidence"],
    )

    missing = carriers_missing_from_crosswalk(margin, crosswalk)

    assert list(missing["carrier_name"]) == ["United Airlines, Inc."]
    assert missing["share_pct"].iloc[0] == pytest.approx(100 * 500_000 / 550_000)


def test_probable_codes_count_as_usable_and_unresolved_ones_do_not() -> None:
    margin = pd.DataFrame(
        [("2026M05", "Iberia", "foreign", 60_000),
         ("2026M05", "Air France", "foreign", 30_000),
         ("2026M05", "Orbest", "foreign", 10_000)],
        columns=["period_id", "carrier_name", "carrier_block", "pasajeros"],
    )
    crosswalk = pd.DataFrame(
        [("Iberia", "IBERIA", "IB", "IBE", "resolved"),
         ("Air France", "AIR_FRANCE", "AF", "AFR", "probable"),
         ("Orbest", "ORBEST", "", "", "unresolved")],
        columns=["afac_carrier_name", "carrier_key", "iata", "icao", "confidence"],
    )

    report = carrier_coverage(margin, crosswalk)[0]
    unresolved = unresolved_carrier_weight(margin, crosswalk)

    assert report.passenger_share == pytest.approx(90_000 / 100_000)
    assert list(unresolved["carrier_name"]) == ["Orbest"]


def test_the_shipped_carrier_crosswalk_has_no_duplicate_names() -> None:
    frame = load_carrier_crosswalk()

    assert not frame["afac_carrier_name"].duplicated().any()
    assert set(frame["confidence"]) <= {"resolved", "probable", "unresolved"}


def test_normalisation_folds_accents_punctuation_and_spacing() -> None:
    assert normalise_city("San José (Alajuela)") == normalise_city("SAN JOSE (ALAJUELA)")
    assert normalise_city("Dallas-Fort Worth") == "DALLAS FORT WORTH"
    assert normalise_city(" Mc  Allen ") == "MC ALLEN"
