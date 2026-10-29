"""Private Q3 contract preparation: invented pages, in-memory rows, no real ingestion."""

from types import SimpleNamespace

import pandas as pd
import pytest
from test_source_update_viva_financial import ORIGINAL, native, pages, table

from src.source_updates import viva_financial_candidate as candidate
from src.source_updates import viva_financial_gold as gold
from src.source_updates import viva_financials as source
from src.source_updates.catalog import ROOT
from src.source_updates.viva_financial_checks import numeric, reconcile
from src.source_updates.viva_financial_spec import FLEET, GRAIN, NATIVE, TABLE
from src.transform.stage9_lineage import add_record_ids


def q3_pages():
    # The existing helper invents all amounts. No original report is read here.
    result = [
        p.replace("June 30", "September 30")
        .replace("July 24th", "Oct 28th")
        .replace("2Q 2026", "3Q 2026")
        .replace("2Q 2025", "3Q 2025")
        .replace("Six-month", "Nine-month")
        .replace("6M ", "9M ")
        for p in pages(2)
    ]
    result[0] = result[0].replace("Nacionales S.A.", "Nacionales, S.A.")
    result[8] = result[8].replace("Operating profit (loss)", "Operating profit")
    result[10] = (
        result[10]
        .replace("Jun 2026", "Sep 2026")
        .replace("Accounts receivables and other", "Accounts receivable and other")
    )
    debt = result[2].split("Aircraft*", 1)[0].replace("Jun 2026", "Sep 2026")
    result[2] = (
        debt
        + "Aircraft* Sep 2026 Jun 2026 Mar 2026 Dec 2025 Sep 2025\n"
        + table(
            FLEET,
            dict(
                a320ceo=1, a320neo=1, a321ceo=1, a321neo=1, fleet_total=4, a321_fraction=50, neo_fraction=50
            ),
            5,
            False,
        )
        + "\n*Total Fleet at EoP excludes short term leases (ACMIs)"
    )
    return result


@pytest.fixture(autouse=True)
def no_actual_pdf_or_candidate_io(monkeypatch):
    def forbidden(*_a, **_kw):
        raise AssertionError("Actual PDF ingestion/candidate IO is outside these contract tests")

    monkeypatch.setattr(source, "PdfReader", forbidden)
    monkeypatch.setattr(candidate, "originals", forbidden)
    monkeypatch.setattr(candidate, "frames", forbidden)
    monkeypatch.setattr(candidate, "writer", forbidden)


@pytest.fixture
def q3_native():
    original = {
        **ORIGINAL,
        "source_file": "SYNTHETIC-q3.pdf",
        "sha256": "c" * 64,
        "downloaded_at": "2026-10-29T06:00:00Z",
    }
    return pd.concat(
        [source.edition(q3_pages(), original, 3), source.edition(pages(2), ORIGINAL, 2)], ignore_index=True
    )


def test_q3_full_domain_keeps_separate_quarter_nine_month_and_five_fleet_instants(q3_native):
    gold.validate(q3_native, period="2026Q3")
    assert len(q3_native) == 803
    primary = q3_native.loc[q3_native.edition.eq("2026Q3")]
    assert len(primary) == 405
    assert set(primary.loc[primary.period_type.eq("quarter"), "period_start_date"]) == {
        "2026-07-01",
        "2025-07-01",
    }
    assert set(primary.loc[primary.period_type.eq("nine_month"), "period_start_date"]) == {
        "2026-01-01",
        "2025-01-01",
    }
    assert primary.loc[primary.period_type.eq("instant"), "period_start_date"].isna().all()
    assert set(primary.loc[primary.statement.eq("fleet"), "period_end_date"]) == {
        "2026-09-30",
        "2026-06-30",
        "2026-03-31",
        "2025-12-31",
        "2025-09-30",
    }
    assert primary.report_date.eq("2026-10-28").all()
    details = reconcile(q3_native)
    assert details["quarters_validated"] == ["2026Q3"] and not details["historical_harmonization_allowed"]
    assert {d["comparison_period"] for d in details["cross_edition_diagnostics"]} == {"2026H1", "2025H1"}
    assert details["derived_Q1_metrics_emitted"] == 0
    # Historical Q2/Q1 remain byte-for-value compatible in memory.
    previous = native()
    gold.validate(previous)
    pd.testing.assert_frame_equal(
        q3_native.loc[q3_native.edition.eq("2026Q2")].reset_index(drop=True),
        previous.loc[previous.edition.eq("2026Q2")].reset_index(drop=True),
        check_exact=True,
    )


@pytest.mark.parametrize(
    "page,old,new",
    [
        (7, "Nine-month period", "Six-month period"),
        (8, "Operating profit", "Operating profit (loss)"),
        (
            2,
            "Aircraft* Sep 2026 Jun 2026 Mar 2026 Dec 2025 Sep 2025",
            "Aircraft* Sep 2026 Jun 2026 Mar 2026 Dec 2025",
        ),
        (10, "Accounts receivable and other", "Accounts receivables and other"),
    ],
)
def test_changed_q3_table_scope_and_labels_reject_instead_of_inventing_rows(page, old, new):
    value = q3_pages()
    assert old in value[page]
    value[page] = value[page].replace(old, new)
    with pytest.raises(ValueError):
        source.edition(value, ORIGINAL, 3)


def test_q3_contract_rejects_missing_support_mislabeled_duration_and_source_units(q3_native):
    for mutation in ("support", "duration", "unit"):
        frame = q3_native.copy()
        if mutation == "support":
            frame = frame.loc[frame.edition.eq("2026Q3")]
        elif mutation == "duration":
            frame.loc[frame.period_type.eq("nine_month"), "period_type"] = "half_year"
        else:
            index = frame.index[frame.metric_key.eq("asm")][0]
            frame.loc[index, "unit"] = "seat_kilometers"
        with pytest.raises(ValueError):
            gold.validate(frame, period="2026Q3")


def test_q3_gold_contract_is_in_memory_only_and_rejects_prior_edition_projection(q3_native):
    primary = add_record_ids(q3_native, table_name=NATIVE, natural_key_columns=GRAIN)
    facts = primary.loc[primary.edition.eq("2026Q3") & primary.segment.ne("context_not_gold")].copy()
    facts["native_parent_record_id"] = facts.pop("record_id")
    facts["normalization"] = "reported_value_times_explicit_scale_no_currency_or_distance_conversion"
    facts["value"] = [float(numeric(r)) for r in facts.itertuples(index=False)]
    facts = add_record_ids(facts, table_name=TABLE, natural_key_columns=GRAIN)
    gold.validate(facts, gold=True, period="2026Q3")
    assert len(facts) == 393 and facts.edition.eq("2026Q3").all()
    bad = facts.copy()
    bad.loc[bad.index[0], "edition"] = "2026Q2"
    with pytest.raises(ValueError):
        gold.validate(bad, gold=True, period="2026Q3")


def test_period_role_router_uses_only_synthetic_reader_and_keeps_q2_pair(monkeypatch):
    seen = []

    def reader(stream):
        data = stream.getvalue()
        assert data.startswith(b"%PDF-SYNTHETIC") and len(data) < 64
        return SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda: "synthetic")])

    def edition(_pages, original, q):
        seen.append((original["source_file"], q))
        return pd.DataFrame({"edition": [f"2026Q{q}"]})

    monkeypatch.setattr(source, "PdfReader", reader)
    monkeypatch.setattr(source, "edition", edition)
    import src.source_updates.viva_financial_checks as checks

    monkeypatch.setattr(checks, "reconcile", lambda _native: {"synthetic_router": True})
    inputs = {role: (b"%PDF-SYNTHETIC", {"source_file": role}) for role in ("pdf", "prior_quarter")}
    for period, expected in [
        ("2026Q2", [("pdf", 2), ("prior_quarter", 1)]),
        ("2026Q3", [("pdf", 3), ("prior_quarter", 2)]),
    ]:
        seen.clear()
        source.parse(inputs, period)
        assert seen == expected
    with pytest.raises(ValueError):
        source.parse(inputs, "2026Q4")


def test_q3_plan_never_opens_originals_or_writes_candidate_outputs():
    workspace = ROOT / "tmp/source-updates/contract-only-viva-q3-not-executed"
    assert not workspace.exists()
    result = candidate.run(workspace, "viva_financials", "2026Q3", "2026-10-29T08:00:00Z", "a" * 32)
    assert result["status"] == "planned_not_executed" and not workspace.exists()
    assert (
        not result["latest_source_availability_verified"] and not result["ready_for_calendar_incorporation"]
    )
    assert result["activation"] == "none" and result["publication"] == "not_authorized"


def test_revision_support_transition_is_diagnostic_and_cannot_use_future_baseline(q3_native, monkeypatch):
    previous = native()
    monkeypatch.setattr(candidate.pd, "read_parquet", lambda _path: previous)
    monkeypatch.setattr(candidate, "digest", lambda _path: "a" * 64)
    result = candidate.revisions(
        ROOT / "tmp/source-updates/synthetic-no-files",
        "baselines/synthetic.parquet",
        "viva_financials",
        {"silver/viva_financial_native": q3_native},
    )
    assert result["added"] == 405 and result["removed"] == 257 and result["unchanged"] == 398
    assert result["changed"] == 0 and result["edition_transition"] == {
        "baseline_primary": "2026Q2",
        "current_primary": "2026Q3",
        "support_scope_shift_not_historical_deletion": True,
    }
    monkeypatch.setattr(candidate.pd, "read_parquet", lambda _path: q3_native)
    with pytest.raises(ValueError, match="later than"):
        candidate.revisions(
            ROOT / "tmp/source-updates/synthetic-no-files",
            "baselines/synthetic.parquet",
            "viva_financials",
            {"silver/viva_financial_native": previous},
        )


def test_q3_closed_edition_binding_requires_exact_original_and_keeps_revision_uncertainty(
    q3_native, monkeypatch
):
    from src.source_updates import availability_viva_financials as proof
    from src.source_updates.closed_editions import accepted

    item = dict(
        product="viva_financials",
        adapter="viva_financial",
        period="2026Q3",
        workspace=str(ROOT / "tmp/source-updates/synthetic-no-files"),
        receipt_id="a" * 32,
        candidate_as_of="2026-10-29T08:00:00Z",
        availability={"source_scope": proof.SCOPE},
    )
    result = dict(
        status="checks_passed",
        report_period="2026Q3",
        effective_as_of=item["candidate_as_of"],
        retention_receipt_sha256="b" * 64,
    )
    row = dict(
        source_url=proof.URL,
        sha256=proof.SHA,
        source_file="SYNTHETIC-q3.pdf",
        http_status=200,
        download_method="httpx",
        bytes=336146,
        downloaded_at="2026-10-29T06:37:58.284944+00:00",
    )
    frame = q3_native.copy()
    frame.loc[frame.edition.eq("2026Q3"), "source_hash"] = proof.SHA
    monkeypatch.setattr(proof, "originals", lambda *_args: ({"pdf": (b"SYNTHETIC", row)}, "b" * 64))
    monkeypatch.setattr(proof.pd, "read_parquet", lambda *_args: frame)
    cutoff = "2026-11-17T18:00:00Z"
    value = proof.verify(item, result, cutoff)
    assert value["latest_available_period"] is None
    assert value["validated_closed_edition"]["revision_check"]["status"] == "not_checked"
    assert not value["validated_closed_edition"]["source_observation_current_for_round"]
    assert accepted(
        item,
        dict(
            status="checks_passed",
            latest_source_availability_verified=False,
            source_availability_evidence=value,
        ),
    )
    for key, bad in (
        ("sha256", "c" * 64),
        ("source_url", proof.URL.replace("3T26", "2T26")),
        ("download_method", "manual"),
        ("http_status", 403),
    ):
        saved = row[key]
        row[key] = bad
        with pytest.raises(ValueError):
            proof.verify(item, result, cutoff)
        row[key] = saved
    for changed in (
        {**item, "period": "2026Q2"},
        {**item, "availability": {"source_scope": proof.SCOPE, "known_new_edition": True}},
    ):
        with pytest.raises(ValueError):
            proof.verify(changed, result, cutoff)
    frame.loc[frame.edition.eq("2026Q3"), "source_hash"] = "c" * 64
    with pytest.raises(ValueError):
        proof.verify(item, result, cutoff)
