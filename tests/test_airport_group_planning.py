"""Independent planning guards; no source capture or synthetic availability claims."""

import json
from uuid import uuid4

import httpx
import pytest

from src.source_updates import readiness, retained
from src.source_updates.catalog import ROOT

MONTH = "2026M07"
CUTOFF = "2026-10-23T12:00:00-06:00"


@pytest.mark.parametrize("product", ["gap_traffic", "asur_traffic"])
@pytest.mark.parametrize("adapter", ["retained", "government", "airport_group"])
def test_readiness_rejects_cross_family_adapters_before_source_reads(product, adapter):
    root = ROOT / "tmp/source-updates" / ("independent-static-" + uuid4().hex)
    item = dict(
        id="group",
        product=product,
        period=MONTH,
        adapter=adapter,
        workspace=str(root / "source"),
        receipt_id="a" * 32,
        required=True,
        candidate_as_of=CUTOFF,
    )
    proposal = dict(version=1, as_of=CUTOFF, required_items=["group"], items=[item])
    if adapter == "airport_group":
        assert readiness.preflight(proposal, root / "round")[0]["adapter"] == adapter
    else:
        with pytest.raises(ValueError, match="adapter"):
            readiness.preflight(proposal, root / "round")
    item["adapter"] = "airport_group"
    item["period"] = "2026Q3"
    with pytest.raises(ValueError, match="monthly"):
        readiness.preflight(proposal, root / "round")
    assert not root.exists()


@pytest.mark.parametrize("product", ["gap_traffic", "asur_traffic", "aicm_traffic", "aifa_traffic"])
@pytest.mark.parametrize("entrypoint", ["run", "frames"])
def test_generic_path_rejects_every_dedicated_product_before_any_source_read(
    monkeypatch, product, entrypoint
):
    workspace = ROOT / "tmp/source-updates" / ("independent-dedicated-guard-" + uuid4().hex)

    def forbidden(*args, **kwargs):
        pytest.fail("A dedicated product entered the generic source reader")

    monkeypatch.setattr(retained, "originals", forbidden)
    with pytest.raises(ValueError, match="candidate"):
        getattr(retained, entrypoint)(workspace, product, MONTH, CUTOFF, "a" * 32)
    assert not workspace.exists()


@pytest.mark.parametrize("round_kind", ["monthly", "combined"])
def test_airport_family_plan_contains_both_sec_groups_once_in_the_monthly_scope(round_kind):
    from src.source_updates.catalog import plan

    output = plan(round_kind, CUTOFF, "2026Q3" if round_kind == "combined" else None, "airports")
    monthly = [
        (row["id"], row["target_period"]) for row in output["products"] if row["target_cadence"] == "monthly"
    ]
    assert set(monthly) == {
        (p, "2026M09") for p in ["gap_traffic", "asur_traffic", "oma_traffic", "aicm_traffic", "aifa_traffic"]
    }
    assert len(monthly) == 5
    quarterly = [
        (row["id"], row["target_period"])
        for row in output["products"]
        if row["target_cadence"] == "quarterly"
    ]
    assert quarterly == ([("aicm_slots", "2026Q3")] if round_kind == "combined" else [])
    assert output["network_requests"] == output["paid_requests"] == 0
    assert output["writes"] == [] and output["activation"] == "none"


def test_only_airport_products_move_family_while_sec_financials_keep_identity_and_cadence():
    from src.source_updates.catalog import FAMILIES, plan, product_map

    products = product_map()
    assert "sec_edgar" in FAMILIES["corporate"] and "sec_edgar" not in FAMILIES["airports"]
    for product in ["gap_traffic", "asur_traffic"]:
        assert products[product]["family"] == "airports"
        assert products[product]["source_key"] == "sec_edgar" and products[product]["cadence"] == "monthly"
        assert products[product]["parser_step"] == "parse.airports"
    for product in [
        "am_sec",
        "volaris_sec",
        "volaris_traffic_ir",
        "delta_sec",
        "ryanair_sec",
        "am_financials",
        "bmv_xbrl",
        "viva_financials",
    ]:
        assert products[product]["family"] == "corporate"
    corporate = plan("combined", CUTOFF, "2026Q3", "corporate")["products"]
    assert not {"gap_traffic", "asur_traffic"} & {row["id"] for row in corporate}
    assert {
        (row["id"], row["target_cadence"])
        for row in corporate
        if row["id"] in {"am_sec", "volaris_sec", "volaris_traffic_ir"}
    } == {
        ("am_sec", "monthly"),
        ("am_sec", "quarterly"),
        ("volaris_sec", "quarterly"),
        ("volaris_traffic_ir", "monthly"),
    }
    assert products["volaris_traffic_ir"]["source_key"] == "volaris_ir"
    assert products["volaris_sec"]["source_key"] == "sec_edgar"


@pytest.mark.parametrize("round_kind", ["monthly", "combined"])
def test_documented_airport_skill_cli_lists_sec_group_tasks_without_starting_http(
    round_kind, monkeypatch, capsys
):
    from src.source_updates.__main__ import main

    def forbidden(*args, **kwargs):
        pytest.fail("Planning the documented airport skill must never construct an HTTP client")

    monkeypatch.setattr(httpx, "Client", forbidden)
    args = ["plan", "--round", round_kind, "--as-of", CUTOFF, "--family", "airports"]
    if round_kind == "combined":
        args.extend(["--quarter", "2026Q3"])
    assert main(args) == 0
    output = json.loads(capsys.readouterr().out)
    for product in ["gap_traffic", "asur_traffic"]:
        selected = [row for row in output["products"] if row["id"] == product]
        assert len(selected) == 1 and selected[0]["target_period"] == "2026M09"
        assert selected[0]["target_cadence"] == "monthly" and selected[0]["family"] == "airports"
