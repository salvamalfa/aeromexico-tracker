"""Private quote replay keeps source history, null semantics, money boundaries and idempotence."""

from __future__ import annotations

import hashlib
import json

import pytest

from src.fare_quotes.__main__ import rebuild
from src.fare_quotes.normalize import canonical_row, decode_snapshot


def quote(**changes):
    return dict(
        query_date="2026-11-10",
        origin="MEX",
        destination="MTY",
        departure_date="2026-12-10",
        return_date="2026-12-17",
        cash_final_mxn=3107,
        points=14398,
        redemption_cash_mxn=None,
        redemption_taxes_mxn=1399,
        evidence_url="https://example.test/retained-checkout",
        status="partial_redemption",
        notes='{"award_carrier_cash":134}',
        **changes,
    )


def snapshot(row):
    return dict(
        provider="DOTERS",
        spreadsheet_id="test-book",
        sheet_name="Capturas_v2",
        range="A1:X2",
        fetched_at="2026-11-10T20:00:00Z",
        values=[list(row), list(row.values())],
    )


def test_partial_redemption_never_invents_a_final_payment():
    row = canonical_row(quote(), "DOTERS")
    assert row["cash_final_mxn"] == 3107
    assert row["points"] == 14398
    assert row["redemption_cash_mxn"] is None
    assert row["redemption_carrier_mxn"] == 134
    assert row["redemption_taxes_mxn"] == 1399


@pytest.mark.parametrize("provider", ["viva", "VIVA", " doters "])
def test_capture_workflow_provider_aliases_replay_without_changing_bronze(provider):
    source = snapshot(quote(provider=provider))
    rows, errors = decode_snapshot(source)
    assert not errors
    assert rows[0]["provider"] == "DOTERS"
    assert source["values"][1][-1] == provider


def test_provider_aliases_do_not_hide_a_different_or_unknown_airline():
    for provider in ("volaris", "unknown"):
        rows, errors = decode_snapshot(snapshot(quote(provider=provider)))
        assert not rows
        assert errors[0]["reason"] == "Row provider contradicts snapshot"


def test_legacy_amr_keeps_components_but_does_not_assert_cash_final():
    source = dict(
        provider="AMR",
        spreadsheet_id="old-book",
        sheet_name="Vuelos",
        range="A1:R2",
        fetched_at="2026-11-10T20:00:00Z",
        format="amr_legacy_v1",
        values=[
            ["historic headers"],
            [
                "10/11/2026",
                "MEX",
                "CUN",
                "10/12/2026",
                "17/12/2026",
                "05:30",
                "09:00",
                "Main",
                "No",
                20000,
                750,
                1200,
                900,
                0,
            ],
        ],
    )
    rows, errors = decode_snapshot(source)
    assert not errors
    assert rows[0]["cash_final_mxn"] is None
    assert rows[0]["cash_carrier_mxn"] == 1200
    assert rows[0]["cash_taxes_mxn"] == 900
    assert rows[0]["redemption_cash_mxn"] is None
    assert rows[0]["status"] == "legacy_unverified"


@pytest.mark.parametrize("points", [0, 100])
def test_volaris_rejects_even_zero_points(points):
    row = quote()
    row.update(points=points, status="ok")
    with pytest.raises(ValueError, match="Volaris points"):
        canonical_row(row, "VOLARIS")


def test_volaris_null_is_inapplicable_not_zero():
    row = quote()
    row.update(points=None, redemption_taxes_mxn=None, notes=None, status="ok")
    result = canonical_row(row, "VOLARIS")
    assert result["points"] is None
    assert result["points_applicability"] == "not_applicable"


def test_timezone_uses_mexico_date_not_snapshot_fetch_time():
    row = quote()
    row.update(captured_at="2026-11-11T02:00:00Z")
    assert canonical_row(row, "DOTERS")["query_date"] == "2026-11-10"
    row.update(query_date="2026-11-11")
    with pytest.raises(ValueError, match="disagrees"):
        canonical_row(row, "DOTERS")


def test_snapshot_replay_deduplicates_and_preserves_every_source(tmp_path):
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    source = snapshot(quote())
    raw = json.dumps(source)
    (bronze / "first.json").write_text(raw)
    source["fetched_at"] = "2026-11-11T20:00:00Z"
    (bronze / "second.json").write_text(json.dumps(source))
    payload = rebuild(bronze, tmp_path / "silver", tmp_path / "gold.json")
    assert len(payload["rows"]) == 1
    assert len(payload["rows"][0]["sources"]) == 2
    assert payload["counts"]["DOTERS"]["verified_cash"] == 1
    assert payload["counts"]["DOTERS"]["complete"] == 0
    assert (bronze / "first.json").read_text() == raw


def test_conflicting_capture_id_quarantines_both_versions(tmp_path):
    bronze = tmp_path / "bronze"
    bronze.mkdir()
    for index, final in enumerate([3107, 3500]):
        row = quote()
        row.update(capture_key="same-capture", cash_final_mxn=final)
        (bronze / f"{index}.json").write_text(json.dumps(snapshot(row)))
    payload = rebuild(bronze, tmp_path / "silver", tmp_path / "gold.json")
    assert payload["rows"] == []
    assert payload["quarantine_count"] == 2


def test_valid_rows_survive_invalid_row_quarantine():
    source = snapshot(quote())
    invalid = list(source["values"][1])
    invalid[source["values"][0].index("cash_final_mxn")] = "3.107,00"
    source["values"].append(invalid)
    rows, errors = decode_snapshot(source)
    assert len(rows) == len(errors) == 1
    assert errors[0]["source"]["row"] == 3


def test_alternate_airport_url_needs_selected_flight_summary():
    row = quote()
    row.update(
        evidence_url="https://example.test/?itineraryCode=NLU_MTY_20261210&alternateStations=1001",
        outbound_flight="VB1120",
        return_flight="VB1117",
    )
    with pytest.raises(ValueError, match="selected flight summary"):
        canonical_row(row, "DOTERS")
    verification = dict(
        basis="selected_flight_summary",
        origin="MEX",
        destination="MTY",
        outbound_flight="VB1120",
        return_flight="VB1117",
    )
    assert canonical_row(row, "DOTERS", verification=verification)["origin"] == "MEX"


def test_complete_loyalty_result_requires_final_redemption_payment():
    row = quote()
    row["status"] = "ok"
    with pytest.raises(ValueError, match="final redemption payment"):
        canonical_row(row, "DOTERS")


def test_field_review_excludes_only_unconfirmed_fields_and_keeps_bronze(tmp_path):
    bronze = tmp_path / "fare_quotes"
    bronze.mkdir()
    source = snapshot(quote(capture_key="one"))
    raw = json.dumps(source).encode()
    (bronze / "source.json").write_bytes(raw)
    reviews = tmp_path / "fare_quote_field_reviews"
    reviews.mkdir()
    review = dict(
        schema_version="fare_quote_field_review_v1",
        provider="DOTERS",
        capture_id="one",
        source_snapshot_sha256=hashlib.sha256(raw).hexdigest(),
        reviewed_at="2026-11-10T23:00:00-06:00",
        effective_overrides=dict(points=None, redemption_taxes_mxn=None),
        reason="Loading in source",
    )
    (reviews / "initial.json").write_text(json.dumps(review))
    result = rebuild(bronze, tmp_path / "silver", tmp_path / "gold.json")
    assert result["rows"][0]["cash_final_mxn"] == 3107
    assert result["rows"][0]["points"] is None
    assert result["rows"][0]["redemption_taxes_mxn"] is None
    assert (bronze / "source.json").read_bytes() == raw
    review["source_snapshot_sha256"] = "0" * 64
    (reviews / "initial.json").write_text(json.dumps(review))
    with pytest.raises(ValueError, match="fingerprint"):
        rebuild(bronze, tmp_path / "silver", tmp_path / "gold.json")


def test_repeated_sheet_read_keeps_one_effectively_reviewed_observation_and_all_sources(tmp_path):
    bronze = tmp_path / "fare_quotes"
    bronze.mkdir()
    first = snapshot(quote(capture_key="one"))
    original_bytes = json.dumps(first).encode()
    (bronze / "z-original.json").write_bytes(original_bytes)
    repeated = json.loads(original_bytes)
    repeated["fetched_at"] = "2026-11-11T20:00:00Z"
    other = quote(capture_key="two")
    other["destination"] = "CUN"
    repeated["values"].append(list(other.values()))
    repeated_bytes = json.dumps(repeated).encode()
    (bronze / "a-repeated.json").write_bytes(repeated_bytes)
    reviews = tmp_path / "fare_quote_field_reviews"
    reviews.mkdir()
    initial = dict(
        schema_version="fare_quote_field_review_v1",
        provider="DOTERS",
        capture_id="one",
        source_snapshot_sha256=hashlib.sha256(original_bytes).hexdigest(),
        reviewed_at="2026-11-10T23:00:00-06:00",
        effective_overrides=dict(points=None, redemption_taxes_mxn=None),
    )
    (reviews / "initial.json").write_text(json.dumps(initial))
    result = rebuild(bronze, tmp_path / "silver", tmp_path / "gold.json")
    reviewed = next(row for row in result["rows"] if row["capture_id"] == "one")
    assert len(result["rows"]) == 2
    assert result["quarantine_count"] == 0
    assert reviewed["cash_final_mxn"] == 3107
    assert reviewed["points"] is None and reviewed["redemption_taxes_mxn"] is None
    assert {s["snapshot_sha256"] for s in reviewed["sources"]} == {
        hashlib.sha256(original_bytes).hexdigest(),
        hashlib.sha256(repeated_bytes).hexdigest(),
    }
    assert len(reviewed["sources"]) == 2
    confirmed = {
        **initial,
        "source_snapshot_sha256": hashlib.sha256(repeated_bytes).hexdigest(),
        "reviewed_at": "2026-11-10T23:05:00-06:00",
        "effective_overrides": dict(points=14398, redemption_taxes_mxn=1399),
    }
    (reviews / "confirmed.json").write_text(json.dumps(confirmed))
    result = rebuild(bronze, tmp_path / "silver", tmp_path / "gold.json")
    reviewed = next(row for row in result["rows"] if row["capture_id"] == "one")
    assert len(result["rows"]) == 2 and result["quarantine_count"] == 0
    assert reviewed["points"] == 14398 and reviewed["redemption_taxes_mxn"] == 1399
    assert reviewed["field_review"] == confirmed and len(reviewed["sources"]) == 2
    assert result["counts"]["DOTERS"]["verified_cash"] == 2
    assert (bronze / "z-original.json").read_bytes() == original_bytes
    assert (bronze / "a-repeated.json").read_bytes() == repeated_bytes
