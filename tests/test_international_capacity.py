"""Seat capacity for Aeromexico's international routes, from a synthetic sweep."""

from __future__ import annotations

import pandas as pd
import pytest

from src.analytics.international_capacity import (
    OUTPUT_COLUMNS,
    captured_legs,
    derive,
    derive_period,
    load_seat_reference,
)

SEAT_REFERENCE = pd.DataFrame(
    [
        ("B737-800", "Boeing 737-800", "AEROMEXICO", 180, 170, 190, "midpoint", "https://example.org/20f", "", ""),
        ("E190", "Embraer 190", "AEROMEXICO_CONNECT", 99, 99, 99, "reported", "https://example.org/20f", "", ""),
    ],
    columns=["canonical_model", "raw_model", "carrier_key", "seats_point", "seats_low", "seats_high",
             "point_method", "primary_source_url", "secondary_source_url", "notes"],
)
CITIES = pd.DataFrame(
    [("MEXICO", "Mexico", "MEX"), ("MADRID", "España", "MAD"), ("BOGOTA", "Colombia", "BOG")],
    columns=["afac_city", "afac_country", "airport_iata"],
)
FOREIGN_THROUGH = pd.DataFrame(columns=["operator_key", "stop_iata", "first_iata", "reason"])
FLIGHT_COLUMNS = [
    "period_id", "origin_iata", "dest_iata", "operator_key", "operator_iata", "operator_icao",
    "operator_name", "aircraft_model", "via_iata", "flights", "codeshare_unknown", "status_incomplete",
]


def _flights(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=FLIGHT_COLUMNS)


def _write_reference(reference_dir):
    reference_dir.mkdir(parents=True, exist_ok=True)
    SEAT_REFERENCE.to_csv(reference_dir / "aeromexico_aircraft_seat_capacity.csv", index=False)
    CITIES.to_csv(reference_dir / "afac_international_city_iata_crosswalk.csv", index=False)
    FOREIGN_THROUGH.to_csv(reference_dir / "afac_international_foreign_through_flights.csv", index=False)


def test_load_seat_reference_keys_by_model_and_carrier(tmp_path):
    _write_reference(tmp_path)
    reference = load_seat_reference(tmp_path)
    assert reference[("Boeing 737-800", "AEROMEXICO")]["seats_point"] == 180
    assert ("Embraer 190", "AEROMEXICO") not in reference  # carrier-specific, not just model-specific
    assert reference[("Embraer 190", "AEROMEXICO_CONNECT")]["seats_low"] == 99


def test_captured_legs_drops_unmapped_city_and_foreign_carrier(tmp_path):
    silver = tmp_path / "silver"
    silver.mkdir()
    _flights([
        ("2026M04", "MEX", "MAD", "AEROMEXICO", "", "", "Aeromexico", "Boeing 737-800", "", 10.0, 0.0, 0.0),
        # ZZZ is not in the city crosswalk: both this leg's endpoints must map, so it drops out entirely,
        # the same acceptance rule build_international_seed applies to the passenger estimator's capture.
        ("2026M04", "MEX", "ZZZ", "AEROMEXICO", "", "", "Aeromexico", "Boeing 737-800", "", 3.0, 0.0, 0.0),
        # A foreign carrier is out of scope for this table entirely.
        ("2026M04", "MEX", "MAD", "IBERIA", "IB", "IBE", "Iberia", "Airbus A350", "", 7.0, 0.0, 0.0),
    ]).to_parquet(silver / "aerodatabox_international_flights_2026M04_nucleo.parquet", index=False)
    legs = captured_legs("2026M04", silver, CITIES, FOREIGN_THROUGH)
    assert set(legs["operator_key"]) == {"AEROMEXICO"}
    assert float(legs["flights"].sum()) == 10.0


def test_derive_period_maps_seats_and_gates_low_coverage_on_capacity_usable():
    reference = load_seat_reference_from_frames()
    legs = pd.DataFrame(
        [
            # MEX -> MAD, AEROMEXICO: 10 mapped + 2 unmapped-model = 83.3% coverage, below the 95% gate.
            ("2026M04", "MEX", "MAD", "AEROMEXICO", "Boeing 737-800", 10.0),
            ("2026M04", "MEX", "MAD", "AEROMEXICO", "Boeing 787-9 Dreamliner (unlisted variant)", 2.0),
            # MAD -> MEX, AEROMEXICO: fully mapped, at the gate.
            ("2026M04", "MAD", "MEX", "AEROMEXICO", "Boeing 737-800", 8.0),
            # MEX -> BOG, Connect: fully mapped.
            ("2026M04", "MEX", "BOG", "AEROMEXICO_CONNECT", "Embraer 190", 5.0),
        ],
        columns=["period_id", "origin_iata", "dest_iata", "operator_key", "aircraft_model", "flights"],
    )
    frame, report = derive_period("2026M04", legs, reference)

    assert list(frame.columns) == list(OUTPUT_COLUMNS)
    assert "aircraft_model" not in frame.columns  # no per-route model breakdown ever leaves this module

    low_coverage = frame[(frame.origin_iata == "MEX") & (frame.destination_iata == "MAD")].iloc[0]
    assert low_coverage["aircraft_model_coverage"] == pytest.approx(10 / 12)
    assert low_coverage["capacity_usable"] is False or low_coverage["capacity_usable"] == False  # noqa: E712
    assert pd.isna(low_coverage["seats_estimated"])
    assert pd.isna(low_coverage["departures_estimated"])

    full_coverage = frame[(frame.origin_iata == "MAD") & (frame.destination_iata == "MEX")].iloc[0]
    assert full_coverage["capacity_usable"] == True  # noqa: E712
    assert full_coverage["departures_estimated"] == pytest.approx(8.0)
    assert full_coverage["seats_estimated"] == pytest.approx(8.0 * 180)
    assert full_coverage["seats_estimated_low"] == pytest.approx(8.0 * 170)
    assert full_coverage["seats_estimated_high"] == pytest.approx(8.0 * 190)
    assert full_coverage["market_key"] == "MAD<>MEX"

    connect = frame[frame.carrier_key == "AEROMEXICO_CONNECT"].iloc[0]
    assert connect["capacity_usable"] == True  # noqa: E712
    assert connect["seats_estimated"] == pytest.approx(5.0 * 99)

    assert report["unmapped_models"] == {("Boeing 787-9 Dreamliner (unlisted variant)", "AEROMEXICO"): 2.0}
    # Candidate departures reconcile with the raw captured legs: every row here
    # already passed the city-mapping filter, so nothing else is dropped.
    assert report["candidate_departures"] == pytest.approx(float(legs["flights"].sum()))


def load_seat_reference_from_frames() -> dict[tuple[str, str], dict]:
    key = list(zip(SEAT_REFERENCE["raw_model"], SEAT_REFERENCE["carrier_key"]))
    return {k: row._asdict() for k, row in zip(key, SEAT_REFERENCE.itertuples(index=False))}


def test_derive_reconciles_departures_with_capture_and_rejects_duplicates(tmp_path):
    silver = tmp_path / "silver"
    reference_dir = tmp_path / "reference"
    silver.mkdir()
    _write_reference(reference_dir)
    _flights([
        ("2026M04", "MEX", "MAD", "AEROMEXICO", "", "", "Aeromexico", "Boeing 737-800", "", 10.0, 0.0, 0.0),
        ("2026M04", "MAD", "MEX", "AEROMEXICO", "", "", "Aeromexico", "Boeing 737-800", "", 8.0, 0.0, 0.0),
    ]).to_parquet(silver / "aerodatabox_international_flights_2026M04_nucleo.parquet", index=False)
    _flights([
        ("2026M04", "MEX", "BOG", "AEROMEXICO_CONNECT", "", "", "Aeromexico Connect", "Embraer 190", "", 5.0, 0.0, 0.0),
    ]).to_parquet(silver / "aerodatabox_international_flights_2026M04_resto.parquet", index=False)

    frame, reports = derive(["2026M04"], silver_dir=silver, reference_dir=reference_dir)

    assert not frame.duplicated(["period_id", "origin_iata", "destination_iata", "carrier_key"]).any()
    assert list(frame.columns) == list(OUTPUT_COLUMNS)
    # Every mapped route here reconciles departures_estimated with the raw
    # captured flights: no day-weighting or scaling happens in this module,
    # the sweep's "flights" column already carries the month-scaled weight.
    by_route = frame.set_index(["origin_iata", "destination_iata", "carrier_key"])
    assert by_route.loc[("MEX", "MAD", "AEROMEXICO"), "departures_estimated"] == pytest.approx(10.0)
    assert by_route.loc[("MAD", "MEX", "AEROMEXICO"), "departures_estimated"] == pytest.approx(8.0)
    assert by_route.loc[("MEX", "BOG", "AEROMEXICO_CONNECT"), "departures_estimated"] == pytest.approx(5.0)
    assert reports[0]["period_id"] == "2026M04"
    assert reports[0]["aircraft_model_coverage"] == pytest.approx(1.0)


def test_duplicate_reference_row_is_rejected(tmp_path):
    reference_dir = tmp_path / "reference"
    reference_dir.mkdir(parents=True)
    bad = pd.concat([SEAT_REFERENCE, SEAT_REFERENCE.iloc[[0]]], ignore_index=True)
    bad.to_csv(reference_dir / "aeromexico_aircraft_seat_capacity.csv", index=False)
    with pytest.raises(ValueError, match="duplicate"):
        load_seat_reference(reference_dir)
