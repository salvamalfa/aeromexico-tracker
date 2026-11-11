"""Independent examples for public means, comparison grain, privacy and nulls."""

import json

from src.fare_quotes.aggregate import build_averages
from src.fare_quotes.normalize import canonical_row
from src.web_export.fare_averages import export_fare_averages, validate_averages


def observation(**changes):
    row = dict(
        query_date="2026-11-10",
        origin="MEX",
        destination="MTY",
        departure_date="2026-12-10",
        return_date="2026-12-17",
        cash_final_mxn=100,
        points=1000,
        status="partial_redemption",
        fare="Main",
        conditions="Un adulto; misma tarifa; equipaje personal",
        evidence="https://example.test/private",
        outbound_flight="AM123",
    )
    row.update(changes)
    return canonical_row(row, row.pop("provider", "AMR"))


def private(*rows):
    return dict(schema_version="local_fare_quotes_v1", private=True, rows=list(rows))


def test_arithmetic_means_have_independent_denominators_and_no_invented_award_payment():
    value = build_averages(private(observation(), observation(cash_final_mxn=300, points=None)))
    group = value["groups"][0]
    assert group["metrics"]["cash_final_mxn"] == {"mean": 200, "n": 2}
    assert group["metrics"]["points"] == {"mean": 1000, "n": 1}
    assert group["paired_cash_points"] == 1
    assert group["metrics"]["redemption_cash_mxn"] == {"mean": None, "n": 0}
    validate_averages(value)


def test_fare_conditions_horizon_and_airports_are_never_blended():
    rows = [
        observation(),
        observation(fare="Premier"),
        observation(conditions="Incluye maleta"),
        observation(departure_date="2027-02-10", return_date="2027-02-17"),
        observation(origin="NLU"),
    ]
    value = build_averages(private(*rows))
    assert len(value["groups"]) == 5
    mexico = next(g for g in value["groups"] if g["origin"] == "MEX")
    aifa = next(g for g in value["groups"] if g["origin"] == "NLU")
    assert mexico["origin_map_id"] == "CITY_MX_MEXICO"
    assert aifa["origin_map_id"] == "CITY_MX_SANTA_LUCIA"


def test_unknown_conditions_and_unverified_history_do_not_enter_means():
    history = observation()
    history["status"] = "legacy_unverified"
    value = build_averages(private(history, observation(provider="DOTERS", conditions=None)))
    assert value["groups"] == []
    assert value["excluded_unverified_observations"] == 2


def test_unknown_fares_are_excluded_even_with_identical_documented_conditions():
    unknown = observation(fare=None, cash_final_mxn=300)
    blank = observation(fare="", cash_final_mxn=500)
    blank["fare"] = " \t "
    value = build_averages(private(observation(), unknown, blank))
    assert len(value["groups"]) == 1
    assert value["groups"][0]["fare"] == "Main"
    assert value["groups"][0]["observations"] == 1
    assert value["groups"][0]["metrics"]["cash_final_mxn"] == {"mean": 100, "n": 1}
    assert value["excluded_unverified_observations"] == 2


def test_public_export_contains_no_private_quote_identifiers_and_is_deterministic(tmp_path):
    a, b = observation(), observation(cash_final_mxn=300)
    a["sources"] = [{"spreadsheet_id": "do-not-publish-this", "row": 99}]
    target = export_fare_averages(private(a, b), tmp_path)
    raw = target.read_bytes()
    assert b"do-not-publish-this" not in raw
    assert b"AM123" not in raw
    assert b"example.test" not in raw
    assert b"captured_at" not in raw
    export_fare_averages(private(b, a), tmp_path)
    assert target.read_bytes() == raw


def test_volaris_public_points_remain_null_with_no_applicable_program():
    value = build_averages(private(observation(provider="VOLARIS", points=None, status="ok")))
    group = value["groups"][0]
    assert group["metrics"]["points"] == {"mean": None, "n": 0}
    assert group["points_applicability"] == "not_applicable"
    assert "No aplica" not in json.dumps(group["metrics"])  # text belongs to presentation, not numeric data
    validate_averages(value)
