"""Synthetic dossiers test contracts; retained-original extraction is separate evidence."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates import global_readiness, readiness, retained
from src.source_updates import viva_financial_candidate as candidate
from src.source_updates import viva_financials as source
from src.source_updates.viva_financial_checks import reconcile
from src.source_updates.viva_financial_gold import validate
from src.source_updates.viva_financial_spec import BALANCE, CASH, DEBT, FLEET, INCOME, INDICATORS, TABLE

CUTOFF = "2026-10-23T18:00:00-06:00"
ORIGINAL = dict(
    source_system="viva_ir", source_file="q2.pdf", sha256="a" * 64, downloaded_at="2026-08-24T03:15:17Z"
)


def table(definitions, values, columns=2, variation=True):
    result = []
    for label, key, unit, _scale, segment in definitions:
        value = str(values.get((key, segment), values.get(key, 1)))
        if unit == "fraction":
            value += "%"
        elif unit == "times_ltm":
            value += "x"
        result.append(label + " " + " ".join([value] * columns) + (" 0.0%" if variation else ""))
    return "\n".join(result)


def pages(q=2):
    """Invented data; expected accounting values do not come from the production parser."""
    result = [""] * (12 if q == 2 else 10)
    month, short, date = ("June 30", "Jun", "July 24th") if q == 2 else ("March 31", "Mar", "April 30th")
    result[0] = (
        f"Mexico City, {date}, 2026 Grupo Viva Aerobus, S.A. de C.V. "
        f"the parent company of Aeroenlaces Nacionales S.A. de C.V. "
        f"announced today its {q}Q 2026 financial results. Viva’s "
        f"functional and reporting currency is the U.S. Dollar."
    )
    result[5] = (
        '"available seat miles" "revenue passenger miles" scheduled available '
        "seat miles (ASMs) Passengers: Customers who purchased their plane ticket to fly "
        "during the month referred in the report, regardless of whether they flew or not. non-IFRS "
        "financial measure Starting October 1, 2022"
    )
    note = (
        f"(1) Our consolidated financial statements for the period "
        f"ended {month}, 2026, are not yet available. These figures "
        f"are preliminary"
    )
    entity = source.ENTITY
    preliminary_mark = "1" if q == 1 else ""
    income_values = dict(
        passenger_revenue=600,
        ancillary_revenue=400,
        total_revenue=1000,
        other_income_expense_offset=-50,
        fuel=100,
        depreciation_amortization=50,
        landing_navigation=50,
        wages=50,
        operational_support=50,
        marketing_distribution=50,
        maintenance=50,
        leases=100,
        other_expenses=50,
        total_operating_expenses=500,
        operating_income=500,
        operating_margin=50,
        financial_income=10,
        financial_costs=-20,
        net_finance_costs=-10,
        income_before_tax=490,
        ebt_margin=49,
        income_tax=90,
        net_income=400,
        net_margin=40,
    )
    indicators = dict(
        total_revenue=1000,
        ebitda_non_ifrs=550,
        ebitdar_non_ifrs=650,
        ebitda_margin=55,
        ebitdar_margin=65,
        trasm=100,
        casm=50,
        casm_ex_fuel=40,
        casm_fuel=10,
        fare_per_booked_passenger=60,
        ancillary_per_booked_passenger=40,
        revenue_per_booked_passenger=100,
        revenue_per_seat=50,
        cost_per_seat=25,
        cost_ex_fuel_per_seat=20,
        seats=20,
        average_stage_length=50,
    )
    for key, values in [
        ("asm", (1, 0.6, 0.4)),
        ("rpm", (0.7, 0.4, 0.3)),
        ("booked_passengers", (10, 6, 4)),
        ("scheduled_load_factor", (90, 90, 90)),
    ]:
        indicators.update(
            {
                (key, segment): value
                for segment, value in zip(("total", "domestic", "international"), values, strict=True)
            }
        )
    for kind, page in [("quarter", 7), ("half_year", 8)] if q == 2 else [("quarter", 7)]:
        prefix = "Three" if kind == "quarter" else "Six"
        period = f"{q}Q" if kind == "quarter" else "6M"
        header = (
            f"{entity} {prefix}-month period ended {month}, 2026 and 2025 "
            f"(Financial Information in Thousands of U.S. Dollars, unless "
            f"otherwise stated) Financial and Operational Indicators {period} "
            f"2026 {period} 2025 % Var\n"
        )
        result[page - 1] = header + table(INDICATORS, indicators) + "\n(1) Bloomberg (2) Banxico"
        income_defs = [
            (
                label.replace("Operating profit (loss)", "Operating loss") if q == 1 else label,
                key,
                unit,
                scale,
                segment,
            )
            for label, key, unit, scale, segment in INCOME
        ]
        if kind == "half_year" or q == 1:
            income_defs = [
                (
                    label.replace("Income (loss) before income tax", "Loss before income tax").replace(
                        "Net income (loss)", "Net loss"
                    ),
                    key,
                    unit,
                    scale,
                    segment,
                )
                for label, key, unit, scale, segment in income_defs
            ]
        income_page = (9 if kind == "quarter" else 10) if q == 2 else 8
        result[income_page - 1] = (
            (
                f"{entity} {prefix}-month period ended {month}, 2026 and 2025 "
                f"(Thousands of U.S. Dollars) "
                f"US$ Thousand (unaudited){'1' if kind == 'half_year' else preliminary_mark} "
                f"{period} 2026 {period} 2025 % Var\n"
            )
            + table(income_defs, income_values)
            + ("\n" + note if kind == "half_year" or q == 1 else "")
        )
    balance_values = {key: 10 for _, key, *_ in BALANCE}
    balance_values.update(
        current_assets=60,
        assets=150,
        current_liabilities=100,
        liabilities=150,
        equity=0,
        liabilities_equity=150,
        **{key: 0 for _, key, *_ in BALANCE[34:42]},
    )
    result[(11 if q == 2 else 9) - 1] = (
        (
            f"{entity} As of {month}, 2026 and December 31, 2025 (Thousands "
            f"of U.S. Dollars) US$ Thousand (unaudited)1 {short} 2026 "
            f"Dec 2025 % Var\n"
        )
        + table(BALANCE, balance_values)
        + "\n"
        + note
    )
    cash_values = dict(
        cash_operating=10, cash_investing=-4, cash_financing=-1, cash_change=5, cash_begin=5, cash_end=10
    )
    cash = []
    for kind in ["quarter", "half_year"] if q == 2 else ["quarter"]:
        prefix, period = ("Three", f"{q}Q") if kind == "quarter" else ("Six", "6M")
        cash.append(
            (
                f"{entity} {prefix}-month period ended {month}, 2026 and 2025 "
                f"(Thousands of U.S. Dollars) "
                f"US$ Thousand (unaudited){'1' if kind == 'half_year' else preliminary_mark} "
                f"{period} 2026 {period} 2025 % Var\n"
            )
            + table(CASH, cash_values)
            + ("\n" + note if kind == "half_year" or q == 1 else "")
            + "\nDuring this period lease payments are reflected in financing activities."
        )
    result[-1] = "\n".join(cash)
    debt_values = dict(
        financial_debt=0.02,
        lease_liabilities=0.02,
        adjusted_debt=0.04,
        cash=0.01,
        net_adjusted_debt=0.03,
        net_debt_to_ltm_ebitdar=2,
        cash_to_ltm_revenue=5,
    )
    result[2] = (
        f"US$ Million {short} 2026 Dec 2025 % Var\n"
        + table(DEBT, debt_values)
        + "\n(1) Cash and cash equivalents IFRS 9 amendment cash in transit "
        "is classified within accounts receivable and other receivables. "
        "Prior periods have not been adjusted for comparability.\n"
    )
    result[2] += (
        (
            "Aircraft* Jun 2026 Mar 2026 Dec 2025 Jun 2025\n"
            if q == 2
            else "Aircraft* Mar 2026 Dec 2025 Mar 2025\n"
        )
        + table(
            FLEET,
            dict(
                a320ceo=1, a320neo=1, a321ceo=1, a321neo=1, fleet_total=4, a321_fraction=50, neo_fraction=50
            ),
            4 if q == 2 else 3,
            False,
        )
        + "\n*Total Fleet at EoP excludes short term leases (ACMIs)"
    )
    return result


def native():
    return pd.concat(
        [
            source.edition(pages(2), ORIGINAL, 2),
            source.edition(pages(1), {**ORIGINAL, "source_file": "q1.pdf", "sha256": "b" * 64}, 1),
        ],
        ignore_index=True,
    )


def test_synthetic_full_product_preserves_scope_and_reports_cross_edition_differences():
    frame = native()
    validate(frame)
    details = reconcile(frame)
    assert len(frame) == 655
    assert len(details["accounting_and_operating_checks"]) > 150
    assert any(
        row["status"] == "reported_difference_requires_review" for row in details["cross_edition_diagnostics"]
    )
    assert details["derived_Q1_metrics_emitted"] == 0
    assert not details["historical_harmonization_allowed"]
    # Reported scheduled LF is deliberately different from total RPM/ASM.
    lf = frame.loc[frame.metric_key.eq("scheduled_load_factor")]
    assert lf.value.eq(90).all()


@pytest.mark.parametrize(
    "page,old,new",
    [
        (0, "2Q 2026 financial", "3Q 2026 financial"),
        (0, "U.S. Dollar", "Mexican Peso"),
        (6, "2Q 2026 2Q 2025", "2Q 2025 2Q 2026"),
        (6, "ASMs (millions)", "ASKs (millions)"),
        (6, "Booked Passengers (thousands)", "Transported Passengers (thousands)"),
        (6, "Domestic 0.6", "Domestic N/A"),
        (6, "Domestic 0.6", "Domestic 0,,6"),
        (6, "90%", "190%"),
        (6, "TRASM (US cents) 100", "TRASM (US cents) 100%"),
        (8, "Passenger revenue 600", "Passenger revenue NaN"),
        (10, "As of June 30, 2026", "As of July 31, 2026"),
        (11, "These figures are preliminary", "Final audited results"),
    ],
)
def test_changed_context_unit_missing_or_malformed_rows_fail_closed(page, old, new):
    raw = pages()
    assert old in raw[page]
    raw[page] = raw[page].replace(old, new)
    with pytest.raises(ValueError):
        source.edition(raw, ORIGINAL, 2)


def test_duplicate_and_extra_table_rows_are_rejected():
    raw = pages()
    raw[8] = raw[8].replace("Fuel 100 100 0.0%", "Fuel 100 100 0.0% Fuel 100 100 0.0%")
    with pytest.raises(ValueError):
        source.edition(raw, ORIGINAL, 2)
    raw = pages()
    raw[8] += " Missing new expense 1 1 0.0%"
    with pytest.raises(ValueError):
        source.edition(raw, ORIGINAL, 2)


@pytest.mark.parametrize(
    "metric,statement",
    [
        ("passenger_revenue", "income"),
        ("assets", "balance"),
        ("cash_financing", "cash_flow"),
        ("asm", "indicators"),
    ],
)
def test_failed_own_statement_reconciliation_is_not_hidden_by_cross_edition_warning(metric, statement):
    frame = native()
    mask = frame.edition.eq("2026Q2") & frame.statement.eq(statement) & frame.metric_key.eq(metric)
    index = frame.index[mask][0]
    frame.loc[index, "source_value"] = "99999999"
    frame.loc[index, "value"] = 99999999
    with pytest.raises(ValueError):
        reconcile(frame)


@pytest.mark.parametrize(
    "field,value",
    [
        ("period_end_date", "2026-07-31"),
        ("scale", 1),
        ("unit", "MXN"),
        ("agent_eligible", True),
        ("is_preliminary", False),
        ("value", float("nan")),
    ],
)
def test_contract_rejects_forged_financial_semantics(field, value):
    frame = native()
    frame.loc[frame.index[frame.statement.eq("income")][0], field] = value
    with pytest.raises(Exception):
        validate(frame)


def test_contract_rejects_missing_duplicate_support_or_primary_observations():
    frame = native()
    for bad in [frame.iloc[1:], pd.concat([frame, frame.iloc[:1]]), frame.loc[frame.edition.eq("2026Q2")]]:
        with pytest.raises(ValueError):
            validate(bad)


def workspace(monkeypatch, tag):
    root = (Path("tmp/source-updates") / ("viva-financial-test-" + tag)).resolve()
    import shutil

    if root.exists():
        shutil.rmtree(root)
    depot, child = root / "depot", root / "candidate"
    files = {}
    for q, role in [(2, "pdf"), (1, "prior_quarter")]:
        row = save_bronze(
            b"%PDF-synthetic-" + str(q).encode(),
            source_system="viva_ir",
            entity="viva_test",
            period=f"2026Q{q}",
            ext="pdf",
            download_method="manual",
            downloaded_at=datetime(2026, 8, 24, tzinfo=UTC),
            source_url=f"https://www.investorcloud.net/VivaAerobus/Download/Viva{q}Q2026.pdf",
            bronze_root=depot,
        )
        files[role] = row.relative_to(depot).as_posix()

    def reader(stream):
        q = int(stream.getvalue().decode()[-1])
        return SimpleNamespace(
            pages=[SimpleNamespace(extract_text=lambda text=text: text) for text in pages(q)]
        )

    monkeypatch.setattr(source, "PdfReader", reader)
    saved = retained.retain(child, depot, "viva_financials", files, execute=True)
    return root, depot, child, files, saved["run_id"]


def test_actual_runner_gold_lineage_replay_immutability_and_readiness(monkeypatch, request):
    root, _depot, child, _files, run_id = workspace(monkeypatch, request.node.name)
    result = candidate.run(child, "viva_financials", "2026Q2", CUTOFF, run_id, execute=True)
    facts = pd.read_parquet(child / f"data/gold/{TABLE}.parquet")
    native_rows = pd.read_parquet(child / "data/silver/viva_financial_native.parquet")
    assert facts.edition.eq("2026Q2").all() and not facts.segment.eq("context_not_gold").any()
    assert set(facts.native_parent_record_id) <= set(
        native_rows.loc[native_rows.edition.eq("2026Q2"), "record_id"]
    )
    assert (
        facts.loc[facts.metric_key.eq("total_revenue") & facts.statement.eq("income"), "value"]
        .eq(1000000)
        .all()
    )
    assert result["lineage"]["artifact_count"] == 2
    before = candidate.inventory(child)
    assert (
        candidate.run(child, "viva_financials", "2026Q2", CUTOFF, run_id, check=True)["output_sha256"]
        == result["output_sha256"]
    )
    assert candidate.inventory(child) == before
    with pytest.raises(ValueError, match="immutable"):
        candidate.run(child, "viva_financials", "2026Q2", CUTOFF, run_id, execute=True)
    with pytest.raises(ValueError):
        candidate.run(child, "viva_financials", "2026Q2", "2026-10-24T18:00:00-06:00", run_id, check=True)
    item = dict(
        id="viva",
        product="viva_financials",
        period="2026Q2",
        adapter="viva_financial",
        workspace=str(child),
        receipt_id=run_id,
        required=True,
        candidate_as_of=CUTOFF,
    )
    recipe = dict(version=1, as_of=CUTOFF, required_items=["viva"], items=[item])
    checked = readiness.execute(recipe, root / "review", write=True)
    assert checked["status"] == "checks_passed" and not checked["ready_for_calendar_incorporation"]
    assert not result["latest_source_availability_verified"]
    assert result["network_requests"] == result["paid_requests"] == 0
    assert result["activation"] == "none" and result["publication"] == "not_authorized"
    facts.iloc[0, facts.columns.get_loc("value")] += 1
    facts.to_parquet(child / f"data/gold/{TABLE}.parquet", index=False)
    with pytest.raises(ValueError):
        candidate.run(child, "viva_financials", "2026Q2", CUTOFF, run_id, check=True)


def test_generic_retained_cannot_bypass_complete_financial_adapter():
    with pytest.raises(ValueError, match="dedicated"):
        retained.run(Path("tmp/source-updates/viva-bypass"), "viva_financials", "2026Q2", CUTOFF, "a" * 32)


def test_failure_validates_whole_dossier_before_any_silver_gold_write(monkeypatch, request):
    _root, _depot, child, _files, run_id = workspace(monkeypatch, request.node.name)

    def fail(*_args):
        raise ValueError("invalid own balance")

    monkeypatch.setattr(candidate, "parse", fail)
    with pytest.raises(ValueError, match="invalid own balance"):
        candidate.run(child, "viva_financials", "2026Q2", CUTOFF, run_id, execute=True)
    assert not list((child / "data/silver").rglob("*.parquet"))
    assert not list((child / "data/gold").rglob("*.parquet"))


def test_prior_quarter_support_cannot_bind_a_current_quarter_release(monkeypatch, request):
    root, _depot, child, _files, run_id = workspace(monkeypatch, request.node.name)
    candidate.run(child, "viva_financials", "2026Q2", CUTOFF, run_id, execute=True)
    item = dict(
        id="viva",
        product="viva_financials",
        period="2026Q2",
        adapter="viva_financial",
        workspace=str(child),
        receipt_id=run_id,
        required=True,
        candidate_as_of=CUTOFF,
    )
    checked = global_readiness.verify(item, root / "global-review")
    receipt = json.loads((child / f"receipts/retained-{run_id}.json").read_text())
    primary = receipt["originals"]["pdf"]
    support = receipt["originals"]["prior_quarter"]
    assert checked["contributing_artifacts"] == [
        dict(source_url=primary["source_url"], sha256=primary["sha256"])
    ]
    task = {k: v for k, v in item.items() if k != "required"}
    task.update(cadence="quarterly", used=True, depends_on=[])
    recipe = dict(
        version=1,
        round="quarterly",
        as_of=CUTOFF,
        monthly_period="2026M06",
        quarterly_period="2026Q2",
        items=[task],
        releases=[
            dict(
                entity="VIVA_AEROBUS",
                period="2026Q2",
                kind="financial_report",
                confirmed=True,
                published_at="2026-07-24T12:00:00-06:00",
                document_url=support["source_url"],
                source_sha256=support["sha256"],
                task_id="viva",
            )
        ],
    )
    rejected = global_readiness.evaluate(recipe, {"viva": checked})
    assert "VIVA_AEROBUS:release_not_bound_to_verified_contributing_artifact" in rejected["calendar_blockers"]
    assert rejected["quarterly_date"] is None
    recipe["releases"][0].update(document_url=primary["source_url"], source_sha256=primary["sha256"])
    accepted = global_readiness.evaluate(recipe, {"viva": checked})
    assert (
        "VIVA_AEROBUS:release_not_bound_to_verified_contributing_artifact"
        not in accepted["calendar_blockers"]
    )
    assert not accepted["ready_for_calendar_incorporation"]
    empty = global_readiness.evaluate(recipe, {"viva": {**checked, "contributing_artifacts": []}})
    assert "VIVA_AEROBUS:release_not_bound_to_verified_contributing_artifact" in empty["calendar_blockers"]
    assert empty["quarterly_date"] is None
