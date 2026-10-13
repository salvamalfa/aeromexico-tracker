"""Synthetic gate consumption receipts preserve exact multi-entity approvals."""

import copy
import json
import shutil
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from test_stage16_analyst import inputs as inputs  # noqa: F401 -- pytest fixture
from test_stage17_lifecycle import case as case  # noqa: F401 -- pytest fixture

from src.analysis_agent import lifecycle as flow
from src.publish import gate
from src.publish import manifest as manifest_mod


def test_four_record_gate_receipt_keeps_shuffled_approval_pairs_and_publication_state(
    case, inputs, monkeypatch, tmp_path
):
    legacy, original_report, original_consent, root = case
    _, package, calculations = inputs
    checks = flow.verified_inputs(legacy)[2]
    instant = datetime.now(timezone.utc)

    class Clock(datetime):
        current = instant

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz else cls.current.replace(tzinfo=None)

    monkeypatch.setattr(flow, "datetime", Clock)
    presentation = flow.require_current_presentation
    monkeypatch.setattr(
        flow,
        "require_current_presentation",
        lambda record: None if flow.is_entity_record(record) else presentation(record),
    )
    monkeypatch.setattr(
        flow,
        "verified_inputs",
        lambda record: (
            {**package, "schema_version": "entity_evidence_v1", "entity_key": flow.entity_key(record)}
            if flow.is_entity_record(record)
            else package,
            calculations,
            checks,
        ),
    )
    records = [legacy]
    for entity in ["INDUSTRY", "VIVA_AEROBUS", "VOLARIS"]:
        record = copy.deepcopy(legacy)
        record["draft"].update(
            schema_version="entity_analyst_v1",
            entity_key=entity,
            period_label="2T26",
            cutoff_date="2026-10-13",
            selection_mode="retrospective",
            guidance_as_of="report_date",
        )
        record["content_hash"] = flow.digest(record["draft"])
        record["version"] = flow.digest({k: record[k] for k in ("draft", "prompt_version", "code_version")})
        record["analysis_id"] = entity + "_2026Q2_" + record["version"]
        records.append(record)
    paths, authorized = [], []
    for index, record in enumerate(sorted(records, key=lambda record: record["version"])):
        entity = flow.entity_key(record)
        report = original_report | {"version": record["version"], "content_hash": record["content_hash"]}
        consent = original_consent | {
            "version": record["version"],
            "content_hash": record["content_hash"],
            "authorized_at": (instant - timedelta(seconds=1)).isoformat(),
        }
        if flow.is_entity_record(record):
            report = report | {"entity_key": entity, "period_id": "2026Q2"}
            consent = consent | {"entity_key": entity, "period_id": "2026Q2"}
        Clock.current = instant - timedelta(seconds=2)
        audit = flow.record_audit(record, report, root)
        Clock.current = instant
        # Select a genuine consent nonce whose SHA ordering opposes the
        # version ordering; audit, approval and event replay remain real.
        history = flow.events(root)
        for nonce in range(4096):
            consent["conversation_reference"] = f"TEST ONLY {entity} receipt association {nonce}"
            event = dict(
                action="approval",
                version=record["version"],
                period_id="2026Q2",
                payload={"authorization": consent, "audit_hash": audit["payload"]["audit_hash"]},
                actor=consent["human_name"],
                sequence=len(history) + 1,
                previous_hash=history[-1]["event_hash"],
                created_at=instant.isoformat(),
            )
            if flow.is_entity_record(record):
                event["entity_key"] = entity
            if flow.digest(event).startswith("fb73"[index]):
                break
        else:
            pytest.fail("Could not construct the adversarial synthetic approval ordering")
        approval = flow.approve(record, consent, root)
        assert approval["event_hash"].startswith("fb73"[index])
        authorized.append(flow.consumer_payload(record, root))
        path = tmp_path / f"{entity}.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        paths.append(path)
        assert flow.state(record, root)["state"] == "approved"

    expected_pairs = sorted((entry["version"], entry["approval_event"]) for entry in authorized)
    assert [approval for _, approval in expected_pairs] != sorted(approval for _, approval in expected_pairs)
    monkeypatch.setattr(gate, "PATHS", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(manifest_mod, "refuse_if_build_inputs_dirty", lambda: None)
    monkeypatch.setattr(manifest_mod, "current_commit", lambda: "a" * 40)
    for name in ["build_flight_payload", "build_executive_payload", "build_market_payload"]:
        monkeypatch.setattr(gate, name, lambda: {})
    for name in ["export_flights", "export_executive", "export_market"]:
        monkeypatch.setattr(gate, name, lambda *args: None)
    web_data = tmp_path / "web/public/data/v1"

    def build_web(web_dir):
        dist = tmp_path / "dist"
        shutil.copytree(web_data, dist / "data/v1")
        (dist / "index.html").write_text("TEST ONLY local generated site", encoding="utf-8")
        return dist

    monkeypatch.setattr(gate, "build_web", build_web)
    site = tmp_path / "site"
    result = gate.publish(paths[::-1], site, root=root, web_data_v1=web_data)
    assert list(zip(result["receipt"]["versions"], result["receipt"]["approval_events"])) == expected_pairs
    assert result["receipt"]["output"] == str(site)
    identities = result["receipt"]["analysis_identities"]
    assert {(e["version"], e["approval_event"]) for e in identities} == set(expected_pairs)
    assert {e["entity_key"] for e in identities} == {"AEROMEXICO", "INDUSTRY", "VIVA_AEROBUS", "VOLARIS"}
    proof_path = next((root / "publications").glob("*.published.json"))
    proof = json.loads(proof_path.read_bytes())
    assert proof["receipt_type"] == "gate_site_manifest"
    assert proof["proof_scope"] == "local_generated_site"
    assert proof["output"] == str(site / "publication_manifest.json")
    assert proof["html_sha256"] == manifest_mod.sha256_file(site / "publication_manifest.json")
    assert all(flow.state(record, root)["state"] == "published" for record in records)

    target = site / "publication_manifest.json"
    original = target.read_bytes()
    target.unlink()
    assert all(flow.state(record, root)["state"] == "approved" for record in records)
    target.write_bytes(original)
    assert all(flow.state(record, root)["state"] == "published" for record in records)
    flow.revoke(legacy, "TEST ONLY withdrawal after local generation", "TEST ONLY", root)
    assert flow.state(legacy, root)["state"] == "validated"
    assert all(flow.state(record, root)["state"] == "published" for record in records if record is not legacy)
