"""Synthetic-only entity lifecycle isolation; never writes real approvals."""

import json
import sqlite3
import sys
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from test_stage16_analyst import inputs  # noqa: F401 -- pytest fixture dependency as inputs
from test_stage17_lifecycle import case as case
from test_stage17_lifecycle import fresh

from src.analysis_agent import lifecycle as flow

REAL_VERIFIED_INPUTS = flow.verified_inputs
REAL_REQUIRE_PRESENTATION = flow.require_current_presentation


@pytest.fixture
def entity_case(case, monkeypatch):  # noqa: F811 -- injected pytest fixture
    old, _, _, root = case
    checks = flow.verified_inputs(old)[2]
    record = deepcopy(old)
    draft = record["draft"]
    draft.update(
        schema_version="entity_analyst_v1",
        entity_key="VOLARIS",
        period_label="2T26 (abril–junio de 2026)",
        cutoff_date="2026-10-13",
        selection_mode="retrospective",
        guidance_as_of="report_date",
    )
    draft["package_id"] = "VOLARIS_" + draft["period_id"] + "_" + "a" * 64
    draft["calculation_fingerprint"] = "b" * 64
    record["content_hash"] = flow.digest(draft)
    record["version"] = flow.digest({k: record[k] for k in ("draft", "prompt_version", "code_version")})
    record["analysis_id"] = "VOLARIS_" + draft["period_id"] + "_" + record["version"]
    monkeypatch.setattr(flow, "verified_inputs", lambda r: (None, None, checks))
    original_presentation = flow.require_current_presentation
    monkeypatch.setattr(
        flow,
        "require_current_presentation",
        lambda r: None if flow.is_entity_record(r) else original_presentation(r),
    )
    report = dict(
        entity_key="VOLARIS",
        period_id=draft["period_id"],
        version=record["version"],
        content_hash=record["content_hash"],
        reviewer="independent_codex_agent",
        reviewer_task="TEST ONLY / independent reviewer",
        model=None,
        model_unavailable_reason="Synthetic fixture only",
        package_id=draft["package_id"],
        calculation_fingerprint=draft["calculation_fingerprint"],
        reviewed_claim_ids=[c["claim_id"] for c in draft["claims"]],
        decision="pass",
        findings=[],
        checks=[dict(key=k, result="pass", detail="Synthetic check") for k in sorted(flow.CHECKS)],
    )
    consent = dict(
        entity_key="VOLARIS",
        period_id=draft["period_id"],
        decision="approve_analysis",
        version=record["version"],
        content_hash=record["content_hash"],
        human_name="TEST ONLY",
        verbatim_message="Synthetic authorization only, not a user approval.",
        conversation_reference="pytest entity consent",
        authorized_at=datetime.now(timezone.utc).isoformat(),
    )
    return record, report, consent, root, old


def test_entity_identity_and_legacy_identity(entity_case):
    r, _, _, _, old = entity_case
    flow.verify_record(r)
    flow.verify_record(old)
    assert flow.record_identity(r)[:2] == ("VOLARIS", r["draft"]["period_id"])
    assert flow.record_identity(old)[0] == "AEROMEXICO"
    r["analysis_id"] = r["draft"]["period_id"] + "_" + r["version"]
    with pytest.raises(ValueError, match="Version identity"):
        flow.verify_record(r)


@pytest.mark.parametrize("reference_kind", ["audit", "authorization"])
@pytest.mark.parametrize("mutation", ["wrong_entity", "missing_entity", "wrong_period"])
def test_cross_entity_or_period_references_rejected(entity_case, reference_kind, mutation):
    r, a, h, root, _ = entity_case
    reference = a if reference_kind == "audit" else h
    if mutation == "wrong_entity":
        reference["entity_key"] = "VIVA"
    elif mutation == "missing_entity":
        reference.pop("entity_key")
    else:
        reference["period_id"] = "2025Q2"
    check = flow.audit_contract if reference_kind == "audit" else flow.check_authorization
    with pytest.raises(ValueError, match="identity mismatch"):
        check(reference, r)
    assert flow.events(root) == []


def test_legacy_explicit_wrong_entity_also_rejected(case):
    r, a, h, _ = case
    a["entity_key"] = h["entity_key"] = "VOLARIS"
    with pytest.raises(ValueError, match="entity"):
        flow.audit_contract(a, r)
    with pytest.raises(ValueError, match="entity"):
        flow.check_authorization(h, r)


def test_pending_entity_consent_then_audit_approval_and_revocation(entity_case):
    r, a, h, root, _ = entity_case
    flow.request_publication(r, h, root)
    with pytest.raises(ValueError, match="passing independent"):
        flow.approve(r, h, root)
    flow.record_audit(r, a, root)
    approval = flow.approve(r, h, root)
    payload = flow.consumer_payload(r, root)
    assert approval["entity_key"] == payload["entity_key"] == "VOLARIS"
    assert payload["selection_mode"] == "retrospective"
    assert "verbatim_message" not in json.dumps(payload)
    flow.revoke(r, "TEST ONLY withdrawal", "TEST ONLY", root)
    with pytest.raises(ValueError):
        flow.verify_handoff(payload, r, root)
    with pytest.raises(ValueError):
        flow.approve(r, fresh(h), root)
    h["conversation_reference"] = "pytest new consent"
    flow.approve(r, fresh(h), root)
    assert flow.state(r, root)["state"] == "approved"


@pytest.mark.parametrize("invalidation", ["revoke", "failed_audit"])
def test_pending_entity_request_invalidated(entity_case, invalidation):
    r, a, h, root, _ = entity_case
    flow.request_publication(r, h, root)
    if invalidation == "revoke":
        flow.revoke(r, "TEST withdrawal", "TEST", root)
    else:
        bad = deepcopy(a)
        bad["decision"] = "changes_requested"
        flow.record_audit(r, bad, root)
    flow.record_audit(r, a, root)
    with pytest.raises(ValueError, match="Fresh human consent"):
        flow.approve(r, h, root)


def test_same_version_cannot_share_state_or_deduplicate_between_entities_or_periods(entity_case, monkeypatch):
    r, a, _, root, old = entity_case
    # Force a version collision to exercise ledger indexing, independent of digest uniqueness.
    monkeypatch.setattr(flow, "verify_record", lambda record: None)
    other = deepcopy(r)
    other["draft"]["entity_key"] = "VIVA"
    another_period = deepcopy(r)
    another_period["draft"]["period_id"] = "2026Q1"
    same_payload = {"text": "Synthetic same comment"}
    first = flow.append("comment", r, same_payload, "TEST", root)
    second = flow.append("comment", other, same_payload, "TEST", root)
    third = flow.append("comment", another_period, same_payload, "TEST", root)
    assert len({first["event_hash"], second["event_hash"], third["event_hash"]}) == 3
    flow.record_audit(r, a, root)
    assert flow.state(r, root)["state"] == "validated"
    assert flow.state(other, root)["state"] == "draft"
    assert flow.state(another_period, root)["state"] == "draft"
    flow.revoke(other, "Synthetic revoke", "TEST", root)
    assert flow.state(r, root)["state"] == "validated"
    assert len(flow.state(r, root)["events"]) == 2


def test_mixed_sql_rebuild_preserves_legacy_events_and_adds_identity(entity_case):
    r, a, _, root, old = entity_case
    legacy = flow.comment(old, "Synthetic legacy comment", "TEST", root)
    assert "entity_key" not in legacy
    before = next((root / "events").glob("*.json")).read_bytes()
    flow.record_audit(r, a, root)
    dbpath = flow.rebuild_projection([old, r], root)
    with sqlite3.connect(dbpath) as db:
        assert set(db.execute("SELECT entity_key, state FROM fact_quarterly_analysis")) == {
            ("AEROMEXICO", "draft"),
            ("VOLARIS", "validated"),
        }
        assert list(db.execute("SELECT entity_key FROM analysis_events ORDER BY sequence")) == [
            ("AEROMEXICO",),
            ("VOLARIS",),
        ]
    assert sorted((root / "events").glob("*.json"))[0].read_bytes() == before
    assert flow.events(root)[0] == legacy


def test_entity_consumption_still_holds_lock_against_revocation(entity_case):
    r, a, h, root, _ = entity_case
    flow.record_audit(r, a, root)
    flow.approve(r, fresh(h), root)
    with flow.authorized_consumption(r, root):
        with pytest.raises(ValueError, match="Ledger busy"):
            flow.revoke(r, "Race", "TEST", root)


def test_verify_input_paths_entity_bound_and_legacy_bound(entity_case, monkeypatch):
    r, _, _, _, old = entity_case
    calls = []
    entity_calls = []

    def entity_inputs(record):
        entity_calls.append(record)
        return {}, {}, {}

    monkeypatch.setitem(
        sys.modules, "src.analysis_agent.entity_adapter", SimpleNamespace(verified_inputs=entity_inputs)
    )
    monkeypatch.setattr(flow, "load_inputs", lambda p, c: (calls.append((p, c)) or {}, {}))
    monkeypatch.setattr(flow, "validate", lambda *args: {})
    monkeypatch.setattr(flow, "verified_inputs", REAL_VERIFIED_INPUTS)
    verify = flow.verified_inputs
    old = deepcopy(old)
    old["draft"]["package_id"] = old["draft"]["period_id"] + "_" + "a" * 64
    old["draft"]["calculation_fingerprint"] = "b" * 64
    old["content_hash"] = flow.digest(old["draft"])
    old["version"] = flow.digest({k: old[k] for k in ("draft", "prompt_version", "code_version")})
    old["analysis_id"] = old["draft"]["period_id"] + "_" + old["version"]
    verify(r)
    verify(old)
    assert entity_calls == [r]
    assert calls[0][0].name.startswith("2026Q2_")
    bad = deepcopy(r)
    bad["draft"]["package_id"] = "VIVA_" + old["draft"]["package_id"]
    bad["content_hash"] = flow.digest(bad["draft"])
    bad["version"] = flow.digest({k: bad[k] for k in ("draft", "prompt_version", "code_version")})
    bad["analysis_id"] = "VOLARIS_" + bad["draft"]["period_id"] + "_" + bad["version"]
    with pytest.raises(ValueError, match="Invalid input identity"):
        verify(bad)
    assert len(calls) == len(entity_calls) == 1


def test_entity_presentation_dispatch(entity_case, monkeypatch):
    r, _, _, _, _ = entity_case
    invoked = []
    monkeypatch.setitem(
        sys.modules,
        "src.analysis_agent.entity_adapter",
        SimpleNamespace(require_current_presentation=lambda record: invoked.append(record)),
    )
    monkeypatch.setattr(flow, "require_current_presentation", REAL_REQUIRE_PRESENTATION)
    flow.require_current_presentation(r)
    assert invoked == [r]


@pytest.mark.parametrize(
    "field,value",
    [
        ("entity_key", "../private"),
        ("entity_key", None),
        ("period_id", "../2026Q2"),
        ("version", "../secret"),
    ],
)
def test_hash_valid_but_unsafe_ledger_identity_rejected(entity_case, field, value):
    r, _, _, root, _ = entity_case
    event = flow.comment(r, "Synthetic comment", "TEST", root)
    event[field] = value
    event["event_hash"] = flow.digest({k: v for k, v in event.items() if k != "event_hash"})
    original = next((root / "events").glob("*.json"))
    original.unlink()
    flow.atomic_json(root / "events" / f"00000001_{event['event_hash']}.json", event)
    flow.advance_head(root, event)
    with pytest.raises(ValueError, match="Invalid ledger event identity"):
        flow.events(root)


def test_sql_projection_allows_same_version_across_entities(entity_case, monkeypatch):
    r, _, _, root, _ = entity_case
    other = deepcopy(r)
    other["draft"]["entity_key"] = "VIVA"
    other["analysis_id"] = "VIVA_" + other["draft"]["period_id"] + "_" + other["version"]
    monkeypatch.setattr(flow, "verify_record", lambda record: None)
    path = flow.rebuild_projection([r, other], root)
    with sqlite3.connect(path) as db:
        rows = list(db.execute("SELECT entity_key, version FROM fact_quarterly_analysis ORDER BY entity_key"))
    assert rows == [("VIVA", r["version"]), ("VOLARIS", r["version"])]
