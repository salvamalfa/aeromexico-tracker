"""Closed evidence contracts accept the approved corpus, never grant authority."""

import copy
import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from src.conversational_analytics.evidence_index import (
    APPROVED_INDEX_SHA256_ENV,
    EvidenceIndex,
    canonical_index_sha256,
)

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "config/chat/evidence/approved-index.json"
CANONICAL_SHA = "9f8f12fc088cefce09f822d6647f5b46856e6ee7b600c5a1750db0c3e5f07005"
RAW_SHA = "b9980be0fbd456fc50fce482b03377b69f4faae92d0b96f1d217ad3a85451356"


def validator():
    schema = json.loads((ROOT / "contracts/chat/evidence-index.schema.json").read_bytes())
    Draft202012Validator.check_schema(schema)
    checker = FormatChecker()

    # Some installations omit the optional RFC3339 format dependency. Keep
    # calendar/timezone validation explicit rather than silently ignoring it.
    @checker.checks("date-time", raises=(TypeError, ValueError))
    def date_time(value):
        if not isinstance(value, str):
            return True
        return datetime.fromisoformat(value.replace("Z", "+00:00")).utcoffset() is not None

    return Draft202012Validator(schema, format_checker=checker)


def editorial_index():
    payload = json.loads(INDEX.read_bytes())
    payload["records"] = [next(r for r in payload["records"] if "publisher_observations" in r)]
    return payload


def replace(payload, path, value):
    target = payload["records"][0]
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def test_all_33_approved_records_and_legacy_fixture_keep_their_exact_bytes(monkeypatch):
    raw = INDEX.read_bytes()
    payload = json.loads(raw)
    assert hashlib.sha256(raw).hexdigest() == RAW_SHA
    assert canonical_index_sha256(payload) == CANONICAL_SHA
    assert len(payload["records"]) == 33
    assert sum(r["kind"] == "report" for r in payload["records"]) == 7
    assert sum("publisher_observations" in r for r in payload["records"]) == 23
    validator().validate(payload)
    legacy = json.loads((ROOT / "tests/fixtures/chat_evidence/index.json").read_bytes())
    legacy["records"] = [r for r in legacy["records"] if r["review"]["decision"] == "owner_approved"]
    validator().validate(legacy)
    monkeypatch.setenv(APPROVED_INDEX_SHA256_ENV, CANONICAL_SHA)
    assert len(EvidenceIndex(INDEX).records) == 33
    assert INDEX.read_bytes() == raw


@pytest.mark.parametrize(
    "path",
    [(), ("source",), ("review",), ("review", "receipt"), ("publisher_observations", 0)],
)
def test_unknown_properties_remain_closed_at_every_editorial_level(path):
    payload = editorial_index()
    target = payload["records"][0]
    for key in path:
        target = target[key]
    target["unreviewed_extension"] = "not approved"
    assert not validator().is_valid(payload)


@pytest.mark.parametrize(
    "path,value",
    [
        (("source", "sha256"), "a" * 63),
        (("review", "receipt", "proposal_sha256"), "g" * 64),
        (("review", "receipt", "source_sha256"), "A" * 64),
        (("published_at",), "2026-02-30"),
        (("first_reported_on",), "02/11/2026"),
        (("event_date",), "2026-13-01"),
        (("first_captured_at",), "2026-11-02T00:25:45"),
        (("event_first_observed_at",), "2026-02-30T00:25:45Z"),
        (("publisher_observations", 0, "observed_at"), "yesterday"),
        (("publisher_observations", 0, "published_on"), "2026-11-31"),
        (("publisher_observations", 0, "event_end_date"), "not a date"),
        (("review", "receipt", "approved_at"), "2026-11-02"),
        (("source", "json_pointer"), "/../../secret"),
        (("source", "artifact_file"), "unreviewed.json"),
        (("publication_precision",), "timestamp"),
        (("publication_date_basis",), "invented_UTC_timestamp"),
        (("first_capture_scope",), "first_publisher_availability"),
        (("summary_kind",), "publisher_verbatim_article"),
        (("source", "sha256_semantics"), "original_publisher_bytes"),
        (("publisher_observations", 0, "method"), "unverified_fetch"),
        (("publisher_observations", 0, "source_kind"), "invented"),
        (("publisher_observations", 0, "representation"), "original_publisher_bytes"),
        (("publisher_observations", 0, "original_page_sha256"), "a" * 64),
        (("publisher_observations", 0, "publisher_page_read"), False),
        (("publisher_observations",), []),
        (("kind",), "report"),
        (("review", "decision"), "pending"),
        (("review", "receipt", "decision"), "candidate"),
    ],
)
def test_malformed_or_misrepresented_editorial_evidence_is_rejected(path, value):
    payload = editorial_index()
    replace(payload, path, value)
    assert not validator().is_valid(payload)


@pytest.mark.parametrize(
    "path",
    [
        ("event_first_observed_at",), ("first_capture_scope",), ("first_reported_on",),
        ("impact_note",), ("publication_date_basis",), ("publication_precision",),
        ("publisher_observations",), ("summary_kind",),
        ("source", "artifact_file"), ("source", "json_pointer"), ("source", "sha256_semantics"),
        ("review", "receipt", "proposal_sha256"),
        ("publisher_observations", 0, "original_page_sha256"),
    ],
)
def test_editorial_provenance_cannot_be_partially_dropped(path):
    payload = editorial_index()
    target = payload["records"][0]
    for key in path[:-1]:
        target = target[key]
    del target[path[-1]]
    assert not validator().is_valid(payload)


@pytest.mark.parametrize("kind", ["report", "legacy_news"])
@pytest.mark.parametrize("location", ["record", "source", "receipt"])
def test_news_extension_does_not_open_reports_or_legacy_records(kind, location):
    payload = json.loads(INDEX.read_bytes())
    row = next(
        r for r in payload["records"]
        if (
            r["kind"] == "report" if kind == "report"
            else r["kind"] == "news" and "publisher_observations" not in r
        )
    )
    payload["records"] = [copy.deepcopy(row)]
    target = payload["records"][0]
    if location == "record":
        target["publication_precision"] = "day"
    elif location == "source":
        target["source"]["artifact_file"] = "candidates.json"
    else:
        target["review"]["receipt"]["proposal_sha256"] = "a" * 64
    assert not validator().is_valid(payload)


@pytest.mark.parametrize(
    "path,value",
    [
        (("description",), "An unapproved replacement summary."),
        (("review", "receipt", "candidate_id"), "another_record"),
        (("review", "owner_id"), "another_owner"),
    ],
)
def test_schema_compatibility_never_confers_approval(tmp_path, monkeypatch, path, value):
    payload = editorial_index()
    replace(payload, path, value)
    validator().validate(payload)  # Shape alone cannot establish exact authority.
    fixture = tmp_path / "unapproved-index.json"
    fixture.write_text(json.dumps(payload), encoding="utf-8")
    # Only this test fixture receives a new transport pin. The real pin and
    # the existing candidate/source/excerpt authority bindings remain unchanged.
    monkeypatch.setenv(APPROVED_INDEX_SHA256_ENV, canonical_index_sha256(payload))
    assert EvidenceIndex(fixture).records == []
