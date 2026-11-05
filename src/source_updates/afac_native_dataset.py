"""Closed native AFAC dataset descriptor and replay from original Gold versions.

Only the descriptor reference is carried by the AFAC profile. All artifacts
remain in the candidate's private tmp workspace; canonical Gold uses the same
five hashes when incorporated in the reviewed producer checkout.
"""

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from src.dashboard.market import build_market_payload
from src.parse.afac.market_scope import cells_sha256
from src.source_updates.afac_native_producer import producer_version, verify_preparation, version_at_commit
from src.source_updates.afac_native_replay import binding as dataset_binding
from src.source_updates.afac_native_replay import digest, raw_cells, resolve_workspace, warehouse_cells
from src.source_updates.afac_native_replay import replay as replay_pipeline
from src.source_updates.catalog import ROOT
from src.source_updates.collection import safe_workspace, writer

GOLD = ("fact_carrier_metrics", "dim_carrier", "dim_period", "dim_source_artifact", "bridge_record_lineage")
SCHEMA = "afac_native_dataset_v2"
HASH = re.compile(r"[a-f0-9]{64}")


def seed_filelist(workspace):
    """Portable preparation packet; call before build, with original B Gold."""
    workspace = safe_workspace(Path(workspace))
    selection = json.loads((workspace / "data/afac_native_annual_inputs.json").read_bytes())
    files = [
        workspace / "data/afac_native_annual_inputs.json",
        workspace / "data/afac_native_update.json",
        workspace / "data/bronze/_manifest.jsonl",
        workspace / "data/reference/carrier_crosswalk.csv",
    ]
    files += list((workspace / "data/gold").glob("*.parquet"))
    files += list((workspace / "data/silver").glob("*.parquet"))
    files += [workspace / "baseline-gold" / f"{name}.parquet" for name in GOLD]
    for item in selection["observations"]:
        raw = workspace / "data/bronze" / item["source_file"]
        files.extend([raw, raw.with_suffix(raw.suffix + ".meta.json")])
    if any(not path.is_file() or path.is_symlink() for path in files):
        raise ValueError("Native AFAC preparation seed is incomplete or aliased")
    return sorted({path.relative_to(workspace).as_posix() for path in files})


def _identities(descriptor, repo):
    from src.parse.afac.annual_series import native_metadata

    workspace = resolve_workspace(descriptor["dataset"]["workspace"], repo)
    selection = json.loads((workspace / "data/afac_native_annual_inputs.json").read_bytes())
    entries = [
        json.loads(line) for line in (workspace / "data/bronze/_manifest.jsonl").read_text().splitlines()
    ]
    identities = []
    for item in sorted(selection["observations"], key=lambda row: row["year"]):
        raw = workspace / "data/bronze" / item["source_file"]
        raw.resolve().relative_to((workspace / "data/bronze").resolve())
        if any(path.is_symlink() for path in (raw, *raw.parents)):
            raise ValueError("Native AFAC source identity cannot traverse an alias")
        metadata_file = raw.with_suffix(raw.suffix + ".meta.json")
        metadata = native_metadata(raw)
        if metadata not in entries or metadata["sha256"] != item["sha256"] or digest(raw) != item["sha256"]:
            raise ValueError("Native AFAC selected original differs from its physical capture entry")
        entry = (
            json.dumps(metadata, sort_keys=True, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode()
        identities.append(
            {
                **item,
                "metadata_sha256": digest(metadata_file),
                "capture_entry_sha256": hashlib.sha256(entry).hexdigest(),
            }
        )
    return identities


def source_identities(reference, repo=ROOT):
    return _identities(json.loads(_physical(reference, repo).read_bytes()), repo)


def load_outputs(reference, repo=ROOT):
    """Read the pinned prepared outputs after replay; no regeneration shortcut."""
    descriptor = json.loads(_physical(reference, repo).read_bytes())
    workspace = resolve_workspace(descriptor["dataset"]["workspace"], repo)
    _physical({key: descriptor["warehouse"][key] for key in ("path", "sha256")}, repo)
    selection = json.loads((workspace / "data/afac_native_annual_inputs.json").read_bytes())
    last = max(selection["observations"], key=lambda row: row["year"])
    period = f"{last['year']}M{last['through']:02d}"
    cells = warehouse_cells(workspace, period)
    if cells_sha256(cells) != descriptor["market_cells_sha256"]:
        raise ValueError("Native AFAC prepared warehouse cells changed")
    sources = {}
    for item in selection["observations"]:
        raw = workspace / "data/bronze" / item["source_file"]
        meta = json.loads(raw.with_suffix(raw.suffix + ".meta.json").read_bytes())
        sources[item["year"]] = {
            "sha256": item["sha256"],
            "through": item["through"],
            "downloaded_at": meta["downloaded_at"],
        }
    return build_market_payload(str(workspace / "data/warehouse.duckdb")), cells, sources


def _ref(path, repo=ROOT):
    selected = path.resolve()
    selected.relative_to((repo / "tmp/source-updates").resolve())
    if path.is_symlink() or not selected.is_file():
        raise ValueError("Native AFAC dataset reference must be a regular private candidate file")
    return {"path": selected.relative_to(repo).as_posix(), "sha256": digest(selected)}


def _physical(ref, repo):
    if set(ref) != {"path", "sha256"} or not HASH.fullmatch(ref["sha256"]):
        raise ValueError("Native AFAC dataset requires a closed file reference")
    path = repo / ref["path"]
    if any(item.is_symlink() for item in (path, *path.parents)) or _ref(path, repo) != ref:
        raise ValueError("Native AFAC dataset physical reference changed")
    return path


def _semantic(frame):
    # Exact public row values, including source metadata and original dates.
    return hashlib.sha256(
        frame.to_json(orient="split", date_format="iso", date_unit="ns", double_precision=15).encode()
    ).hexdigest()


def _preservation(before, after):
    non_afac = ~(before.metric_key.eq("passengers_afac") & before.source_system.eq("afac"))
    prior = before.metric_key.eq("passengers_afac") & before.period_id.lt("2019M01")
    after_masks = (
        ~(after.metric_key.eq("passengers_afac") & after.source_system.eq("afac")),
        after.metric_key.eq("passengers_afac") & after.period_id.lt("2019M01"),
    )
    for mask, after_mask in zip((non_afac, prior), after_masks, strict=True):
        retained = after[after_mask].reset_index(drop=True)
        pd.testing.assert_frame_equal(before[mask].reset_index(drop=True), retained, check_exact=True)
    # Every legacy row keeps identity, values, capture and valid_from. Only the
    # closure/current flags of genuinely superseded AFAC versions may change.
    retained = after.set_index("record_id").loc[before.record_id].reset_index()
    immutable = [name for name in before if name not in {"valid_to", "is_current"}]
    pd.testing.assert_frame_equal(
        before[immutable].reset_index(drop=True), retained[immutable], check_exact=True
    )
    return dict(
        non_afac_records=int(non_afac.sum()),
        non_afac_semantic_sha256=_semantic(before[non_afac]),
        pre2019_afac_records=int(prior.sum()),
        pre2019_afac_semantic_sha256=_semantic(before[prior]),
        original_records_retained=len(before),
    )


def _warehouse_semantic(workspace):
    payload = build_market_payload(str(workspace / "data/warehouse.duckdb"))
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def create(workspace, baseline_gold):
    """Retain an audited descriptor after the normal pipeline has completed.

    baseline_gold maps exactly GOLD's five names to untouched original files.
    It never points at an evaluation Gold file to be overwritten.
    """
    workspace = safe_workspace(Path(workspace))
    if set(baseline_gold) != set(GOLD):
        raise ValueError("Native AFAC needs the five exact original Gold baseline tables")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    version = producer_version()
    if version_at_commit(commit) != version:
        raise ValueError("Commit the native AFAC producer code before preparing its data descriptor")
    with writer(workspace):
        saved = workspace / "baseline-gold"
        saved.mkdir(exist_ok=True)
        baseline = {}
        for name in GOLD:
            source = Path(baseline_gold[name])
            target = saved / f"{name}.parquet"
            if source.resolve() == (workspace / "data/gold" / target.name).resolve():
                raise ValueError("Corrected Gold cannot serve as its own original baseline")
            if target.exists() and digest(target) != digest(source):
                raise ValueError("Original Gold baseline copy already differs; use a new candidate")
            if not target.exists():
                shutil.copyfile(source, target)
            baseline[name] = _ref(target)
        gold = {name: _ref(workspace / "data/gold" / f"{name}.parquet") for name in GOLD}
        before = pd.read_parquet(saved / "fact_carrier_metrics.parquet")
        after = pd.read_parquet(workspace / "data/gold/fact_carrier_metrics.parquet")
        preservation = _preservation(before, after)
        selection = json.loads((workspace / "data/afac_native_annual_inputs.json").read_bytes())
        latest = max(selection["observations"], key=lambda row: row["year"])
        period = f"{latest['year']}M{latest['through']:02d}"
        native, gold_cells = raw_cells(workspace, selection), warehouse_cells(workspace, period)
        if native != gold_cells:
            raise ValueError("Native AFAC raw and persistent Gold cells do not agree")
        descriptor = dict(
            schema_version=SCHEMA,
            dataset=dataset_binding(workspace),
            baseline_gold=baseline,
            gold=gold,
            silver=_ref(workspace / "data/silver/afac_monthly_stats.parquet"),
            checks=_ref(workspace / "data/quality/afac_total_checks.parquet"),
            warehouse={
                **_ref(workspace / "data/warehouse.duckdb"),
                "semantic_sha256": _warehouse_semantic(workspace),
            },
            preservation=preservation,
            market_cells_sha256=cells_sha256(gold_cells),
            producer_commit=commit,
            producer_version=version,
        )
        descriptor["source_identities"] = _identities(descriptor, ROOT)
        raw = (json.dumps(descriptor, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode()
        token = hashlib.sha256(raw).hexdigest()
        path = workspace / f"receipts/afac-native-dataset-v2-{token}.json"
        path.parent.mkdir(exist_ok=True)
        if path.exists() and path.read_bytes() != raw:
            raise ValueError("Native AFAC descriptor is immutable; use a new candidate")
        if not path.exists():
            path.write_bytes(raw)
        return _ref(path)


def validate_binding(value):
    """Validate the public identity shape without opening private source files."""
    if (
        set(value)
        != {
            "schema_version",
            "descriptor",
            "gold",
            "silver",
            "checks",
            "baseline_gold",
            "warehouse",
            "preservation",
            "canonical_gold_sha256",
            "market_cells_sha256",
            "producer_commit",
            "producer_version",
            "source_identities",
        }
        or value["schema_version"] != SCHEMA
        or set(value["gold"]) != set(GOLD)
        or set(value["baseline_gold"]) != set(GOLD)
        or set(value["canonical_gold_sha256"]) != set(GOLD)
    ):
        raise ValueError("Unsupported closed native AFAC dataset binding")
    refs = [
        value["descriptor"],
        value["silver"],
        value["checks"],
        *value["gold"].values(),
        *value["baseline_gold"].values(),
    ]
    warehouse = value["warehouse"]
    if set(warehouse) != {"path", "sha256", "semantic_sha256"} or not HASH.fullmatch(
        warehouse["semantic_sha256"]
    ):
        raise ValueError("Native AFAC warehouse needs its retained and regenerable identities")
    refs.append({key: warehouse[key] for key in ("path", "sha256")})
    for ref in refs:
        if (
            set(ref) != {"path", "sha256"}
            or not isinstance(ref["path"], str)
            or not ref["path"].startswith("tmp/source-updates/")
            or ".." in Path(ref["path"]).parts
            or not HASH.fullmatch(ref["sha256"])
        ):
            raise ValueError("Native AFAC binding contains an invalid private artifact reference")
    if value["canonical_gold_sha256"] != {name: ref["sha256"] for name, ref in value["gold"].items()}:
        raise ValueError("Canonical AFAC Gold hashes differ from the verified native output")
    if not HASH.fullmatch(value["market_cells_sha256"]):
        raise ValueError("Native AFAC raw-to-Gold market cells lack their exact digest")
    if not re.fullmatch(r"[a-f0-9]{40}", value["producer_commit"]) or not HASH.fullmatch(
        value["producer_version"]
    ):
        raise ValueError("Native AFAC preparation lacks its committed producer identity")
    identities = value["source_identities"]
    if not identities or [row["year"] for row in identities] != list(range(2019, identities[-1]["year"] + 1)):
        raise ValueError("Native AFAC source identities are not the exact contiguous annual selection")
    for row in identities:
        if (
            set(row)
            != {"year", "through", "source_file", "sha256", "metadata_sha256", "capture_entry_sha256"}
            or not isinstance(row["through"], int)
            or isinstance(row["through"], bool)
            or not 1 <= row["through"] <= 12
            or any(
                not HASH.fullmatch(row[key]) for key in ("sha256", "metadata_sha256", "capture_entry_sha256")
            )
        ):
            raise ValueError("Native AFAC source identity has unsupported fields or hashes")
    proof = value["preservation"]
    if set(proof) != {
        "non_afac_records",
        "non_afac_semantic_sha256",
        "pre2019_afac_records",
        "pre2019_afac_semantic_sha256",
        "original_records_retained",
    }:
        raise ValueError("Native AFAC preservation proof has an unsupported shape")
    if any(
        not isinstance(proof[key], int) or isinstance(proof[key], bool) or proof[key] < 0
        for key in ("non_afac_records", "pre2019_afac_records", "original_records_retained")
    ):
        raise ValueError("Native AFAC preservation counts are invalid")
    if any(
        not HASH.fullmatch(proof[key]) for key in ("non_afac_semantic_sha256", "pre2019_afac_semantic_sha256")
    ):
        raise ValueError("Native AFAC preserved records lack exact semantic hashes")
    return value


def _replay(reference, repo, *, canonical):
    """Rebuild from original Gold, all selected raw inputs and normal contracts."""
    path = _physical(reference, repo)
    descriptor = json.loads(path.read_bytes())
    if set(descriptor) != {
        "schema_version",
        "dataset",
        "baseline_gold",
        "gold",
        "silver",
        "checks",
        "warehouse",
        "preservation",
        "market_cells_sha256",
        "producer_commit",
        "producer_version",
        "source_identities",
    }:
        raise ValueError("Native AFAC descriptor contains unsupported fields")
    result = {
        key: descriptor[key]
        for key in (
            "schema_version",
            "gold",
            "silver",
            "checks",
            "baseline_gold",
            "warehouse",
            "preservation",
            "market_cells_sha256",
            "producer_commit",
            "producer_version",
            "source_identities",
        )
    }
    result.update(
        descriptor=reference,
        canonical_gold_sha256={name: ref["sha256"] for name, ref in descriptor["gold"].items()},
    )
    validate_binding(result)
    verify_preparation(result["producer_commit"], result["producer_version"], repo)
    canonical_paths = _canonical_gold(result, repo) if canonical else []
    if _identities(descriptor, repo) != result["source_identities"]:
        raise ValueError("Native AFAC original identities changed after preparation")
    physical = [
        _physical(ref, repo)
        for ref in [
            result["silver"],
            result["checks"],
            *result["gold"].values(),
            *result["baseline_gold"].values(),
            {key: result["warehouse"][key] for key in ("path", "sha256")},
        ]
    ]
    baseline = {name: _physical(ref, repo) for name, ref in result["baseline_gold"].items()}
    workspace = resolve_workspace(descriptor["dataset"]["workspace"], repo)
    selected = json.loads((workspace / "data/afac_native_annual_inputs.json").read_bytes())["observations"]
    last = max(selected, key=lambda row: row["year"])
    period = f"{last['year']}M{last['through']:02d}"
    _, _, _, report = replay_pipeline(
        descriptor["dataset"], last["sha256"], period, baseline_gold=baseline, repo=repo
    )
    expected = {f"data/gold/{name}.parquet": ref["sha256"] for name, ref in result["gold"].items()}
    expected.update(
        {
            "data/silver/afac_monthly_stats.parquet": result["silver"]["sha256"],
            "data/quality/afac_total_checks.parquet": result["checks"]["sha256"],
        }
    )
    if (
        any(report["native_output_sha256"].get(name) != value for name, value in expected.items())
        or report["native_market_semantic_sha256"] != result["warehouse"]["semantic_sha256"]
        or report["market_cells_sha256"] != result["market_cells_sha256"]
    ):
        raise ValueError("Native AFAC persistent outputs differ from replay of the original Gold and sources")
    proof = _preservation(
        pd.read_parquet(baseline["fact_carrier_metrics"]),
        pd.read_parquet(_physical(result["gold"]["fact_carrier_metrics"], repo)),
    )
    if proof != result["preservation"]:
        raise ValueError("Native AFAC original finance or historical record preservation differs")
    files = [path, *physical, *[workspace / name for name in descriptor["dataset"]["files"]]]
    files.extend(canonical_paths)
    return {"binding": result, "input_files": sorted(set(files))}


def _canonical_gold(binding, repo):
    paths = []
    for name, expected in binding["canonical_gold_sha256"].items():
        relative = f"data/gold/{name}.parquet"
        path = repo / relative
        if not path.is_file() or path.is_symlink() or digest(path) != expected:
            raise ValueError(f"Canonical native AFAC Gold is missing or different: {relative}")
        original = subprocess.check_output(["git", "show", f"HEAD:{relative}"], cwd=repo)
        if hashlib.sha256(original).hexdigest() != expected:
            raise ValueError(f"Canonical native AFAC Gold is not the committed output: {relative}")
        paths.append(path)
    return paths


def replay(reference, repo=ROOT):
    """Publication replay: physical and committed canonical Gold must match."""
    return _replay(reference, repo, canonical=True)


def audit_candidate(reference, repo=ROOT):
    """Private transport audit before canonical incorporation; no publication claim."""
    return _replay(reference, repo, canonical=False)


def materialize_inputs(reference, repo=ROOT):
    from src.source_updates.afac_native_materialize import materialize_inputs as materialize

    return materialize(reference, repo)


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--materialize", type=Path)
    modes.add_argument("--audit", type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    selected = args.materialize or args.audit
    ref = {
        "path": str(selected.relative_to(ROOT)) if selected.is_absolute() else selected.as_posix(),
        "sha256": args.sha256,
    }
    result = materialize_inputs(ref) if args.materialize else audit_candidate(ref)
    print(json.dumps(result, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
