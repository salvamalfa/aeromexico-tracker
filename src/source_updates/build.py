"""Reuse explicit offline pipeline steps in a separate process and candidate root."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from src.source_updates.catalog import ROOT
from src.source_updates.collection import safe_workspace, writer

# Never expose arbitrary imports, legacy network run(), analytics, model training,
# dashboards, analysis approval or the publication gate through the coordinator.
ALLOWED = frozenset(
    {
        "parse.peer_discovery",
        "parse.sec",
        "parse.aeromexico_ir",
        "parse.aeromexico_ir_financial",
        "parse.bmv",
        "parse.afac",
        "parse.peers",
        "parse.bts",
        "parse.fx",
        "parse.fuel",
        "parse.market",
        "parse.airports",
        "parse.airport_reference",
        "parse.news",
        "transform.stage4",
        "transform.validate_stage4",
        "transform.validate_stage5",
        "transform.validate_silver",
        "transform.stage6",
        "transform.validate_stage6",
    }
)
GRANULAR = {
    "parse.fx": (
        "src.ingest.macro.banxico:build_from_bronze",
        ("banxico_sie", "federal_reserve_h10"),
        ("fx_rates", "macro_indicators"),
    ),
    "parse.fuel": ("src.ingest.macro.fuel:build_from_bronze", ("eia",), ("fuel_prices",)),
    "parse.market": ("src.ingest.market.prices:build_from_bronze", ("yahoo_finance",), ("market_prices",)),
    "parse.airports": (
        "src.ingest.airports.groups:build_from_bronze",
        ("oma_ir", "aicm", "aifa", "sec"),
        ("airport_traffic",),
    ),
    "parse.airport_reference": (
        "src.ingest.airports.reference:build_from_bronze",
        ("ourairports",),
        ("../gold/dim_airport",),
    ),
    "parse.news": ("src.source_updates.news:build_from_bronze", ("rss", "gdelt"), ("news_headlines",)),
}


def build_plan(workspace: Path, steps: list[str]) -> dict:
    workspace = safe_workspace(workspace)
    if not steps or len(steps) != len(set(steps)) or set(steps) - ALLOWED:
        raise ValueError("Select unique, explicitly allowed offline parse/transform steps")
    return {
        "mode": "dry_run",
        "workspace": str(workspace),
        "steps": steps,
        "network_requests": 0,
        "paid_requests": 0,
        "activation": "none",
        "writes": [
            str(workspace / name)
            for name in ("config", "data", "docs", "logs", "receipts", ".source-update.lock")
        ],
        "status": "candidate_build_requires_existing_inputs_and_period_checks",
    }


def build(workspace: Path, steps: list[str], *, execute: bool = False) -> dict:
    planned = build_plan(workspace, steps)
    if not execute:
        return planned
    with writer(workspace):
        # Public config only. No .env, credentials, private snapshot, approved
        # analysis ledger or retained provider artifacts are copied or modified.
        (workspace / "config").mkdir(exist_ok=True)
        for path in (ROOT / "config").glob("*.yaml"):
            destination = workspace / "config" / path.name
            if destination.exists() and destination.read_bytes() != path.read_bytes():
                raise ValueError(f"Candidate config differs: {path.name}; use a new workspace")
            if not destination.exists():
                shutil.copyfile(path, destination)
        reference = ROOT / "data/reference"
        if reference.exists() and not (workspace / "data/reference").exists():
            shutil.copytree(reference, workspace / "data/reference")
        (workspace / "docs").mkdir(exist_ok=True)
        report = workspace / "receipts" / f"build-{uuid4().hex}.json"
        report.parent.mkdir(exist_ok=True)
        completed = subprocess.run(
            [sys.executable, "-m", "src.source_updates.build", str(workspace), ",".join(steps), str(report)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if not report.exists():
            return {
                **planned,
                "mode": "build",
                "status": "failed_before_receipt",
                "returncode": completed.returncode,
            }
        result = json.loads(report.read_text())
        result.update(
            activation="none",
            publication="not_authorized",
            period_acceptance="not_checked",
            returncode=completed.returncode,
        )
        return result


def worker(workspace: Path, requested: list[str], report: Path) -> int:
    build_plan(workspace, requested)
    if not report.resolve().is_relative_to((workspace / "receipts").resolve()):
        raise ValueError("Build receipt must remain inside the candidate workspace")
    # These modules import PATHS by value. Set the candidate root BEFORE loading
    # any parser/transform/registry, in a fresh interpreter for every build.
    import src.config as config

    config.PATHS = config.ProjectPaths(root=workspace)
    config.PATHS.ensure_runtime_directories()
    from dataclasses import replace

    from src.pipeline.model import (
        InputRequirement,
        PipelinePhase,
        PipelineRunError,
        PipelineStep,
        RequirementLevel,
    )
    from src.pipeline.registry import PIPELINE_STEPS
    from src.pipeline.runner import run_pipeline

    registry = {step.step_id: step for step in PIPELINE_STEPS}
    for name, (action, sources, outputs) in GRANULAR.items():
        registry[name] = PipelineStep(
            name,
            PipelinePhase.PARSE,
            name,
            action,
            RequirementLevel.REQUIRED,
            (InputRequirement(name, bronze_source_systems=sources),),
            tuple(f"data/silver/{table}.parquet" for table in outputs),
        )
    # Requested order is deliberate. Selected dependencies must precede children.
    seen = set()
    for name in requested:
        step = registry[name]
        if (set(step.depends_on) & set(requested)) - seen:
            raise ValueError("Selected dependency must precede its consumer")
        seen.add(name)
    selected = [replace(registry[name], requirement=RequirementLevel.REQUIRED) for name in requested]
    try:
        run_pipeline(
            root=workspace,
            steps=selected,
            offline=True,
            report_path=report,
            run_id=report.stem,
            include_dependencies=False,
        )
    except PipelineRunError:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(worker(Path(sys.argv[1]), sys.argv[2].split(","), Path(sys.argv[3])))
