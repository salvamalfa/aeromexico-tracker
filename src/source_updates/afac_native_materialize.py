"""Materialize only regenerable AFAC inputs and the canonical warehouse at L."""

import json
import shutil

from src.source_updates.catalog import ROOT


def materialize_inputs(reference, repo=ROOT):
    from src.parse.afac.market_scope import cells_sha256
    from src.source_updates.afac_native_dataset import (
        _canonical_gold,
        _physical,
        digest,
        source_identities,
        validate_binding,
    )
    from src.source_updates.afac_native_producer import verify_preparation
    from src.source_updates.afac_native_replay import binding as dataset_binding
    from src.source_updates.afac_native_replay import resolve_workspace, warehouse_cells

    if repo.resolve() != ROOT.resolve():
        raise ValueError("Materialize native AFAC inputs from the producer checkout's own Python entrypoint")
    descriptor = json.loads(_physical(reference, repo).read_bytes())
    binding = {
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
    binding.update(
        descriptor=reference,
        canonical_gold_sha256={name: ref["sha256"] for name, ref in descriptor["gold"].items()},
    )
    validate_binding(binding)
    verify_preparation(binding["producer_commit"], binding["producer_version"], repo)
    _canonical_gold(binding, repo)
    workspace = resolve_workspace(descriptor["dataset"]["workspace"], repo)
    if dataset_binding(workspace, repo) != descriptor["dataset"]:
        raise ValueError("Native AFAC preparation packet changed before materialization")
    source_identities(reference, repo)
    selection_file = workspace / "data/afac_native_annual_inputs.json"
    selection = json.loads(selection_file.read_bytes())
    manifest = repo / "data/bronze/_manifest.jsonl"
    entries = [json.loads(line) for line in manifest.read_text().splitlines()] if manifest.is_file() else []
    for item in selection["observations"]:
        source = workspace / "data/bronze" / item["source_file"]
        destination = repo / "data/bronze" / item["source_file"]
        destination.resolve().relative_to((repo / "data/bronze").resolve())
        metadata = json.loads(source.with_suffix(source.suffix + ".meta.json").read_bytes())
        if destination.exists() and digest(destination) != item["sha256"]:
            raise ValueError("Canonical Bronze original already differs; do not overwrite its capture")
        sidecar = destination.with_suffix(destination.suffix + ".meta.json")
        if sidecar.exists() and json.loads(sidecar.read_bytes()) != metadata:
            raise ValueError("Canonical Bronze original sidecar already differs")
    for item in selection["observations"]:
        source = workspace / "data/bronze" / item["source_file"]
        destination = repo / "data/bronze" / item["source_file"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(source, destination)
        sidecar = destination.with_suffix(destination.suffix + ".meta.json")
        if not sidecar.exists():
            shutil.copyfile(source.with_suffix(source.suffix + ".meta.json"), sidecar)
        metadata = json.loads(sidecar.read_bytes())
        if metadata not in entries:
            entries.append(metadata)
    manifest.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in entries), encoding="utf-8"
    )
    shutil.copyfile(selection_file, repo / "data/afac_native_annual_inputs.json")
    from src.parse.afac.annual_series import run
    from src.transform.stage6_warehouse import build_warehouse

    result = run()  # Normal parser/contract, only Silver and TOTAL checks.
    if (
        digest(repo / "data/silver/afac_monthly_stats.parquet") != binding["silver"]["sha256"]
        or digest(repo / "data/quality/afac_total_checks.parquet") != binding["checks"]["sha256"]
    ):
        raise ValueError("Canonical AFAC Silver/checks differ from the verified preparation")
    build_warehouse(max_stage=9)
    last = max(selection["observations"], key=lambda row: row["year"])
    period = f"{last['year']}M{last['through']:02d}"
    if cells_sha256(warehouse_cells(repo, period)) != binding["market_cells_sha256"]:
        raise ValueError("Canonical AFAC warehouse differs from verified raw/Gold cells")
    _canonical_gold(binding, repo)
    return dict(
        status="native_afac_inputs_materialized_no_gold_writes",
        validation=result,
        market_cells_sha256=binding["market_cells_sha256"],
        warehouse_sha256=digest(repo / "data/warehouse.duckdb"),
    )
