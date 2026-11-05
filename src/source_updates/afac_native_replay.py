"""Physical binding and isolated ordinary-pipeline replay of a native dataset."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path

import duckdb

from src.parse.afac.market_scope import cells_sha256, market_cells
from src.parse.afac.monthly_stats import _load_crosswalk, parse_annual_passenger_workbook
from src.pipeline.offline import block_network
from src.source_updates.build import build
from src.source_updates.catalog import ROOT

STEPS = ["parse.afac_annual", "transform.afac_native", "transform.warehouse"]


def warehouse_cells(workspace, period):
    with duckdb.connect(str(workspace / "data/warehouse.duckdb"), read_only=True) as db:
        rows = db.execute(
            "SELECT f.carrier_key,f.period_id,f.segment,f.value FROM v_carrier_default f "
            "JOIN dim_carrier d ON f.carrier_key=d.carrier_key "
            "WHERE f.metric_key='passengers_afac' AND f.period_type='month' "
            "AND f.period_id BETWEEN '2019M01' AND ? AND d.country IN ('Mexico','MX')",
            [period],
        ).fetchall()
    cells = {(key, month, segment): float(value) for key, month, segment, value in rows}
    if len(cells) != len(rows):
        raise ValueError("Native AFAC warehouse repeats a consolidated Mexican cell")
    return cells


def raw_cells(workspace, selection):
    cells = {}
    crosswalk = _load_crosswalk(workspace / "data/reference/carrier_crosswalk.csv")
    for row in selection["observations"]:
        facts, checks = parse_annual_passenger_workbook(
            workspace / "data/bronze" / row["source_file"], row["year"]
        )
        values, _ = market_cells(facts, checks, row["year"], row["through"], crosswalk)
        cells.update(values)
    return cells


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def resolve_workspace(relative, repo=ROOT):
    if (
        not isinstance(relative, str)
        or not relative.startswith("tmp/source-updates/")
        or ".." in Path(relative).parts
    ):
        raise ValueError("Native AFAC dataset workspace must be a canonical repo-relative candidate path")
    selected = repo / relative
    target = selected.resolve()
    target.relative_to((repo / "tmp/source-updates").resolve())
    if any(path.is_symlink() for path in (selected, *selected.parents)):
        raise ValueError("Native AFAC dataset workspace cannot traverse a symlink")
    return target


def binding(workspace, repo=ROOT):
    workspace = Path(workspace).resolve()
    relative = workspace.relative_to(repo.resolve()).as_posix()
    workspace = resolve_workspace(relative, repo)
    files = [
        workspace / "data/afac_native_annual_inputs.json",
        workspace / "data/afac_native_update.json",
        workspace / "data/bronze/_manifest.jsonl",
        workspace / "data/silver/bts_t100_segment.parquet",
        workspace / "data/reference/carrier_crosswalk.csv",
    ]
    files += sorted((workspace / "data/gold").glob("*.parquet"))
    files += sorted((workspace / "data/silver").glob("*.parquet"))
    for row in (json.loads(line) for line in files[2].read_text().splitlines()):
        raw = workspace / "data/bronze" / row["source_file"]
        raw.resolve().relative_to((workspace / "data/bronze").resolve())
        files.extend((raw, raw.with_suffix(raw.suffix + ".meta.json")))
    for path in files:
        if any(item.is_symlink() for item in (path, *path.parents)) or not path.is_file():
            raise ValueError("Native AFAC dataset requires regular physical inputs")
    return {
        "workspace": relative,
        "files": {path.relative_to(workspace).as_posix(): digest(path) for path in sorted(set(files))},
    }


def replay(dataset, source_hash, period, *, baseline_gold=None, repo=ROOT):
    if set(dataset) != {"workspace", "files"}:
        raise ValueError("Native AFAC dataset requires its exact physical binding")
    workspace = resolve_workspace(dataset["workspace"], repo)
    if binding(workspace, repo) != dataset:
        raise ValueError("Native AFAC dataset changed after its source profile was pinned")
    selection = json.loads((workspace / "data/afac_native_annual_inputs.json").read_bytes())
    selected = [row for row in selection["observations"] if row["year"] == int(period[:4])]
    if (
        len(selected) != 1
        or selected[0]["sha256"] != source_hash
        or selected[0]["through"] != int(period[-2:])
    ):
        raise ValueError("Native AFAC dataset does not select the certified source edition")
    if max(row["year"] for row in selection["observations"]) != int(period[:4]):
        raise ValueError("An older AFAC arrival cannot remove a later native dataset year")
    scratch = repo / "tmp/source-updates"
    scratch.mkdir(parents=True, exist_ok=True)
    with block_network(), tempfile.TemporaryDirectory(prefix="afac-native-replay-", dir=scratch) as directory:
        candidate = Path(directory)
        shutil.copytree(workspace / "data", candidate / "data")
        if baseline_gold is not None:
            for name, path in baseline_gold.items():
                shutil.copyfile(path, candidate / "data/gold" / f"{name}.parquet")
        report = build(candidate, STEPS, execute=True)
        if report.get("status") != "completed" or report.get("returncode") != 0:
            raise ValueError(f"Native AFAC ordinary pipeline failed: {report}")
        from src.web_export.__main__ import main as export

        destination = candidate / "export"
        status = export(
            [
                "--only",
                "market",
                "--database",
                str(candidate / "data/warehouse.duckdb"),
                "--out",
                str(destination),
            ]
        )
        if status != 0 or {path.name for path in destination.iterdir()} != {"market.json"}:
            raise ValueError("Native AFAC generic exporter did not produce exactly one Market payload")
        payload = json.loads((destination / "market.json").read_bytes())
        if payload["metadata"]["last_period"] != period:
            raise ValueError("Native AFAC warehouse coverage differs from its source arrival")
        # Use the same consolidated cells that feed Market. The source parser
        # already reconciled their literal Mexican TOTALs before Gold.
        cells = {}
        for row in payload["months"]:
            for segment, block in row["segments"].items():
                for key, value in block["carriers"].items():
                    cells[(key, row["period_id"], segment)] = value["passengers"]
                cells[("MARKET_TOTAL_MX", row["period_id"], segment)] = block["mexican_carriers_passengers"]
        sources = {}
        for row in selection["observations"]:
            source = workspace / "data/bronze" / row["source_file"]
            meta = json.loads(source.with_suffix(source.suffix + ".meta.json").read_bytes())
            sources[row["year"]] = {
                "sha256": row["sha256"],
                "downloaded_at": meta["downloaded_at"],
                "through": row["through"],
            }
        if binding(workspace, repo) != dataset:
            raise ValueError("Native AFAC physical dataset changed during isolated replay")
        report["native_output_sha256"] = {
            path.relative_to(candidate).as_posix(): digest(path)
            for path in [
                *(candidate / "data/gold").glob("*.parquet"),
                candidate / "data/silver/afac_monthly_stats.parquet",
                candidate / "data/quality/afac_total_checks.parquet",
            ]
        }
        report["native_market_semantic_sha256"] = hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
        ).hexdigest()
        native_cells = raw_cells(workspace, selection)
        gold_cells = warehouse_cells(candidate, period)
        if native_cells != gold_cells:
            raise ValueError("Native AFAC raw cells differ from persistent consolidated Gold/warehouse cells")
        report["market_cells_sha256"] = cells_sha256(gold_cells)
        return payload, cells, sources, report
