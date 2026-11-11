"""A disputed summary price is masked until an individual final-cart audit."""

import hashlib
import json

import pytest

from src.fare_quotes.__main__ import _apply_field_review, rebuild
from src.fare_quotes.aggregate import build_averages
from src.fare_quotes.normalize import canonical_row
from tests.test_fare_quotes import quote, snapshot


@pytest.fixture
def audit(tmp_path):
    bronze = tmp_path / "fare_quotes"
    bronze.mkdir()
    source = snapshot(quote(capture_key="one", fare="Zero", conditions="adulto; redondo; sin extras"))
    source["values"][1][source["values"][0].index("cash_final_mxn")] = 4611
    raw = json.dumps(source).encode()
    (bronze / "first.json").write_bytes(raw)
    source["fetched_at"] = "2026-11-11T06:00:00Z"
    repeated = json.dumps(source).encode()
    (bronze / "second.json").write_bytes(repeated)
    reviews = tmp_path / "fare_quote_field_reviews"
    reviews.mkdir()
    mask = {
        "schema_version": "fare_quote_field_review_v1",
        "provider": "DOTERS", "capture_id": "one",
        "source_snapshot_sha256": hashlib.sha256(raw).hexdigest(),
        "reviewed_at": "2026-11-10T23:00:00-06:00",
        "effective_overrides": {"cash_final_mxn": None},
        "reason": "Summary included a login-dependent discount; final cart unaudited",
    }
    (reviews / "pending.json").write_text(json.dumps(mask))

    def run():
        return rebuild(bronze, tmp_path / "silver", tmp_path / "gold.json")

    correction = {
        **mask, "reviewed_at": "2026-11-11T00:05:00-06:00",
        "effective_overrides": {}, "verified": True,
        "observed_correction": {"cash_final_mxn": 4731},
        "correction_evidence": {
            "verified": True, "observed_at": "2026-11-10T23:10:00-06:00",
            "evidence_url": "https://example.test/final-cart",
            "dom_sha256": "a" * 64,
        },
    }
    return tmp_path, bronze, reviews, raw, repeated, correction, run


def test_cash_mask_keeps_points_and_individual_audit_restores_only_observed_price(audit):
    _, bronze, reviews, raw, repeated, correction, run = audit
    masked = run()
    assert masked["quarantine_count"] == 0 and len(masked["rows"]) == 1
    row = masked["rows"][0]
    assert row["cash_final_mxn"] is None and row["points"] == 14398
    assert len(row["sources"]) == 2
    assert masked["counts"]["DOTERS"]["verified_cash"] == 0
    group = build_averages(masked)["groups"][0]
    assert group["metrics"]["cash_final_mxn"] == {"mean": None, "n": 0}
    assert group["metrics"]["points"] == {"mean": 14398, "n": 1}
    assert group["paired_cash_points"] == 0
    (reviews / "audited.json").write_text(json.dumps(correction))
    corrected = run()
    assert len(corrected["rows"]) == 1 and corrected["quarantine_count"] == 0
    row = corrected["rows"][0]
    assert row["cash_final_mxn"] == 4731 and row["points"] == 14398
    assert row["field_review"] == correction and len(row["sources"]) == 2
    assert corrected["counts"]["DOTERS"]["verified_cash"] == 1
    group = build_averages(corrected)["groups"][0]
    assert group["metrics"]["cash_final_mxn"] == {"mean": 4731, "n": 1}
    assert group["paired_cash_points"] == 1
    assert (bronze / "first.json").read_bytes() == raw
    assert (bronze / "second.json").read_bytes() == repeated


def test_unrelated_later_review_cannot_resurrect_a_masked_cash_price(audit):
    _, _, reviews, _, _, correction, run = audit
    later = {**correction, "effective_overrides": {"points": 14400}}
    del later["observed_correction"]
    del later["correction_evidence"]
    (reviews / "points-only.json").write_text(json.dumps(later))
    result = run()
    row = result["rows"][0]
    assert row["points"] == 14400 and row["cash_final_mxn"] is None
    assert len(row["field_review_history"]) == 2
    assert result["counts"]["DOTERS"]["verified_cash"] == 0


@pytest.mark.parametrize("query_date,observed_at,accepted", [
    ("2026-11-10", "2026-11-11T05:59:59Z", True),
    ("2026-11-10", "2026-11-11T06:00:00Z", False),
    ("2026-12-31", "2027-01-01T05:59:59Z", True),
    ("2026-12-31", "2027-01-01T06:00:00Z", False),
])
def test_cash_correction_uses_exact_mexico_date_including_quarter_boundary(audit, query_date, observed_at, accepted):
    _, _, _, _, _, review, _ = audit
    raw = quote()
    raw.update(query_date=query_date, departure_date="2027-02-01", return_date="2027-02-08")
    row = canonical_row(raw, "DOTERS")
    review["correction_evidence"]["observed_at"] = observed_at
    if accepted:
        _apply_field_review(row, review)
        assert row["cash_final_mxn"] == 4731
    else:
        with pytest.raises(ValueError, match="capture a new observation"):
            _apply_field_review(row, review)


@pytest.mark.parametrize("query_date,observed_at,accepted", [
    ("2026-11-10", "2026-11-11T05:59:59Z", True),
    ("2026-11-10", "2026-11-11T06:00:00Z", False),
    ("2026-12-31", "2027-01-01T05:59:59Z", True),
    ("2026-12-31", "2027-01-01T06:00:00Z", False),
])
def test_redemption_supplement_uses_same_mexico_query_date(query_date, observed_at, accepted):
    raw = quote()
    raw.update(query_date=query_date, departure_date="2027-02-01", return_date="2027-02-08",
               capture_key="FCO1-Main", cash_final_mxn=36995.26, points=242400, redemption_taxes_mxn=2298.29)
    row = canonical_row(raw, "AMR")
    review = {
        "effective_overrides": {}, "verified": True,
        "observed_supplement": {"redemption_cash_mxn": 2313.29, "redemption_carrier_mxn": 15},
        "supplement_evidence": {"observed_at": observed_at, "evidence_url": "https://example.test/retained-dom",
                                "dom_sha256": "a" * 64, "verified": True},
    }
    if accepted:
        _apply_field_review(row, review)
        assert row["redemption_cash_mxn"] == 2313.29 and row["redemption_carrier_mxn"] == 15
        assert row["points"] == 242400 and row["redemption_taxes_mxn"] == 2298.29
    else:
        with pytest.raises(ValueError, match="capture a new observation"):
            _apply_field_review(row, review)


@pytest.mark.parametrize("change", [
    "unverified_review", "unverified_evidence", "no_evidence", "naive_time",
    "no_dom_hash", "wrong_source", "other_field", "null_amount", "direct_override",
])
def test_cash_replacement_requires_exact_source_and_observed_verified_evidence(audit, change):
    _, _, reviews, _, _, correction, run = audit
    if change == "unverified_review":
        correction["verified"] = False
    elif change == "unverified_evidence":
        correction["correction_evidence"]["verified"] = False
    elif change == "no_evidence":
        del correction["correction_evidence"]
    elif change == "naive_time":
        correction["correction_evidence"]["observed_at"] = "2026-11-11T00:00:00"
    elif change == "no_dom_hash":
        del correction["correction_evidence"]["dom_sha256"]
    elif change == "wrong_source":
        correction["source_snapshot_sha256"] = "0" * 64
    elif change == "other_field":
        correction["observed_correction"]["points"] = 100
    elif change == "null_amount":
        correction["observed_correction"]["cash_final_mxn"] = None
    else:
        correction["effective_overrides"]["cash_final_mxn"] = 4731
    (reviews / "audited.json").write_text(json.dumps(correction))
    with pytest.raises(ValueError):
        run()
