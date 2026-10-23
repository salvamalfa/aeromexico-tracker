"""Independent adversarial contracts; synthetic reports do not establish source availability."""

from __future__ import annotations

import json
import shutil
from decimal import Decimal
from uuid import uuid4

import pandas as pd
import pytest
from test_source_update_viva_financial import CUTOFF, ORIGINAL, native, pages, workspace

from src.source_updates import readiness
from src.source_updates import viva_financial_candidate as candidate
from src.source_updates import viva_financial_gold as gold
from src.source_updates import viva_financials as source
from src.source_updates.viva_financial_checks import reconcile

FACT = "fact_viva_retained_financial_source_metrics"


@pytest.fixture
def stored(monkeypatch):
    root, _, child, _, run_id = workspace(monkeypatch, "independent-" + uuid4().hex)
    try:
        yield root, child, run_id
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_full_domain_contains_both_editions_durations_instants_and_geographies():
    frame = native()
    gold.validate(frame)
    assert len(frame) == 655
    expected = {
        ("2026Q1", "indicators"): 74,
        ("2026Q1", "income"): 48,
        ("2026Q1", "balance"): 88,
        ("2026Q1", "cash_flow"): 12,
        ("2026Q1", "debt"): 14,
        ("2026Q1", "fleet"): 21,
        ("2026Q2", "indicators"): 148,
        ("2026Q2", "income"): 96,
        ("2026Q2", "balance"): 88,
        ("2026Q2", "cash_flow"): 24,
        ("2026Q2", "debt"): 14,
        ("2026Q2", "fleet"): 28,
    }
    assert frame.groupby(["edition", "statement"]).size().to_dict() == expected
    q2 = frame.loc[frame.edition.eq("2026Q2")]
    assert set(q2.loc[q2.period_type.eq("quarter"), "period_start_date"]) == {"2026-04-01", "2025-04-01"}
    assert set(q2.loc[q2.period_type.eq("half_year"), "period_start_date"]) == {"2026-01-01", "2025-01-01"}
    assert q2.loc[q2.period_type.eq("instant"), "period_start_date"].isna().all()
    assert set(q2.loc[q2.metric_key.eq("booked_passengers"), "segment"]) == {
        "total",
        "domestic",
        "international",
    }


@pytest.mark.parametrize("statement", ["indicators", "income", "balance", "cash_flow", "debt", "fleet"])
def test_no_statement_can_omit_even_one_comparative_or_support_observation(statement):
    frame = native()
    index = frame.index[frame.edition.eq("2026Q1") & frame.statement.eq(statement)][-1]
    with pytest.raises(ValueError, match="complete.*domain"):
        gold.validate(frame.drop(index))


@pytest.mark.parametrize("change", ["includes", "unknown"])
def test_fleet_exclusion_scope_must_be_proved_by_the_literal_note(change):
    raw = pages()
    old = "excludes short term leases (ACMIs)"
    assert old in raw[2]
    raw[2] = raw[2].replace(old, "includes short term leases (ACMIs)" if change == "includes" else "")
    with pytest.raises(ValueError):
        source.edition(raw, ORIGINAL, 2)


@pytest.mark.parametrize(
    "old,new",
    [
        ("IFRS 9", "IFRS 16"),
        ("cash in transit", "lease deposits"),
        ("accounts receivable and other receivables", "inventories"),
    ],
)
def test_cash_comparability_cause_must_be_verified_before_receipt_attributes_it(old, new):
    raw = pages()
    proof = (
        "presented in accordance with the IFRS 9 amendment, under which cash in transit "
        "is classified within accounts receivable and other receivables."
    )
    if proof not in raw[2]:
        prefix = "(1) Cash and cash equivalents"
        raw[2] = raw[2].replace(prefix, prefix + " " + proof)
    source.edition(raw, ORIGINAL, 2)
    assert old in raw[2]
    raw[2] = raw[2].replace(old, new)
    with pytest.raises(ValueError):
        source.edition(raw, ORIGINAL, 2)


def test_fractional_aircraft_cannot_pass_as_exact_counts():
    frame = native()
    mask = frame.statement.eq("fleet") & frame.unit.eq("aircraft")
    # Every component and total change proportionally, preserving fleet percentages.
    frame.loc[mask, "source_value"] = frame.loc[mask, "source_value"].map(
        lambda value: str(Decimal(value) * Decimal("1.1"))
    )
    frame.loc[mask, "value"] *= 1.1
    with pytest.raises(ValueError):
        gold.validate(frame)
        reconcile(frame)


def test_cash_rounding_uses_reported_precision_and_rejects_a_larger_residual():
    frame = native()
    mask = (
        frame.edition.eq("2026Q2")
        & frame.statement.eq("cash_flow")
        & frame.period_type.eq("quarter")
        & frame.period_end_date.eq("2026-06-30")
        & frame.metric_key.eq("cash_operating")
    )
    index = frame.index[mask][0]
    frame.loc[index, ["source_value", "value"]] = ["11", 11.0]
    details = reconcile(frame)
    check = next(
        value
        for value in details["accounting_and_operating_checks"]
        if value["check"] == "2026Q2/quarter/2026-04-01/2026-06-30/cash_flow"
    )
    assert Decimal(check["residual"]) == 1000
    assert Decimal(check["rounding_bound"]) == 2000
    frame.loc[index, ["source_value", "value"]] = ["13", 13.0]
    with pytest.raises(ValueError, match="cash_flow"):
        reconcile(frame)


def test_cross_edition_disagreement_is_a_diagnostic_not_an_imputed_quarter():
    frame = native()
    before = frame.copy(deep=True)
    details = reconcile(frame)
    differences = [
        row
        for row in details["cross_edition_diagnostics"]
        if row["status"] == "reported_difference_requires_review"
    ]
    assert differences
    assert details["derived_Q1_metrics_emitted"] == 0
    assert details["historical_harmonization_allowed"] is False
    assert details["technical_certification_not_publication_approval"] is True
    for row in differences:
        assert len(row["source_observations"]) == 3
        assert {source["source_file"] for source in row["source_observations"]} == {"q1.pdf", "q2.pdf"}
        assert {source["source_hash"] for source in row["source_observations"]} == {"a" * 64, "b" * 64}
    pd.testing.assert_frame_equal(frame, before, check_exact=True)


def test_gold_scales_and_every_parent_belong_to_the_actual_q2_artifact(stored):
    _, child, run_id = stored
    result = candidate.run(child, "viva_financials", "2026Q2", CUTOFF, run_id, execute=True)
    frame = pd.read_parquet(child / f"data/gold/{FACT}.parquet")
    silver = pd.read_parquet(child / "data/silver/viva_financial_native.parquet")
    gold.validate(silver)
    gold.validate(frame, gold=True)
    parents = silver.set_index("record_id")
    bridge = pd.read_parquet(child / "data/gold/bridge_record_lineage.parquet")
    artifacts = pd.read_parquet(child / "data/gold/dim_source_artifact.parquet").set_index("source_file")
    retained = json.loads((child / f"receipts/retained-{run_id}.json").read_text())
    primary_file = retained["originals"]["pdf"]["source_file"]
    support_file = retained["originals"]["prior_quarter"]["source_file"]
    assert primary_file != support_file
    assert len(frame) == 386 and frame.edition.eq("2026Q2").all()
    assert not frame.segment.eq("context_not_gold").any()
    assert not frame.metric_key.str.contains("imputed|derived_Q1|context_").any()
    for fact in frame.itertuples(index=False):
        parent = parents.loc[fact.native_parent_record_id]
        assert parent.edition == "2026Q2" and parent.source_file == primary_file
        assert fact.source_hash == parent.source_hash == artifacts.loc[primary_file].artifact_sha256
        assert fact.value == float(
            Decimal(fact.source_value.rstrip("%x").replace(",", "")) * Decimal(str(fact.scale))
        )
        links = bridge.loc[bridge.record_id.eq(fact.record_id)]
        assert len(links) == 2
        assert links.loc[links.link_type.eq("parent_record"), "parent_record_id"].tolist() == [
            fact.native_parent_record_id
        ]
        assert links.loc[links.link_type.eq("artifact"), "artifact_id"].tolist() == [
            artifacts.loc[primary_file].artifact_id
        ]
    scheduled = frame.loc[frame.metric_key.eq("scheduled_load_factor"), "value"]
    assert scheduled.eq(0.9).all()  # Synthetic total RPM/ASM is0.7, deliberately different.
    assert result["first_publication_date"] is None and result["release_lag_days"] is None
    assert result["historical_harmonization_allowed"] is False
    assert result["publication"] == "not_authorized" and result["activation"] == "none"


def test_retained_viva_adapter_is_readable_by_the_round_checker(stored):
    _, child, run_id = stored
    candidate.run(child, "viva_financials", "2026Q2", CUTOFF, run_id, execute=True)
    item = dict(
        id="viva-financial",
        product="viva_financials",
        period="2026Q2",
        adapter="viva_financial",
        workspace=str(child),
        receipt_id=run_id,
        required=True,
        candidate_as_of=CUTOFF,
    )
    before = candidate.inventory(child)
    result = readiness.check_task(item, CUTOFF)
    assert result["status"] == "checks_passed"
    assert result["collection_basis"] == "retained"
    assert not result["latest_source_availability_verified"]
    assert candidate.inventory(child) == before


@pytest.mark.parametrize("target", ["parent", "comparison_receipt", "native_flags"])
def test_immutable_replay_rejects_parent_status_or_native_flag_tampering(stored, target):
    _, child, run_id = stored
    candidate.run(child, "viva_financials", "2026Q2", CUTOFF, run_id, execute=True)
    if target == "comparison_receipt":
        path = child / "receipts/viva-financial-viva_financials-2026Q2.json"
        receipt = json.loads(path.read_text())
        receipt["historical_harmonization_allowed"] = True
        path.write_text(json.dumps(receipt))
    else:
        path = child / (
            f"data/gold/{FACT}.parquet" if target == "parent" else "data/silver/viva_financial_native.parquet"
        )
        frame = pd.read_parquet(path)
        if target == "parent":
            frame.loc[0, "native_parent_record_id"] = "rec_" + "0" * 64
        else:
            frame.loc[0, "agent_eligible"] = True
        frame.to_parquet(path, index=False)
    before = candidate.inventory(child)
    with pytest.raises(ValueError):
        candidate.run(child, "viva_financials", "2026Q2", CUTOFF, run_id, check=True)
    assert candidate.inventory(child) == before
