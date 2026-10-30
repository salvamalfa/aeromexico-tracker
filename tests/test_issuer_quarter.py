"""Adversarial boundaries for the source-replayed compact issuer profile."""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from src.analysis_agent import issuer_quarter as issuer


def example():
    node = dict(
        calculation_id="calc_revenue",
        value=123000000,
        unit="USD",
        period_id="2026Q3",
        input_ids=["metric_revenue"],
        formatted_value="123.0 millones de dólares",
    )
    package = dict(
        entity_key="VOLARIS",
        period_id="2026Q3",
        package_id="package",
        evidence_fingerprint="evidence",
        excerpts=[dict(excerpt_id="excerpt", text="Exact quote")],
        metrics=[dict(metric_id="metric_revenue")],
    )
    calc = dict(calculation_fingerprint="calculation", nodes=[node])
    claim = dict(
        claim_id="entry",
        type="observed_fact",
        text_template="Los ingresos fueron {{revenue}}. "
        + "El dato conserva el mismo periodo y la moneda del reporte. " * 19,
        bindings=dict(revenue=dict(calculation_id="calc_revenue", unit="USD", period_id="2026Q3")),
        evidence_ids=["excerpt"],
        support_calculation_ids=[],
        support_spans=[],
        confidence_reason="Original replayed",
        limitations=[],
    )
    thesis = dict(claim, claim_id="thesis", text_template="Una lectura de negocio", bindings={})
    draft = dict(
        schema_version="entity_analyst_v1",
        source_profile=issuer.PROFILE,
        state="draft",
        entity_key=package["entity_key"],
        period_id=package["period_id"],
        package_id=package["package_id"],
        evidence_fingerprint=package["evidence_fingerprint"],
        calculation_fingerprint="calculation",
        language="es-MX",
        model=None,
        model_unavailable_reason="Not exposed by native host",
        claims=[thesis, claim],
        thesis_claim_id="thesis",
        summary_claim_ids=["entry"],
        sections=[],
    )
    return draft, package, calc


def test_compact_profile_has_its_own_length_contract():
    draft, package, calculations = example()
    result = issuer.validate(draft, package, calculations)
    assert 200 <= result["total_words"] <= 300


@pytest.mark.parametrize(
    "mutation",
    [
        "literal_number",
        "wrong_period",
        "wrong_unit",
        "missing_excerpt",
        "unbound_alias",
        "missing_reference",
        "duplicate_placement",
        "unsupported_attribution",
        "unlimited_hypothesis",
        "short_prose",
    ],
)
def test_claim_mutations_fail_closed(mutation):
    draft, package, calculations = deepcopy(example())
    claim = draft["claims"][1]
    if mutation == "literal_number":
        claim["text_template"] += " 2026."
    elif mutation == "wrong_period":
        claim["bindings"]["revenue"]["period_id"] = "2025Q3"
    elif mutation == "wrong_unit":
        claim["bindings"]["revenue"]["unit"] = "MXN"
    elif mutation == "missing_excerpt":
        claim["evidence_ids"] = ["unknown"]
    elif mutation == "unbound_alias":
        claim["text_template"] += " {{net}}"
    elif mutation == "missing_reference":
        claim["text_template"] = "Sin evidencia"
        claim.update(bindings={}, evidence_ids=[])
    elif mutation == "duplicate_placement":
        draft["sections"] = [dict(title="Duplicado", claim_ids=["entry"])]
    elif mutation == "unsupported_attribution":
        claim["type"] = "company_attribution"
        claim["support_spans"] = [dict(excerpt_id="excerpt", text="Invented company explanation")]
    elif mutation == "unlimited_hypothesis":
        claim["type"] = "hypothesis"
    else:
        claim["text_template"] = "Ingresos {{revenue}}."
    with pytest.raises((ValueError, KeyError)):
        issuer.validate(draft, package, calculations)


@pytest.mark.parametrize(
    "entity,period", [("INDUSTRY", "2026Q3"), ("VOLARIS", "2026Q4"), ("../VOLARIS", "2026Q3")]
)
def test_unreviewed_edition_rejected_before_reading(tmp_path, entity, period):
    with pytest.raises(ValueError, match="Unreviewed"):
        issuer.replay(tmp_path, entity, period, "bad", "bad")


def test_source_workspace_cannot_escape_or_traverse_symlink(tmp_path, monkeypatch):
    root = tmp_path / "tracker"
    root.mkdir()
    outside = tmp_path / "external"
    outside.mkdir()
    link = root / "tmp/source-updates/candidate"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(issuer, "PATHS", SimpleNamespace(root=root))
    for path in (outside, link):
        with pytest.raises(ValueError, match="workspace"):
            issuer.replay(path, "VOLARIS", "2026Q3", "bad", "bad")


def test_output_cannot_write_public_site(tmp_path, monkeypatch):
    root = tmp_path / "tracker"
    root.mkdir()
    monkeypatch.setattr(issuer, "PATHS", SimpleNamespace(root=root))
    with pytest.raises(ValueError, match="private ignored"):
        issuer.immutable(root / "site/data/v1/analysis.json", {})
    assert not (root / "site").exists()


def test_same_private_artifact_is_idempotent_and_conflicting_bytes_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(issuer, "PATHS", SimpleNamespace(root=tmp_path))
    path = tmp_path / "analysis_runs/test.json"
    issuer.immutable(path, {"source": "first"})
    before = path.read_bytes()
    issuer.immutable(path, {"source": "first"})
    assert before == path.read_bytes()
    with pytest.raises(ValueError, match="Immutable"):
        issuer.immutable(path, {"source": "different"})
    assert before == path.read_bytes()
