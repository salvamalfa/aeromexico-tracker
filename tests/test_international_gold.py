"""The dashboard bridge: AFAC city routes onto the airport pairs carriers fly."""

from __future__ import annotations

import pandas as pd
import pytest

from src.analytics.international_gold import ESTIMATE_BAND, build_gold

CITIES = pd.DataFrame(
    [("MEXICO", "Mexico", "MEX"), ("LONDRES", "Reino Unido", "LHR"),
     ("LONDRES", "Reino Unido", "LGW"), ("MONTERREY", "Mexico", "MTY")],
    columns=["afac_city", "afac_country", "airport_iata"],
)
CARRIERS = pd.DataFrame(
    [("Aeroméxico", "national", "AEROMEXICO", "AM", "AMX", "resolved", ""),
     ("British Airways", "foreign", "BRITISH_AIRWAYS", "BA", "BAW", "resolved", ""),
     ("Lacsa", "foreign", "LACSA", "LR", "LRC", "probable", "")],
    columns=["afac_carrier_name", "carrier_block", "carrier_key", "iata", "icao", "confidence", "evidence"],
)
FAMILIES = pd.DataFrame(columns=["carrier_key", "fit_key", "fit_label", "reason"])


def _capture(rows):
    return pd.DataFrame(rows, columns=["period_id", "origin_iata", "dest_iata", "operator_key",
                                       "operator_iata", "operator_icao", "flights"])


def _estimate(rows):
    frame = pd.DataFrame(rows, columns=["period_id", "route_key", "carrier_key", "passengers_estimated"])
    return frame.assign(is_single_operator_seed=False, is_pooled_family=False,
                        display_source="estimated", estimator_version="v")


def test_each_carrier_lands_on_the_airport_pair_it_was_seen_on() -> None:
    capture = _capture([
        ("2026M04", "MEX", "LHR", "AEROMEXICO", "AM", "AMX", 30.0),
        ("2026M04", "MEX", "LGW", "IATA:BA", "BA", "", 10.0),
        ("2026M04", "MEX", "LHR", "IATA:BA", "BA", "", 20.0),
    ])
    estimate = _estimate([
        ("2026M04", "MEXICO-LONDRES", "AEROMEXICO", 9_000.0),
        ("2026M04", "MEXICO-LONDRES", "BRITISH_AIRWAYS", 6_000.0),
        ("2026M04", "MEXICO-LONDRES", "AEROMEXICO_GROUP", 9_000.0),
        ("2026M04", "MEXICO-LONDRES", "SIN_ASIGNAR", 5.0),
    ])

    gold = build_gold(estimate, capture, CITIES, CARRIERS, FAMILIES).set_index("carrier_key")

    assert set(gold.index) == {"AEROMEXICO", "BRITISH_AIRWAYS"}  # no group or unallocated rows
    assert gold.loc["AEROMEXICO", "market_key"] == "LHR<>MEX"
    assert gold.loc["BRITISH_AIRWAYS", "destination_iata"] == "LHR"  # its busiest pair
    assert gold.loc["AEROMEXICO", "departures_estimated"] == 30.0
    assert gold.loc["AEROMEXICO", "passengers_estimated_low"] == pytest.approx(9_000 * (1 - ESTIMATE_BAND))
    assert gold.loc["AEROMEXICO", "passengers_estimated_high"] == pytest.approx(9_000 * (1 + ESTIMATE_BAND))


def test_a_through_flight_keeps_its_first_origin() -> None:
    """AM 58 is MEX-MTY-NRT; its MEXICO-TOKYO passengers belong on MEX<>NRT."""

    cities = pd.concat([CITIES, pd.DataFrame([("TOKYO", "Japon", "NRT")], columns=CITIES.columns)])
    capture = _capture([("2026M04", "MEX", "NRT", "AEROMEXICO", "AM", "AMX", 25.0)])
    estimate = _estimate([("2026M04", "MEXICO-TOKYO", "AEROMEXICO", 5_000.0)])

    gold = build_gold(estimate, capture, cities, CARRIERS, FAMILIES)

    assert gold["market_key"].tolist() == ["MEX<>NRT"]


def test_an_estimate_with_no_captured_pair_is_refused() -> None:
    estimate = _estimate([("2026M04", "MEXICO-LONDRES", "AEROMEXICO", 9_000.0)])

    with pytest.raises(ValueError, match="MEXICO-LONDRES"):
        build_gold(estimate, _capture([]), CITIES, CARRIERS, FAMILIES)
