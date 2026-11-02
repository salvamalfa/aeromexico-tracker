"""Adversarial checks of the separate story profile and its source boundary."""

import copy

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
        "La empresa reportó {{revenue}}. "
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
                        bindings={"revenue": dict(entity="AEROMEXICO", key="revenue", format="money")},
                        summary=True,
                        type="observed_fact",
                    ),
                    dict(
                        id="development",
                        title="Desarrollo",
                        text=text,
                        bindings={"revenue": dict(entity="AEROMEXICO", key="revenue", format="money")},
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
