"""Independent merge counterexamples; simulated receipts never certify a source."""

from __future__ import annotations

import copy
import hashlib
import importlib
import json
import shutil
from uuid import uuid4

import pandas as pd
import pytest

from src.pipeline.offline import block_network
from src.source_updates import global_readiness, readiness, retained, retained_round
from src.source_updates.catalog import ROOT
from tests.test_source_update_global_independent import (
    physically_bound_reports,
    selected,
)
from tests.test_source_update_global_independent import (
    recipe as global_recipe,
)
from tests.test_source_update_retained import candidate as legacy_fixture

candidate = legacy_fixture
CUTOFF = "2026-10-24T12:00:00-06:00"
RUN_ID = "c" * 32
# These identities come from the source-family contracts, not the registry under test.
PRODUCTS = [
    ("viva_financials", "viva_financial", "2026Q2"),
    ("fuel", "series", "2026M09"),
    ("banxico", "series", "2026M09"),
    ("equities", "series", "2026Q3"),
    ("gap_traffic", "airport_group", "2026M09"),
    ("asur_traffic", "airport_group", "2026M09"),
    ("bts_segments", "bts", "2026M07"),
    ("aicm_traffic", "government", "2026M08"),
    ("aifa_traffic", "government", "2026M07"),
    ("volaris_sec", "carrier_source", "2026Q2"),
    ("afac_carriers", "carrier_source", "2026M08"),
    ("rss", "rss_retained", "2026M09"),
    ("afac_airports", "retained", "2026M07"),
    ("h10", "h10", "2026M09"),
    ("am_traffic_ir", "am_traffic_ir", "2026M09"),
    ("aerocivil", "aerocivil", "2026M07"),
    ("gdelt", "gdelt", "2026M09"),
]
ADAPTERS = sorted({adapter for _, adapter, _ in PRODUCTS})
MODULES = {
    "viva_financial": "viva_financial_candidate",
    "series": "series_candidate",
    "airport_group": "airport_group_candidate",
    "bts": "bts_candidate",
    "government": "government_candidate",
    "carrier_source": "carrier_source_candidate",
    "rss_retained": "rss_candidate",
    "retained": "retained",
}


@pytest.fixture
def workspace():
    root = ROOT / "tmp/source-updates" / ("reconciliation-independent-" + uuid4().hex)
    with block_network():
        try:
            yield root
        finally:
            shutil.rmtree(root, ignore_errors=True)


def task(root, product, adapter, period):
    return dict(
        id=product,
        product=product,
        adapter=adapter,
        period=period,
        workspace=str(root / "candidates" / product),
        receipt_id=RUN_ID,
        required=True,
        candidate_as_of=CUTOFF,
    )


@pytest.mark.parametrize("product,expected,period", PRODUCTS)
@pytest.mark.parametrize("adapter", ADAPTERS)
def test_every_product_keeps_its_own_complete_adapter(workspace, product, expected, period, adapter):
    proposal = dict(
        version=1,
        as_of=CUTOFF,
        required_items=[product],
        items=[task(workspace, product, adapter, period)],
    )
    if adapter == expected:
        assert readiness.preflight(proposal, workspace / "round")[0]["adapter"] == expected
    else:
        with pytest.raises(ValueError):
            readiness.preflight(proposal, workspace / "round")
    assert not workspace.exists()


@pytest.mark.parametrize(
    "product,roles",
    [
        ("viva_financials", {"pdf": ("viva_ir",), "prior_quarter": ("viva_ir",)}),
        ("fuel", {"workbook": ("eia",)}),
        (
            "banxico",
            {key: ("banxico_sie",) for key in ("SF43718", "SP1", "SF61745", "fix_methodology")},
        ),
        (
            "equities",
            {
                **{ticker: ("yahoo_finance",) for ticker in ("AERO", "VLRS", "RYAAY", "DAL", "ICAGY")},
                "identity": ("sec",),
            },
        ),
        ("gap_traffic", {"html": ("sec", "sec_edgar", "sec_filing")}),
        ("asur_traffic", {"html": ("sec", "sec_edgar", "sec_filing")}),
        ("bts_segments", {"archive": ("bts_t100",)}),
        ("aicm_traffic", {"pdf": ("aicm",)}),
        ("aifa_traffic", {"workbook": ("aifa",)}),
        ("volaris_sec", {role: ("sec",) for role in ("html", "primary", "submissions", "index")}),
        ("afac_carriers", {"pdf": ("afac",), "database": ("afac",)}),
        ("afac_airports", {"workbook": ("afac",)}),
    ],
)
def test_registry_preserves_required_roles_and_exact_aliases(product, roles):
    definition = retained.spec(product)
    assert definition["roles"] == roles
    assert definition["primary"] in roles


@pytest.mark.parametrize("method", ["frames", "run"])
@pytest.mark.parametrize("product,adapter,period", PRODUCTS[:11])
def test_dedicated_products_cannot_use_native_only_certification(
    workspace, monkeypatch, product, adapter, period, method
):
    def forbidden(*args, **kwargs):
        pytest.fail("Incomplete native-only path read a dedicated product's originals")

    monkeypatch.setattr(retained, "originals", forbidden)
    with pytest.raises(ValueError, match="candidate"):
        getattr(retained, method)(workspace / "candidate", product, period, CUTOFF, RUN_ID)
    assert not workspace.exists()


def checker_result():
    """Routing-only stub. It is not evidence of extraction or source availability."""
    return dict(
        status="checks_passed",
        output_sha256={"routing-contract-only": "d" * 64},
        activation="none",
        publication="not_authorized",
        code_files={"routing-contract-only": "e" * 64},
        rows=1,
        scope="synthetic_dispatch_contract",
        lineage={"records_expected": 1, "artifact_count": 1},
        code_head="synthetic-contract-only",
    )


@pytest.mark.parametrize(
    "product,adapter,period",
    [PRODUCTS[i] for i in (0, 1, 4, 6, 7, 9, 11, 12)],
)
def test_replay_keeps_rss_prefix_and_exact_driver(workspace, monkeypatch, product, adapter, period):
    item = task(workspace, product, adapter, period)
    folder = workspace / "candidates" / product
    receipts = folder / "receipts"
    receipts.mkdir(parents=True)
    prefix = "rss-retained" if adapter == "rss_retained" else "retained"
    (receipts / f"{prefix}-{RUN_ID}.json").write_text(json.dumps({"status": "retained_unvalidated"}))
    names = {
        "viva_financial": f"viva-financial-{product}-{period}.json",
        "series": f"series-{product}-{period}.json",
        "airport_group": f"airport-group-{product}-{period}.json",
        "bts": f"bts-{product}-{period}.json",
        "government": f"government-{product}-{period}.json",
        "carrier_source": f"carrier-source-{product}-{period}.json",
        "rss_retained": f"rss-{period}.json",
        "retained": f"certified-{product}-{period}.json",
    }
    accepted = {**checker_result(), "retention_run_id": RUN_ID, "effective_as_of": CUTOFF}
    (receipts / names[adapter]).write_text(json.dumps(accepted))
    calls = []

    def check(*args, **kwargs):
        calls.append((args, kwargs))
        return checker_result()

    module = importlib.import_module("src.source_updates." + MODULES[adapter])
    monkeypatch.setattr(module, "run", check)
    before = readiness.inventory(folder)
    result = readiness.check_task(item, CUTOFF)
    args = (
        (folder, period, CUTOFF, RUN_ID)
        if adapter == "rss_retained"
        else (folder, product, period, CUTOFF, RUN_ID)
    )
    assert calls == [(args, {"check": True})]
    assert result["collection_basis"] == "retained"
    assert result["latest_source_availability_verified"] is False
    assert readiness.inventory(folder) == before


@pytest.mark.parametrize("fail_replay", [False, True])
def test_batch_selects_carrier_retainer_and_all_dedicated_drivers(workspace, monkeypatch, fail_replay):
    """Test dispatch ordering separately from real extraction tests in each family."""
    from src.source_updates import carrier_source_inputs

    chosen = [PRODUCTS[i] for i in (0, 1, 4, 6, 7, 12, 9, 10)]
    calls = []

    def retainer(kind):
        def retain(folder, source, product, originals, *, execute=False):
            calls.append(("retain", kind, product, execute))
            return {"run_id": RUN_ID}

        return retain

    monkeypatch.setattr(retained_round, "retain", retainer("legacy"))
    monkeypatch.setattr(carrier_source_inputs, "retain", retainer("carrier"))
    for adapter in {a for _, a, _ in chosen}:

        def run(*args, _adapter=adapter, **kwargs):
            calls.append(("certify", _adapter, args[1], kwargs))
            if fail_replay and args[1] == "fuel" and kwargs.get("check"):
                raise ValueError("independent replay failure")
            return checker_result()

        if adapter == "retained":
            monkeypatch.setattr(retained_round, "run", run)
        else:
            monkeypatch.setattr(importlib.import_module("src.source_updates." + MODULES[adapter]), "run", run)
    recipe = dict(
        version=1,
        as_of=CUTOFF,
        source_root=str(workspace / "source"),
        items=[dict(product=p, period=m, originals={}) for p, _, m in chosen],
    )
    result = retained_round.execute(recipe, workspace / "batch", write=True)
    executed = chosen[:2] if fail_replay else chosen
    # All static plans precede any writer. No planning call certifies a source.
    planning = [("retain", "carrier" if a == "carrier_source" else "legacy", p, False) for p, a, _ in chosen]
    execution = []
    for product, adapter, _ in executed:
        execution.extend(
            [
                ("retain", "carrier" if adapter == "carrier_source" else "legacy", product, True),
                ("certify", adapter, product, {"execute": True}),
                ("certify", adapter, product, {"check": True}),
            ]
        )
    assert calls == planning + execution
    assert result["activation"] == "none" and result["publication"] == "not_authorized"
    if fail_replay:
        assert result["status"] == "blocked" and result["failed_action"] == "offline_replay"
        assert [r["product"] for r in result["results"]] == ["viva_financials"]
        assert result["remaining_products_not_started"] == len(chosen) - 2
    else:
        assert result["status"] == "checks_passed"
        assert [r["product"] for r in result["results"]] == [p for p, _, _ in chosen]


@pytest.mark.parametrize("product", ["fuel", "banxico", "equities"])
@pytest.mark.parametrize("cadence", ["monthly", "quarterly"])
def test_series_calendar_uncertainty_survives_an_otherwise_complete_synthetic_round(product, cadence):
    value = global_recipe("combined")
    outcomes = physically_bound_reports(value)
    assert global_readiness.evaluate(value, outcomes)["ready_for_calendar_incorporation"]
    key = selected(value, product, cadence)["id"]
    outcomes[key]["source_conditions"] = ["publication_calendar_completeness_not_verified"]
    result = global_readiness.evaluate(value, outcomes)
    assert not result["ready_for_calendar_incorporation"]
    assert f"{key}:observation_calendar_completeness_not_verified" in result["calendar_blockers"]
    assert result["ready_for_automatic_execution"] is False


def test_viva_prior_quarter_native_support_cannot_bind_the_current_release(workspace, monkeypatch):
    from src.source_updates.viva_financial_spec import TABLE

    item = {
        **task(workspace, "viva_financials", "viva_financial", "2026Q2"),
        "cadence": "quarterly",
        "used": True,
        "depends_on": [],
    }
    item.pop("required")
    folder = workspace / "candidates" / "viva_financials"
    gold = folder / "data/gold"
    gold.mkdir(parents=True)
    pd.DataFrame(
        [
            dict(
                artifact_id="prior",
                source_url="https://cdn.investorcloud.net/contract-q1.pdf",
                artifact_sha256="a" * 64,
            ),
            dict(
                artifact_id="current",
                source_url="https://cdn.investorcloud.net/contract-q2.pdf",
                artifact_sha256="b" * 64,
            ),
        ]
    ).to_parquet(gold / "dim_source_artifact.parquet", index=False)
    pd.DataFrame(
        [
            dict(artifact_id="prior", table_name="viva_financial_source_native"),
            dict(artifact_id="current", table_name=TABLE),
        ]
    ).to_parquet(gold / "bridge_record_lineage.parquet", index=False)
    result = checker_result()
    result["output_sha256"] = {
        f"gold/{name}": "c" * 64 for name in ["dim_source_artifact", "bridge_record_lineage"]
    }
    monkeypatch.setattr(readiness, "check_task", lambda *args: copy.deepcopy(result))
    verified = global_readiness.verify(item, workspace / "round")
    assert verified["contributing_artifacts"] == [
        dict(source_url="https://cdn.investorcloud.net/contract-q2.pdf", sha256="b" * 64)
    ]


def test_legacy_actual_fixture_certificate_binds_the_extracted_registry(candidate):
    workspace, _, selected_originals = candidate
    retention = retained.retain(workspace, candidate[1], "afac_airports", selected_originals, execute=True)
    args = (workspace, "afac_airports", "2026M07", CUTOFF, retention["run_id"])
    result = retained.run(*args, execute=True)
    registry = ROOT / "src/source_updates/retained_registry.py"
    assert (
        result["code_files"]["src/source_updates/retained_registry.py"]
        == hashlib.sha256(registry.read_bytes()).hexdigest()
    )
    assert result["rows"] == 42
    assert retained.run(*args, check=True)["output_sha256"] == result["output_sha256"]
