"""Immutable public B, typed field ownership and private closure; no authority writes."""

import copy
import json
import subprocess
from pathlib import Path

import pytest

from src.publish import afac_history_contract as contract
from src.publish import afac_history_members as members
from src.publish import afac_history_parent as parent

ROOT = Path(__file__).resolve().parents[1]
PARENT = "842d140a983f785e9d39e7d3d378fdfebe79981e"
SCOPE = "708bedf937af692fc87de96cace34cbf55269ea27fb5b7196d74b31bcd026695"


@pytest.fixture(scope="module")
def public_parent():
    manifest, raw, files = contract.site_tree(ROOT, PARENT)
    spec = json.loads(
        contract.transport._git(ROOT, "show", f"{manifest['code_commit']}:{contract.PARENT_ANCHOR}")
    )
    value = {
        "kind": contract.PARENT_KIND,
        "site_commit": PARENT,
        "manifest_sha256": contract.sha(raw),
        "code_commit": manifest["code_commit"],
        "source_implementation_commit": contract.ORIGINAL_IMPLEMENTATION,
        "producer_code_version": contract.ORIGINAL_PRODUCER,
        "scope_sha256": contract.canonical_digest(spec["scope"]),
        "proof": contract.pins({contract.PARENT_PROOF: files[contract.PARENT_PROOF]})[0],
    }
    return value, manifest, raw, files, spec


def test_real_original_unserved_parent_has_eight_unchanged_identities(public_parent):
    value, manifest, raw, files, spec = public_parent
    assert value["scope_sha256"] == SCOPE
    assert value["manifest_sha256"] == "61f6fab632088ee4c316515da397b78969cfada6c9ec098a8407ad3d9aef7729"
    assert contract.parent_public(ROOT, value) == (manifest, raw, files, spec)
    assert len(manifest["analysis_manifest"]) == 8
    assert {entry["period_id"] for entry in manifest["analysis_manifest"]} == {"2026Q2", "2026Q3"}
    assert spec["baseline_commit"] != PARENT


@pytest.mark.parametrize(
    "field,value",
    [
        ("kind", "served_baseline"),
        ("producer_code_version", "c" * 64),
        ("scope_sha256", "0" * 64),
        ("manifest_sha256", "0" * 64),
        ("source_implementation_commit", "5e09a8eb16105257d2377c8c7b7418ad94b36a1f"),
        ("code_commit", PARENT),
        ("proof", {"path": contract.PROOF, "sha256": "0" * 64, "bytes": 1}),
    ],
)
def test_parent_identity_cannot_be_relabelled(public_parent, field, value):
    candidate = copy.deepcopy(public_parent[0])
    candidate[field] = value
    with pytest.raises((ValueError, KeyError, subprocess.CalledProcessError)):
        contract.parent_public(ROOT, candidate)


def bts_binding():
    ref = {"path": "data/bronze/original.zip", "sha256": "a" * 64, "metadata_sha256": "b" * 64}
    return {
        "product": members.COMPARISONS,
        "period": "2026M07",
        "current": ref,
        "previous": {**ref, "path": "data/bronze/previous.zip"},
        "historical_baseline": contract.ORIGINAL_IMPLEMENTATION,
        "crosswalk": {"path": "config/carrier_crosswalk.csv", "sha256": "c" * 64},
    }


@pytest.mark.parametrize("mutation", ["no_crosswalk", "unknown", "csv_path", "csv_sha", "period", "baseline"])
def test_comparison_source_binding_is_closed(mutation):
    value = bts_binding()
    members.validate_binding(members.COMPARISONS, value, {})
    if mutation == "no_crosswalk":
        del value["crosswalk"]
    elif mutation == "unknown":
        value["allow_arbitrary_patch"] = True
    elif mutation == "csv_path":
        value["crosswalk"]["path"] = "tmp/other.csv"
    elif mutation == "csv_sha":
        value["crosswalk"]["sha256"] = "bad"
    elif mutation == "period":
        value["period"] = "2026M08"
    else:
        value["historical_baseline"] = PARENT
    with pytest.raises(ValueError):
        members.validate_binding(members.COMPARISONS, value, {})


def test_afac_binding_binds_actual_cell_projection_and_zone(monkeypatch):
    from types import SimpleNamespace

    # Only the not-yet-integrated Gold adapter is a synthetic boundary here.
    # The final private Linux replay must load its actual closed implementation.
    dataset_binding = {"synthetic_gold_manifest_sha256": "e" * 64}

    def validate_dataset(value):
        if value != dataset_binding:
            raise ValueError("Synthetic typed dataset differs")

    original_import = members.importlib.import_module
    monkeypatch.setattr(
        members.importlib,
        "import_module",
        lambda name: (
            SimpleNamespace(validate_binding=validate_dataset)
            if name == "src.source_updates.afac_native_dataset"
            else original_import(name)
        ),
    )
    projection = {"cells": [{"value": 2}]}
    value = {
        "product": contract.PRODUCT,
        "period": contract.PERIOD,
        "receipt_id": "a" * 64,
        "candidate_as_of": "2026-11-04T18:00:00+00:00",
        "native_dataset": dataset_binding,
        "output_sha256": {"afac_history_native_cells": contract.sha(contract.encoded(projection))},
    }
    members.validate_binding(contract.PRODUCT, value, projection)
    missing = copy.deepcopy(value)
    del missing["native_dataset"]
    with pytest.raises(ValueError, match="AFAC binding"):
        members.validate_binding(contract.PRODUCT, missing, projection)
    wrong = copy.deepcopy(value)
    wrong["native_dataset"] = {"untyped_raw_overwrite": True}
    with pytest.raises(ValueError, match="typed dataset"):
        members.validate_binding(contract.PRODUCT, wrong, projection)
    with pytest.raises(ValueError, match="projection"):
        members.validate_binding(contract.PRODUCT, value, {"cells": []})
    value["candidate_as_of"] = "2026-11-04T18:00:00"
    with pytest.raises(ValueError, match="zone"):
        members.validate_binding(contract.PRODUCT, value, projection)


def test_missing_normal_gold_adapter_has_no_permissive_fallback(monkeypatch):
    def missing(_):
        raise ModuleNotFoundError("Synthetic unavailable normal dataset implementation")

    monkeypatch.setattr(members.importlib, "import_module", missing)
    value = {
        "product": contract.PRODUCT,
        "period": contract.PERIOD,
        "receipt_id": "a" * 64,
        "candidate_as_of": "2026-11-04T18:00:00Z",
        "output_sha256": {"afac_history_native_cells": contract.sha(contract.encoded({}))},
        "native_dataset": {"arbitrary": "not accepted"},
    }
    with pytest.raises(ValueError, match="normal closed AFAC native dataset adapter is required"):
        members.validate_binding(contract.PRODUCT, value, {})


def route_payload():
    return {
        "period": "2026M07",
        "routes": [
            {
                "market_key": "GDL<>ONT",
                "departures": 150,
                "passengers": 42,
                "seats": 50,
                "previous": {"departures": None},
                "eligibility": {"eligible": False, "reason": "after_cutoff"},
                "flight_components": [
                    {"source_label": "Estados Unidos · BTS T-100", "service_class_departures": {"F": 150}}
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    "mutation",
    ["current", "pax", "seats", "eligibility", "charter", "anac", "fraction", "negative", "route", "extra"],
)
def test_bts_granular_boundary_rejects_other_facts(mutation):
    name = sorted(members.BTS_TARGETS)[0]
    original = route_payload()
    corrected = copy.deepcopy(original)
    corrected["routes"][0]["previous"]["departures"] = 124
    members.bts_boundary({name: contract.encoded(original)}, {name: contract.encoded(corrected)})
    row = corrected["routes"][0]
    if mutation in {"current", "pax", "seats"}:
        row[{"current": "departures", "pax": "passengers", "seats": "seats"}[mutation]] += 1
    elif mutation == "eligibility":
        row["eligibility"]["eligible"] = True
    elif mutation in {"fraction", "negative"}:
        row["previous"]["departures"] = 0.5 if mutation == "fraction" else -1
    elif mutation in {"charter", "anac"}:
        original["routes"][0]["flight_components"][0].update(
            {"service_class_departures": {"L": 150}} if mutation == "charter" else {"source_label": "ANAC"}
        )
        corrected["routes"][0]["flight_components"] = copy.deepcopy(
            original["routes"][0]["flight_components"]
        )
    elif mutation == "route":
        row["market_key"] = "MEX<>ONT"
    else:
        corrected["routes"].append(copy.deepcopy(row))
    with pytest.raises(ValueError):
        members.bts_boundary({name: contract.encoded(original)}, {name: contract.encoded(corrected)})


def test_bts_comparison_cannot_replace_preexisting_value():
    name = sorted(members.BTS_TARGETS)[0]
    old, new = route_payload(), route_payload()
    old["routes"][0]["previous"]["departures"] = 124
    new["routes"][0]["previous"]["departures"] = 125
    with pytest.raises(ValueError):
        members.bts_boundary({name: contract.encoded(old)}, {name: contract.encoded(new)})


def test_afac_boundary_preserves_every_non_monthly_key():
    old = {
        contract.TARGETS[0]: contract.encoded({"monthly_passengers": [], "corporate_peer": {"ask": 123}}),
        contract.TARGETS[1]: contract.encoded({"months": []}),
    }
    new = {
        **old,
        contract.TARGETS[0]: contract.encoded({"monthly_passengers": [1], "corporate_peer": {"ask": 123}}),
    }
    contract.output_boundary(old, new)
    new[contract.TARGETS[0]] = contract.encoded({"monthly_passengers": [1], "corporate_peer": {"ask": 124}})
    with pytest.raises(ValueError, match="protected"):
        contract.output_boundary(old, new)


def original_inventory(tmp_path, names=None):
    names = names or ["data/warehouse.db", "tmp/request.json"]
    root = tmp_path / "tmp/original"
    files = []
    for name in names:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = b"original physical input"
        path.write_bytes(raw)
        files.append({"path": name, "sha256": contract.sha(raw), "bytes": len(raw)})
    inventory = {"schema_version": "afac_history_parent_inputs_v1", "files": files}
    path = tmp_path / "inventory.json"
    path.write_bytes(contract.encoded(inventory))
    return {
        "root": "tmp/original",
        "inventory": {"path": "inventory.json", "sha256": contract.sha(path.read_bytes())},
        "request": {"path": names[-1], "sha256": files[-1]["sha256"]},
    }


@pytest.mark.parametrize(
    "mutation", ["code", "ledger", "traversal", "hash", "size", "duplicate", "order", "request_outside"]
)
def test_original_snapshot_cannot_overwrite_producer_or_authority(tmp_path, mutation):
    inputs = original_inventory(tmp_path)
    inventory_path = tmp_path / "inventory.json"
    inventory = json.loads(inventory_path.read_bytes())
    if mutation in {"code", "ledger", "traversal"}:
        inventory["files"][0]["path"] = {
            "code": "src/config.py",
            "ledger": "analysis_runs/lifecycle/head.json",
            "traversal": "../secrets",
        }[mutation]
    elif mutation == "hash":
        inventory["files"][0]["sha256"] = "0" * 64
    elif mutation == "size":
        inventory["files"][0]["bytes"] += 1
    elif mutation == "duplicate":
        inventory["files"].append(inventory["files"][0])
    elif mutation == "order":
        inventory["files"].reverse()
    else:
        request = tmp_path / "tmp/original/tmp/outside.json"
        request.write_bytes(b"outside")
        inputs["request"] = {"path": "tmp/outside.json", "sha256": contract.sha(b"outside")}
    inventory_path.write_bytes(contract.encoded(inventory))
    inputs["inventory"]["sha256"] = contract.sha(inventory_path.read_bytes())
    with pytest.raises(ValueError):
        parent.parent_inventory(tmp_path, inputs)


def test_inventory_is_physical_and_contains_original_request(tmp_path):
    inputs = original_inventory(tmp_path)
    root, request, files = parent.parent_inventory(tmp_path, inputs)
    assert request == root / "tmp/request.json"
    assert len(files) == 2
    (root / "data/warehouse.db").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="changed"):
        parent.parent_inventory(tmp_path, inputs)


@pytest.fixture
def canonical_gold_repo(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    expected = {}
    for name in members.CANONICAL_GOLD:
        path = tmp_path / f"data/gold/{name}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        # Hash-boundary fixture, deliberately no claim that these bytes are
        # native data or a parsed parquet dataset. The native adapter tests that.
        raw = f"synthetic physical Gold DATA fixture {name}".encode()
        path.write_bytes(raw)
        expected[name] = contract.sha(raw)
    subprocess.run(["git", "add", "data/gold"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "synthetic canonical Gold hash fixture",
        ],
        cwd=tmp_path,
        check=True,
    )
    units = [
        {"product": members.COMPARISONS},
        {
            "product": contract.PRODUCT,
            "source_binding": {"native_dataset": {"canonical_gold_sha256": expected}},
        },
    ]
    return tmp_path, units


def test_canonical_gold_data_closure_is_exact_physical_and_committed(canonical_gold_repo):
    repo, units = canonical_gold_repo
    observed = members.canonical_gold(repo, units)
    assert set(observed) == {f"data/gold/{name}.parquet" for name in members.CANONICAL_GOLD}
    assert {Path(name).stem: pin["sha256"] for name, pin in observed.items()} == units[1]["source_binding"][
        "native_dataset"
    ]["canonical_gold_sha256"]


@pytest.mark.parametrize("mutation", ["physical", "head", "extra", "missing", "digest"])
def test_canonical_gold_cannot_be_an_untracked_or_arbitrary_source_overwrite(canonical_gold_repo, mutation):
    repo, units = canonical_gold_repo
    expected = units[1]["source_binding"]["native_dataset"]["canonical_gold_sha256"]
    path = repo / "data/gold/fact_carrier_metrics.parquet"
    if mutation in {"physical", "head"}:
        path.write_bytes(b"uncommitted new data")
        if mutation == "head":
            expected["fact_carrier_metrics"] = contract.sha(path.read_bytes())
    elif mutation == "extra":
        expected["frozen_model_evaluation_gold"] = "0" * 64
    elif mutation == "missing":
        del expected["fact_carrier_metrics"]
    else:
        expected["fact_carrier_metrics"] = "bad"
    with pytest.raises(ValueError):
        members.canonical_gold(repo, units)


@pytest.mark.parametrize("mutation", ["prepare_mode", "adapter", "reorder", "duplicate", "period", "product"])
def test_gate_never_selects_native_preparation_or_a_request_defined_adapter(mutation):
    selections = [
        {
            "product": product,
            "period": members.ADAPTERS[product][1],
            "profile": {"path": f"tmp/{index}.json", "sha256": "a" * 64},
        }
        for index, product in enumerate(members.ORDER)
    ]
    members.selections({"native_sources": selections})
    if mutation == "prepare_mode":
        selections[1]["mode"] = "prepare_candidate"
    elif mutation == "adapter":
        selections[1]["adapter"] = "src.source_updates.afac_native_dataset.audit_candidate"
    elif mutation == "reorder":
        selections.reverse()
    elif mutation == "duplicate":
        selections[1] = copy.deepcopy(selections[0])
    elif mutation == "period":
        selections[1]["period"] = "2026M10"
    else:
        selections[1]["product"] = "free_json_patch"
    with pytest.raises(ValueError):
        members.selections({"native_sources": selections})
