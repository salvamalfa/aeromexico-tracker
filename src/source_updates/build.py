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
        "parse.afac",
        "parse.bmv",
        "parse.complementary",
        "parse.peers",
        "parse.bts",
        "parse.fx",
        "parse.h10",
        "parse.fuel",
        "parse.market",
        "parse.market_chart",
        "parse.airports",
        "parse.airport_reference",
        "parse.news",
        "transform.stage4",
        "transform.validate_stage4",
        "transform.validate_stage5",
        "transform.validate_silver",
        "transform.stage6",
        "transform.validate_stage6",
        "transform.gold_lineage",
    }
)
GRANULAR = {
    "parse.market_chart": (
        "src.source_updates.market:build_from_charts",
        ("yahoo_finance",),
        ("market_prices",),
    ),
    "parse.bmv": (
        "src.source_updates.bmv:parse_selected",
        ("bmv",),
        ("bmv_financials", "bmv_packages_index"),
    ),
    "transform.gold_lineage": (
        "src.source_updates.gold:materialize_lineage",
        (),
        ("../gold/dim_source_artifact", "../gold/bridge_record_lineage"),
    ),
    "parse.fx": (
        "src.ingest.macro.banxico:build_from_bronze",
        ("banxico_sie",),
        ("fx_rates", "macro_indicators"),
    ),
    "parse.fuel": ("src.ingest.macro.fuel:build_from_bronze", ("eia",), ("fuel_prices",)),
    "parse.h10": (
        "src.source_updates.adapters:parse_h10",
        ("federal_reserve_h10",),
        ("fx_rates", "macro_indicators"),
    ),
    "parse.market": ("src.ingest.market.prices:build_from_bronze", ("yahoo_finance",), ("market_prices",)),
    "parse.airports": (
        "src.ingest.airports.groups:build_from_bronze",
        ("oma_ir", "aicm", "aifa", "sec", "sec_edgar", "sec_filing"),
        ("airport_traffic",),
    ),
    "parse.airport_reference": (
        "src.ingest.airports.reference:build_from_bronze",
        ("ourairports",),
        ("../gold/dim_airport",),
    ),
    "parse.news": ("src.source_updates.news:build_from_bronze", ("rss", "gdelt"), ("news_headlines",)),
}


def required_predecessors(steps: list[str]) -> dict[str, tuple[str, ...]]:
    from src.pipeline.registry import PIPELINE_STEPS

    dependencies = {step.step_id: step.depends_on for step in PIPELINE_STEPS}
    dependencies.update({name: () for name in GRANULAR})
    dependencies["parse.complementary"] = ("parse.sec",)
    dependencies["transform.gold_lineage"] = ("transform.validate_stage6",)
    # This granular parser accepts preserved SEC evidence as an explicit file
    # input. If SEC is rebuilt in this run, it must precede the market parser.
    dependencies["parse.market"] = ("parse.sec",) if "parse.sec" in steps else ()
    dependencies["parse.market_chart"] = tuple(
        name for name in ("parse.sec", "parse.complementary") if name in steps
    )
    seen = set()
    for name in steps:
        missing = set(dependencies[name]) - seen
        if missing:
            unavailable = sorted(missing - ALLOWED)
            detail = f"; unavailable in this candidate runner: {unavailable}" if unavailable else ""
            raise ValueError(f"{name} requires earlier pipeline steps: {sorted(missing)}{detail}")
        seen.add(name)
    return {name: dependencies[name] for name in steps}


def build_plan(workspace: Path, steps: list[str]) -> dict:
    workspace = safe_workspace(workspace)
    if not steps or len(steps) != len(set(steps)) or set(steps) - ALLOWED:
        raise ValueError("Select unique, explicitly allowed offline parse/transform steps")
    dependencies = required_predecessors(steps)
    return {
        "mode": "dry_run",
        "workspace": str(workspace),
        "steps": steps,
        "required_predecessors": dependencies,
        "prerequisites": {
            name: requirements
            for name, requirements in {
                "parse.fx": ["All three Banxico CSVs: SF43718, SP1, SF61745; H.10 uses separate parse.h10"],
                "parse.market": [
                    "Candidate data/silver/sec_report_text.parquet from preserved SEC evidence",
                    "Normalized Yahoo CSVs for AERO, VLRS, RYAAY, DAL, ICAGY",
                ],
                "parse.market_chart": [
                    "Candidate verified SEC identity evidence and original SEC Bronze artifact",
                    "All five preserved Yahoo raw JSON charts with exact ticker/USD/EQUITY identity",
                ],
            }.items()
            if name in steps
        },
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
        # Static public inputs used by the normal Gold builders and SQL views.
        for path in [ROOT / "docs/glosario-kpis.md", *(ROOT / "sql/gold").rglob("*.sql")]:
            destination = workspace / path.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and destination.read_bytes() != path.read_bytes():
                raise ValueError(f"Candidate static input differs: {path.relative_to(ROOT)}")
            if not destination.exists():
                shutil.copyfile(path, destination)
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
    # any parser/transform, in a fresh interpreter for every build. Registry
    # dependency metadata is pure and may already be loaded by preflight.
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
    registry["parse.complementary"] = replace(
        registry["parse.complementary"], callable_ref="src.source_updates.complementary:run"
    )
    dependencies = required_predecessors(requested)
    for name, (action, sources, outputs) in GRANULAR.items():
        inputs = (
            [InputRequirement(name, bronze_source_systems=sources)]
            if sources
            else [
                InputRequirement(
                    "Validated Gold",
                    path_patterns=("data/gold/fact_carrier_metrics.parquet", "data/gold/fact_macro.parquet"),
                    require_all_paths=True,
                )
            ]
        )
        if name in {"parse.market", "parse.market_chart"}:
            inputs.append(
                InputRequirement(
                    "Candidate SEC evidence for AERO ticker identity",
                    path_patterns=("data/silver/sec_report_text.parquet",),
                    require_all_paths=True,
                )
            )
        if name == "parse.fx":
            inputs.append(
                InputRequirement(
                    "All three Banxico series (H.10 is not an offline parser input)",
                    path_patterns=tuple(
                        f"data/bronze/**/banxico_sie_{series}_*.csv"
                        for series in ("SF43718", "SP1", "SF61745")
                    ),
                    require_all_paths=True,
                )
            )
        registry[name] = PipelineStep(
            name,
            PipelinePhase.TRANSFORM if name.startswith("transform.") else PipelinePhase.PARSE,
            name,
            action,
            RequirementLevel.REQUIRED,
            tuple(inputs),
            tuple(f"data/silver/{table}.parquet" for table in outputs),
            depends_on=dependencies.get(name, ()),
        )
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
