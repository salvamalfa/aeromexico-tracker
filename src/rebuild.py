"""Isolated, network-blocked rebuild from an immutable Bronze copy."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Iterable
from uuid import uuid4

from src.config import PATHS


CORE_OUTPUTS = (
    "data/silver",
    "data/gold",
    "data/quality",
    "data/analytics",
    "data/warehouse.duckdb",
)
GENERATED_OUTPUTS = CORE_OUTPUTS + (
    "models",
    "docs/analytics",
    "docs/diccionario-datos.md",
    "docs/diccionario-conceptos-xbrl.md",
    "docs/afac-inventario.md",
    "notebooks/01_eda.ipynb",
    "config/carrier_crosswalk.csv",
)


class RebuildError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RebuildResult:
    status: str
    bronze_source: str
    workspace: str
    code_version: str
    published: bool
    report: dict[str, object]
    gold_sha256: dict[str, str]


def create_clean_checkout(
    project_root: Path,
    bronze_source: Path,
    workspace_root: Path,
) -> Path:
    """Copy code/config plus Bronze, explicitly excluding every prior derived output."""

    project_root = project_root.resolve()
    bronze_source = bronze_source.resolve()
    if not (bronze_source / "_manifest.jsonl").is_file():
        raise FileNotFoundError(f"Bronze manifest is missing: {bronze_source / '_manifest.jsonl'}")
    checkout = workspace_root.resolve()
    if checkout.exists():
        raise FileExistsError(f"Rebuild workspace already exists: {checkout}")

    def ignore(directory: str, names: list[str]) -> set[str]:
        ignored = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"} & set(names)
        ignored.update(name for name in names if name.endswith((".pyc", ".pyo")))
        ignored.update(name for name in names if name.startswith(".aeromexico-rebuild-"))
        resolved_directory = Path(directory).resolve()
        if resolved_directory == project_root:
            ignored.update(
                {
                    ".git",
                    ".venv",
                    ".env",
                    ".streamlit",
                    "data",
                    "logs",
                    "models",
                    "notebooks",
                }
                & set(names)
            )
        elif resolved_directory == project_root / "docs":
            ignored.update(
                {
                    "analytics",
                    "diccionario-datos.md",
                    "diccionario-conceptos-xbrl.md",
                    "afac-inventario.md",
                }
                & set(names)
            )
        elif resolved_directory == project_root / "config":
            ignored.update({"carrier_crosswalk.csv"} & set(names))
        return ignored

    shutil.copytree(project_root, checkout, ignore=ignore, copy_function=shutil.copy2)
    target_bronze = checkout / "data" / "bronze"
    target_bronze.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(bronze_source, target_bronze, copy_function=shutil.copy2)
    source_reference = project_root / "data" / "reference"
    if source_reference.is_dir():
        shutil.copytree(
            source_reference,
            checkout / "data" / "reference",
            copy_function=shutil.copy2,
        )
    for relative in CORE_OUTPUTS:
        target = checkout / relative
        if target.exists():
            raise RebuildError(f"Clean checkout unexpectedly contains derived output: {target}")
    return checkout


def _hash_gold(checkout: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((checkout / "data" / "gold").glob("*.parquet"))
    }


def _code_fingerprint(checkout: Path) -> str:
    """Fingerprint the executable code/config copied into an isolated checkout."""

    digest = hashlib.sha256()
    candidates: list[Path] = []
    for directory in (checkout / "src", checkout / "config"):
        if directory.is_dir():
            candidates.extend(path for path in directory.rglob("*") if path.is_file())
    for filename in ("pyproject.toml", "uv.lock", "justfile"):
        path = checkout / filename
        if path.is_file():
            candidates.append(path)
    for path in sorted(candidates, key=lambda item: item.relative_to(checkout).as_posix()):
        relative = path.relative_to(checkout).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return f"sha256:{digest.hexdigest()}"


def _copy_for_publish(checkout: Path, staging: Path, outputs: Iterable[str]) -> list[str]:
    copied: list[str] = []
    for relative in outputs:
        source = checkout / relative
        if not source.exists():
            raise RebuildError(f"Required rebuild output is missing: {relative}")
        destination = staging / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, destination, copy_function=shutil.copy2)
        else:
            shutil.copy2(source, destination)
        copied.append(relative)
    return copied


def publish_outputs(project_root: Path, checkout: Path) -> list[str]:
    """Publish only after success; restore every old target if any swap fails."""

    token = uuid4().hex
    staging = project_root / f".aeromexico-rebuild-publish-{token}"
    backup = project_root / f".aeromexico-rebuild-backup-{token}"
    copied = _copy_for_publish(checkout, staging, GENERATED_OUTPUTS)
    swapped: list[tuple[Path, Path | None]] = []
    try:
        for relative in copied:
            target = project_root / relative
            staged = staging / relative
            prior: Path | None = None
            if target.exists():
                prior = backup / relative
                prior.parent.mkdir(parents=True, exist_ok=True)
                target.replace(prior)
            # Register the in-progress swap before installing the replacement so
            # rollback also restores a target whose staged move fails.
            swapped.append((target, prior))
            target.parent.mkdir(parents=True, exist_ok=True)
            staged.replace(target)
    except Exception:
        for target, prior in reversed(swapped):
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            if prior is not None and prior.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                prior.replace(target)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
        shutil.rmtree(backup, ignore_errors=True)
    return copied


def rebuild_offline(
    *,
    project_root: Path = PATHS.root,
    bronze_source: Path | None = None,
    workspace: Path | None = None,
    publish: bool = True,
    keep_workspace: bool = False,
) -> RebuildResult:
    project_root = project_root.resolve()
    source = (bronze_source or project_root / "data" / "bronze").resolve()
    workspace_path = workspace or Path(
        tempfile.mkdtemp(prefix=".aeromexico-rebuild-", dir=project_root.parent)
    )
    if workspace is None:
        # mkdtemp creates the directory, while create_clean_checkout requires an absent target.
        workspace_path.rmdir()
    checkout = create_clean_checkout(project_root, source, workspace_path)
    code_version = _code_fingerprint(checkout)
    report_relative = Path("data/quality/pipeline_runs/offline-rebuild.json")
    command = [
        sys.executable,
        "-m",
        "src.pipeline.worker",
        "--root",
        str(checkout),
        "--phases",
        "parse,transform,analytics,dashboard",
        "--report",
        str(report_relative),
        "--offline",
    ]
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["AEROMEXICO_CODE_VERSION"] = code_version
    succeeded = False
    try:
        completed = subprocess.run(
            command,
            cwd=checkout,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        report_path = checkout / report_relative
        report = (
            json.loads(report_path.read_text(encoding="utf-8"))
            if report_path.is_file()
            else {"status": "failed", "steps": []}
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            stdout = completed.stdout.strip()
            raise RebuildError(
                "Offline rebuild worker failed. "
                f"workspace={checkout}; stderr={stderr[-2000:]}; stdout={stdout[-2000:]}"
            )
        hashes = _hash_gold(checkout)
        if not hashes:
            raise RebuildError("Offline rebuild produced no Gold Parquet files")
        if publish:
            publish_outputs(project_root, checkout)
        succeeded = True
        return RebuildResult(
            "completed", str(source), str(checkout), code_version, publish, report, hashes
        )
    finally:
        if succeeded and publish and not keep_workspace and checkout.exists():
            shutil.rmtree(checkout, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bronze-source", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--keep-workspace", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = rebuild_offline(
        bronze_source=args.bronze_source,
        workspace=args.workspace,
        publish=not args.no_publish,
        keep_workspace=args.keep_workspace or args.no_publish,
    )
    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
