"""Executable offline certification, revision and immutable-replay contracts."""

import hashlib
import json
import shutil
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates import global_readiness, readiness, retained, series_candidate
from src.source_updates.catalog import ROOT
from tests.test_source_update_series_independent import equities_inputs, fuel_bytes, macro_inputs

CUTOFF = "2026-10-22T12:00:00-06:00"


@contextmanager
def _candidate(product, tmp_path):
    workspace = ROOT / "tmp/source-updates" / ("test-series-" + uuid4().hex)
    source = tmp_path / "bronze"
    inputs = equities_inputs() if product == "equities" else macro_inputs(product)
    selected = {}
    for role, (body, row) in inputs.items():
        _, entity, period, extension = row["logical_key"].split("|")
        path = save_bronze(
            body,
            row["source_system"],
            entity,
            period,
            extension,
            row["source_url"],
            "manual",
            bronze_root=source,
            downloaded_at=datetime(2026, 10, 19, tzinfo=UTC),
        )
        selected[role] = path.relative_to(source).as_posix()
    try:
        yield workspace, source, product, selected
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        shutil.rmtree(workspace.parent / (workspace.name + "-round"), ignore_errors=True)


@pytest.fixture(params=["banxico", "fuel", "equities"])
def candidate(request, tmp_path):
    with _candidate(request.param, tmp_path) as value:
        yield value


def stored(candidate):
    workspace, source, product, selected = candidate
    receipt = retained.retain(workspace, source, product, selected, execute=True)
    return workspace, product, receipt["run_id"]


@pytest.fixture(scope="module", params=["banxico", "fuel", "equities"])
def certified_template(request, tmp_path_factory):
    # Generate each genuine accepted baseline once. Copied candidates retain
    # the exact relative paths, receipt IDs and hashes without rebinding them.
    with _candidate(request.param, tmp_path_factory.mktemp("series-seed")) as value:
        workspace, product, receipt = stored(value)
        series_candidate.run(workspace, product, "2026M09", CUTOFF, receipt, execute=True)
        before = readiness.inventory(workspace)
        yield (workspace, product, receipt), before
        assert readiness.inventory(workspace) == before


@pytest.fixture
def certified_copy(certified_template):
    (seed, product, receipt), expected = certified_template
    workspace = ROOT / "tmp/source-updates" / ("test-series-" + uuid4().hex)
    shutil.copytree(seed, workspace)
    try:
        assert workspace != seed and readiness.inventory(workspace) == expected
        yield workspace, product, receipt
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.parametrize("period", ["2026M09", "2026Q3"])
def test_complete_product_replay_and_global_binding(candidate, period):
    workspace, product, receipt = stored(candidate)
    args = workspace, product, period, CUTOFF, receipt
    assert series_candidate.run(*args)["status"] == "planned_not_executed"
    assert not (workspace / "data/gold").exists()
    result = series_candidate.run(*args, execute=True)
    assert result["lineage"]["status"] == "passed"
    assert set(result["output_sha256"]) == set(series_candidate.output_names(product))
    assert result["paid_requests"] == result["network_requests"] == 0
    assert not result["new_source_capture"] and not result["calendar_completeness_certified"]
    before = readiness.inventory(workspace)
    checked = series_candidate.run(*args, check=True)
    assert checked["output_sha256"] == result["output_sha256"]
    assert readiness.inventory(workspace) == before
    task = {
        "id": "series",
        "product": product,
        "period": period,
        "adapter": "series",
        "workspace": str(workspace),
        "receipt_id": receipt,
        "required": True,
        "candidate_as_of": CUTOFF,
    }
    recipe = {"version": 1, "as_of": CUTOFF, "required_items": ["series"], "items": [task]}
    round_workspace = workspace.parent / (workspace.name + "-round")
    accepted = readiness.execute(recipe, round_workspace, write=True)
    assert accepted["ready_for_review"] and not accepted["ready_for_calendar_incorporation"]
    assert "publication_calendar_completeness_not_verified" in accepted["results"][0]["source_conditions"]
    readiness.execute(recipe, round_workspace, check=True)
    bound = global_readiness.verify({**task, "used": True}, round_workspace)
    assert bound["contributing_artifacts"]
    with pytest.raises(ValueError, match="immutable"):
        series_candidate.run(*args, execute=True)
    # Same physical originals cannot be certified by the older native-only path.
    with pytest.raises(ValueError, match="series_candidate"):
        retained.run(*args, execute=True)


@pytest.mark.parametrize("kind", ["output", "receipt", "source", "sidecar", "code", "cutoff", "run_id"])
def test_exact_replay_rejects_changed_evidence(certified_copy, monkeypatch, kind):
    workspace, product, receipt = certified_copy
    args = [workspace, product, "2026M09", CUTOFF, receipt]
    result = json.loads((workspace / "receipts" / f"series-{product}-2026M09.json").read_text())
    if kind == "output":
        name = next(n for n in result["output_sha256"] if n.startswith("silver/"))
        path = workspace / "data" / (name + ".parquet")
        frame = pd.read_parquet(path)
        frame.loc[0, "source_hash"] = "0" * 64
        frame.to_parquet(path)
    elif kind == "receipt":
        path = workspace / "receipts" / f"series-{product}-2026M09.json"
        changed = json.loads(path.read_text())
        changed["calendar_completeness_certified"] = True
        path.write_text(json.dumps(changed))
    elif kind in {"source", "sidecar"}:
        row = next(
            iter(
                json.loads((workspace / "receipts" / f"retained-{receipt}.json").read_text())[
                    "originals"
                ].values()
            )
        )
        path = workspace / "data/bronze" / row["source_file"]
        if kind == "sidecar":
            path = Path(str(path) + ".meta.json")
        path.write_bytes(b"changed")
    elif kind == "code":
        monkeypatch.setattr(series_candidate, "fingerprints", lambda: {"changed": "a" * 64})
    elif kind == "cutoff":
        args[3] = "2026-10-23T12:00:00-06:00"
    else:
        args[4] = "0" * 32
    before = readiness.inventory(workspace)
    with pytest.raises((ValueError, OSError)):
        series_candidate.run(*args, check=True)
    assert readiness.inventory(workspace) == before


def test_missing_native_roles_reject_before_retention(candidate):
    workspace, source, product, selected = candidate
    # Missing roles reject before any retention, independent of source content.
    with pytest.raises(ValueError, match="exactly"):
        retained.retain(workspace, source, product, {}, execute=True)
    assert not workspace.exists()


def test_baseline_hash_and_metric_revisions(candidate):
    workspace, product, receipt = stored(candidate)
    args = workspace, product, "2026Q3", CUTOFF, receipt
    inputs, _ = retained.originals(workspace, product, receipt, CUTOFF)
    silver, details = series_candidate.read(product, inputs, "2026Q3")
    outputs, _ = series_candidate.frames(workspace, product, "2026Q3", silver, details)
    name = {
        "banxico": "silver/macro_indicators",
        "fuel": "silver/fuel_prices",
        "equities": "silver/market_prices",
    }[product]
    baseline = workspace / "baselines/prior.parquet"
    baseline.parent.mkdir()
    frame = outputs[name].copy()
    column = {"banxico": "value", "fuel": "price_usd_per_gallon", "equities": "adj_close"}[product]
    frame.loc[0, column] += 1
    frame.to_parquet(baseline)
    result = series_candidate.run(*args, execute=True, baseline="baselines/prior.parquet")
    assert result["revisions"]["changed"] == 1
    series_candidate.run(*args, check=True)
    frame.loc[0, column] += 1
    frame.to_parquet(baseline)
    with pytest.raises(ValueError, match="evidence changed"):
        series_candidate.run(*args, check=True)


def test_dry_run_cli_does_not_create_workspace(tmp_path, capsys):
    workspace = ROOT / "tmp/source-updates" / ("series-dry-" + uuid4().hex)
    code = series_candidate.main(
        [
            "certify",
            "--product",
            "banxico",
            "--workspace",
            str(workspace),
            "--period",
            "2026Q3",
            "--as-of",
            CUTOFF,
            "--retention",
            "a" * 32,
            "--dry-run",
        ]
    )
    assert code == 0 and json.loads(capsys.readouterr().out)["status"] == "planned_not_executed"
    assert not workspace.exists()


def test_observed_series_does_not_pass_calendar_even_if_availability_is_asserted():
    recipe = json.loads((ROOT / "config/source_update_global.example.json").read_text())
    recipe["round"] = "monthly"
    recipe["items"] = [
        {
            "id": "fuel",
            "product": "fuel",
            "period": "2026M09",
            "cadence": "monthly",
            "used": True,
            "depends_on": [],
            "adapter": "series",
            "workspace": "unused-in-pure-policy",
            "receipt_id": "a" * 32,
            "candidate_as_of": recipe["as_of"],
        }
    ]
    result = global_readiness.evaluate(
        recipe,
        {
            "fuel": {
                "status": "checks_passed",
                "latest_source_availability_verified": True,
                "source_conditions": ["publication_calendar_completeness_not_verified"],
            }
        },
    )
    assert "fuel:observation_calendar_completeness_not_verified" in result["calendar_blockers"]
    assert not result["ready_for_calendar_incorporation"]


def test_invalid_original_is_retained_but_cannot_create_silver_or_gold(candidate):
    workspace, source, product, selected = candidate
    role = {"banxico": "SF43718", "fuel": "workbook", "equities": "AERO"}[product]
    path = source / selected[role]
    body = path.read_bytes()
    if product == "banxico":
        body = body.replace(b",10\r\n", b",ND\r\n", 1)
    elif product == "fuel":
        body = fuel_bytes([(pd.Timestamp("2026-09-01"), "ND")])
    else:
        chart = json.loads(body)
        chart["chart"]["result"][0]["indicators"]["quote"][0]["close"][0] = None
        body = json.dumps(chart).encode()
    path.write_bytes(body)
    meta = Path(str(path) + ".meta.json")
    row = json.loads(meta.read_text())
    row.update(sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
    meta.write_text(json.dumps(row))
    manifest = source / "_manifest.jsonl"
    rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    rows = [row if item["source_file"] == row["source_file"] else item for item in rows]
    manifest.write_text("".join(json.dumps(item) + "\n" for item in rows))
    saved = retained.retain(workspace, source, product, selected, execute=True)
    with pytest.raises(ValueError):
        series_candidate.run(workspace, product, "2026M09", CUTOFF, saved["run_id"], execute=True)
    assert (workspace / "data/bronze/_manifest.jsonl").exists()
    assert not (workspace / "data/silver").exists()
    assert not (workspace / "data/gold").exists()
    assert not list((workspace / "receipts").glob("series-*.json"))


@pytest.mark.parametrize("product", ["banxico", "fuel", "equities"])
def test_native_only_adapter_cannot_be_used_for_integral_series_recipe(product):
    workspace = ROOT / "tmp/source-updates/static-series-round"
    task = {
        "id": "series",
        "product": product,
        "period": "2026M09",
        "adapter": "retained",
        "workspace": str(workspace.parent / "static-series-source"),
        "receipt_id": "a" * 32,
        "required": True,
        "candidate_as_of": CUTOFF,
    }
    recipe = {"version": 1, "as_of": CUTOFF, "required_items": ["series"], "items": [task]}
    with pytest.raises(ValueError, match="Use series adapter"):
        readiness.preflight(recipe, workspace)


@pytest.mark.parametrize("period", ["2026M09", "2026Q3"])
def test_retained_batch_routes_series_to_integral_certification(candidate, period):
    from src.source_updates.retained_round import execute

    workspace, source, product, selected = candidate
    recipe = {
        "version": 1,
        "as_of": CUTOFF,
        "source_root": str(source),
        "items": [{"product": product, "period": period, "originals": selected}],
    }
    dry = execute(recipe, workspace)
    assert dry["plan"][0]["adapter"] == "series" and not workspace.exists()
    result = execute(recipe, workspace, write=True)
    assert result["status"] == "checks_passed"
    row = result["results"][0]
    assert (
        row["offline_replay_identical"]
        and row["rows"]["gold/fact_market_data" if product == "equities" else "gold/fact_macro"] > 0
    )
    assert row["scope"].startswith("all_observations_in_selected_retained_originals")
    assert result["network_requests"] == 0 and not result["new_source_capture"]


def test_native_macro_revisions_cannot_hide_in_unchanged_aggregates(tmp_path):
    from tests.test_source_update_series_independent import macro_inputs

    inputs = macro_inputs("banxico")
    silver, _ = series_candidate.read("banxico", inputs, "2026Q3")
    baseline = tmp_path / "baselines/prior.parquet"
    baseline.parent.mkdir()
    before = silver["macro_indicators"].copy()
    fix = before.index[before.series_id.eq("SF43718")]
    # Offsetting corrections leave the quarter's mean and close unchanged.
    before.loc[fix[0], "value"] += 1
    before.loc[fix[1], "value"] -= 1
    before.to_parquet(baseline)
    comparison = series_candidate.revisions(
        tmp_path,
        "baselines/prior.parquet",
        "banxico",
        {"silver/macro_indicators": silver["macro_indicators"]},
    )
    assert comparison["changed"] == 2
    assert comparison["baseline_table"] == "silver/macro_indicators"
    assert before.loc[fix, "value"].sum() == silver["macro_indicators"].loc[fix, "value"].sum()
