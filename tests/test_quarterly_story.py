"""Adversarial checks of the separate story profile and its source boundary."""

import copy
import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.analysis_agent import quarterly_story as story
from src.web_export.analysis import _claim_citations
from src.web_export.schemas import analysis_schema_for


@pytest.fixture
def frozen(monkeypatch):
    packages, contexts = {}, {}
    for entity in story.ENTITIES[:-1]:
        package = dict(
            entity_key=entity,
            period_id=story.PERIOD,
            cutoff_date="2026-10-28",
            evidence_fingerprint=entity,
            sources=[dict(artifact_id="report", source_url="https://www.sec.gov/example")],
            excerpts=[
                dict(
                    excerpt_id="qualitative",
                    artifact_id="report",
                    text="The issuer reports business results.",
                    locator="release",
                )
            ],
        )
        calculations = dict(
            period_id=story.PERIOD,
            evidence_fingerprint=entity,
            calculation_fingerprint=entity,
            nodes=[
                dict(
                    key="revenue",
                    period_id=story.PERIOD,
                    value=1000000.0,
                    unit="USD",
                    formatted_value="reported million",
                )
            ],
        )
        packages[entity] = package
        contexts[entity] = (package, calculations)
    monkeypatch.setattr(story, "_contexts", lambda selected: contexts)
    text = (
        "La empresa reportó {{revenue}} y comparó {{reported}}. "
        + "El resultado requiere revisar ventas costos y capacidad durante el trimestre. " * 10
    )
    spec = dict(
        period_id=story.PERIOD,
        analyses={
            e: dict(
                title="Lectura del negocio",
                parts=[
                    dict(
                        id="summary",
                        title="Resumen",
                        text=text,
                        bindings={
                            "revenue": dict(entity="AEROMEXICO", key="revenue", format="money"),
                            "reported": dict(entity="AEROMEXICO", key="revenue", format="reported"),
                        },
                        summary=True,
                        type="observed_fact",
                    ),
                    dict(
                        id="development",
                        title="Desarrollo",
                        text=text,
                        bindings={
                            "revenue": dict(entity="AEROMEXICO", key="revenue", format="money"),
                            "reported": dict(entity="AEROMEXICO", key="revenue", format="reported"),
                        },
                        type="observed_fact",
                    ),
                ],
            )
            for e in story.ENTITIES
        },
    )
    package = story.prepare(spec, packages, "INDUSTRY")
    calculations = story.replay(package)
    return package, calculations, story.draft_for(package, calculations)


@pytest.mark.parametrize("mutation", ["number", "extra_claim", "hidden", "source", "emphasis"])
def test_review_content_cannot_be_changed_after_source_render(frozen, mutation):
    package, calculations, draft = frozen
    draft = copy.deepcopy(draft)
    if mutation == "number":
        draft["claims"][1]["text_template"] += " 900"
    elif mutation == "extra_claim":
        draft["claims"].append(copy.deepcopy(draft["claims"][1]))
    elif mutation == "hidden":
        draft["reader_private_section_keys"] = ["development"]
    elif mutation == "source":
        draft["claims"][1]["source_part"]["bindings"]["revenue"]["entity"] = "VOLARIS"
    else:
        draft["claims"][1]["emphasis"] = ["Unsupported words"]
    with pytest.raises(ValueError, match="differs"):
        story.validate(draft, package, calculations)


def test_frozen_review_identity_is_checked(frozen):
    package, _, _ = frozen
    changed = copy.deepcopy(package)
    changed["review_version"] = "0" * 64
    with pytest.raises(ValueError, match="review identity"):
        story.replay(changed)


def test_failed_native_source_verification_is_never_replaced_by_frozen_values(monkeypatch):
    from src.analysis_agent import quarterly_release

    def unavailable(_):
        raise ValueError("Missing original Library provenance")

    monkeypatch.setattr(quarterly_release, "calculate", unavailable)
    packages = {
        e: dict(
            entity_key=e,
            period_id=story.PERIOD,
            source_profile="quarterly_release_v1" if e == "AEROMEXICO" else "issuer_quarter_v1",
        )
        for e in story.ENTITIES[:-1]
    }
    with pytest.raises(ValueError, match="Missing original Library provenance"):
        story._contexts(packages)


def test_public_citations_retain_verified_values_without_private_packages(frozen):
    package, calculations, draft = frozen
    check = story.validate(draft, package, calculations)
    citations = _claim_citations(draft["claims"][1], package, calculations, {}, check["rendered"]["summary"])
    assert citations[0]["value"] == "US$1.0 millones"
    assert set(citations[0]) == {"label", "href", "title", "value"}
    assert citations[0]["href"] == "https://www.sec.gov/example"


def test_new_industry_q3_can_cite_primary_release_distributor():
    schema = analysis_schema_for("2026Q3", "INDUSTRY")
    assert "globenewswire" in schema["$defs"]["citation"]["properties"]["href"]["pattern"]
    assert (
        "globenewswire"
        not in analysis_schema_for("2026Q2", "INDUSTRY")["$defs"]["citation"]["properties"]["href"]["pattern"]
    )


def test_immutable_json_round_trip_preserves_citations_and_calculation_identity(frozen):
    from src.analysis_agent.evidence import canonical

    package, calculations, _ = frozen
    reread = json.loads(canonical(package))
    assert list(package["review_spec"]["analyses"]["INDUSTRY"]["parts"][0]["bindings"]) == [
        "revenue",
        "reported",
    ]
    assert list(reread["review_spec"]["analyses"]["INDUSTRY"]["parts"][0]["bindings"]) == [
        "reported",
        "revenue",
    ]
    assert story.replay(reread) == json.loads(canonical(calculations))


def test_import_lifecycle_and_public_payload_survive_immutable_serialization(frozen, tmp_path, monkeypatch):
    from jsonschema import Draft202012Validator

    from src.analysis_agent import issuer_quarter, lifecycle
    from src.web_export.analysis import publication_payload

    package, _, _ = frozen
    original_criteria = story.PATHS.root / ".agents/skills/airline-quarterly-story/SKILL.md"
    criteria = tmp_path / ".agents/skills/airline-quarterly-story/SKILL.md"
    criteria.parent.mkdir(parents=True)
    criteria.write_bytes(original_criteria.read_bytes())
    monkeypatch.setattr(story, "PATHS", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(issuer_quarter, "PATHS", SimpleNamespace(root=tmp_path))
    monkeypatch.setattr(story, "code_version", lambda: "f" * 64)
    path = story.import_draft(package)
    record = story.read(path)
    package, calculations, checks = story.verified_inputs(record)
    ledger = tmp_path / "analysis_runs/lifecycle"
    with pytest.raises(ValueError, match="no human approval"):
        lifecycle.consumer_payload(record, root=ledger)
    report = dict(
        entity_key="INDUSTRY",
        version=record["version"],
        content_hash=record["content_hash"],
        package_id=record["draft"]["package_id"],
        calculation_fingerprint=record["draft"]["calculation_fingerprint"],
        reviewer="independent_codex_agent",
        reviewer_task="isolated-test-independent-reviewer",
        model=None,
        model_unavailable_reason="Synthetic isolated fixture",
        decision="pass",
        findings=[],
        reviewed_claim_ids=[c["claim_id"] for c in record["draft"]["claims"]],
        checks=[
            dict(key=key, result="pass", detail="Synthetic isolated fixture") for key in lifecycle.CHECKS
        ],
    )
    lifecycle.record_audit(record, report, root=ledger)
    authorization = dict(
        entity_key="INDUSTRY",
        decision="approve_analysis",
        version=record["version"],
        content_hash=record["content_hash"],
        human_name="isolated-test-owner",
        verbatim_message="Synthetic isolated fixture consent",
        conversation_reference="isolated-test",
        authorized_at=datetime.now(UTC).isoformat(),
    )
    lifecycle.approve(record, authorization, root=ledger)
    payload = publication_payload(
        record, lifecycle.consumer_payload(record, root=ledger), package, calculations
    )
    Draft202012Validator(analysis_schema_for("2026Q3", "INDUSTRY")).validate(payload)
    assert payload["summary"] == [checks["rendered"]["summary"]]
    assert payload["claims"][1]["citations"][0]["value"] == "US$1.0 millones"
