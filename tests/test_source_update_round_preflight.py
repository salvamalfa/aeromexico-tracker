"""Malformed rounds must stop before constructing HTTP clients or writing files."""

import json
from copy import deepcopy
from uuid import uuid4

import pytest

from src.source_updates.__main__ import main
from src.source_updates.catalog import ROOT
from src.source_updates.rounds import validate_recipe


@pytest.fixture
def recipe():
    return json.loads((ROOT / "config/source_update_round.example.json").read_text())


@pytest.fixture
def workspace():
    target = ROOT / "tmp/source-updates" / ("preflight-not-written-" + uuid4().hex)
    yield target
    assert not target.exists()


@pytest.mark.parametrize(
    "mutation",
    ["unknown_step", "missing_predecessor", "no_checks", "naive_cutoff", "open_period",
     "unsupported_table", "unchecked_product", "empty_values", "catalog_only", "missing_baseline"],
)
@pytest.mark.parametrize("execute", [False, True])
def test_invalid_recipe_precedes_acquisition(
    recipe, workspace, tmp_path, monkeypatch, capsys, mutation, execute
):
    import src.source_updates.__main__ as cli

    if mutation == "unknown_step":
        recipe["steps"] = ["publish.site"]
    elif mutation == "missing_predecessor":
        recipe["steps"] = ["transform.stage6"]
    elif mutation == "no_checks":
        recipe["checks"]["checks"] = []
    elif mutation == "naive_cutoff":
        recipe["checks"]["as_of"] = "2026-10-18T12:00:00"
    elif mutation == "open_period":
        recipe["checks"]["checks"][0]["expected_period"] = "2026M10"
    elif mutation == "unsupported_table":
        recipe["checks"]["checks"][0]["table"] = "airport_traffic"
    elif mutation == "unchecked_product":
        recipe["checks"]["checks"][0].update(product="h10", table="fx_rates")
    elif mutation == "empty_values":
        recipe["checks"]["checks"][0]["value_columns"] = []
    elif mutation == "catalog_only":
        recipe["selection"]["items"][0]["purpose"] = "catalog"
    else:
        recipe["checks"]["checks"][0]["baseline_file"] = "baselines/absent.parquet"
    source = tmp_path / "recipe.json"
    source.write_text(json.dumps(recipe))

    def forbidden(*args, **kwargs):
        raise AssertionError("acquisition called before full round preflight")

    monkeypatch.setattr(cli, "collect", forbidden)
    args = [
        "round", "--recipe", str(source), "--workspace", str(workspace),
        "--execute" if execute else "--dry-run",
    ]
    assert main(args) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"


def test_valid_recipe_preflight_has_no_writes_or_mutation(recipe, workspace):
    before = deepcopy(recipe)
    assert validate_recipe(recipe, workspace) is None
    assert recipe == before
