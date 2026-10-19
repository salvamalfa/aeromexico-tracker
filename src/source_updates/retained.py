"""Retain selected public originals and certify product candidates entirely offline."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from uuid import uuid4

import pandas as pd

from src.pipeline.offline import block_network
from src.source_updates.calendar import local_time
from src.source_updates.catalog import ROOT, load_catalog
from src.source_updates.checks import period_end, row_changes, verify_bronze
from src.source_updates.collection import safe_workspace, validate_url, writer
from src.transform.stage6_contracts import validate_table
from src.transform.stage9_lineage import (
    LineageSpec,
    add_record_ids,
    build_bridge_record_lineage,
    build_dim_source_artifact,
)
from src.transform.validate_stage9 import validate_lineage_frames


def spec(product: str) -> dict:
    from src.source_updates import (
        afac_airports,
        afac_countries,
        afac_margins,
        authorities,
        context_snapshots,
        financials,
        oma_traffic,
        route_documents,
        slots,
    )

    registry = {
        "afac_airports": {
            "roles": {"workbook": ("afac",)},
            "primary": "workbook",
            "code_files": [Path(afac_airports.__file__)],
            "table": afac_airports.TABLE,
            "grain": afac_airports.BUSINESS_GRAIN,
            "parse": lambda originals, period: afac_airports.parse(
                originals["workbook"][0], period, originals["workbook"][1]
            ),
        }
    }
    for name, module, roles in [
        (
            "afac_margins",
            afac_margins,
            {"routes": ("afac_research", "afac"), "carriers": ("afac_research", "afac")},
        ),
        (
            "afac_countries",
            afac_countries,
            {"pdf": ("afac_research", "afac"), "routes": ("afac_research", "afac")},
        ),
    ]:
        registry[name] = {
            "roles": roles,
            "primary": next(iter(roles)),
            "code_files": [Path(module.__file__), Path(afac_margins.__file__), Path(afac_airports.__file__)],
            "support_all_originals": True,
            "table": module.TABLE,
            "grain": module.GRAIN,
            "parse": module.parse,
        }
    for name, role, aliases in [
        ("iasa", "pdf", ("faa_iasa",)),
        ("dictionary", "csv", ("loughran_mcdonald",)),
    ]:
        registry[name] = {
            "roles": {role: aliases},
            "primary": role,
            "table": context_snapshots.TABLES[name],
            "grain": context_snapshots.GRAINS[name],
            "parse": getattr(context_snapshots, name),
            "code_files": [Path(context_snapshots.__file__)],
        }
    registry["am_financials"] = {
        "roles": {"pdf": ("aeromexico_ir",)},
        "primary": "pdf",
        "table": financials.TABLE,
        "grain": financials.GRAIN,
        "parse": financials.parse,
        "revision_values": ["value", "unit", "is_preliminary", "is_unaudited"],
        "code_files": [
            Path(financials.__file__),
            ROOT / "src/parse/aeromexico_ir_financial.py",
            ROOT / "src/parse/aeromexico_ir.py",
        ],
    }
    registry["oma_traffic"] = {
        "roles": {"pdf": ("oma_ir",)},
        "primary": "pdf",
        "table": oma_traffic.TABLE,
        "grain": oma_traffic.GRAIN,
        "parse": oma_traffic.parse,
        "code_files": [
            Path(oma_traffic.__file__),
            Path(authorities.__file__),
            Path(afac_airports.__file__),
            ROOT / "src/transform/international_routes.py",
        ],
    }
    registry["aicm_slots"] = {
        "roles": {"pdf": ("aicm",)},
        "primary": "pdf",
        "table": slots.TABLE,
        "grain": slots.GRAIN,
        "parse": slots.parse,
        "code_files": [Path(slots.__file__)],
    }
    for name, aliases in {
        "am_routes": ("aeromexico_press",),
        "oma_routes": ("oma",),
        "colima": ("colima_subsectur_mirror",),
        "aifa_roster": ("expansion",),
    }.items():
        registry[name] = {
            "roles": {"document": aliases},
            "primary": "document",
            "table": route_documents.TABLES[name],
            "grain": route_documents.GRAIN,
            "parse": lambda inputs, period, name=name: route_documents.parse(name, inputs, period),
            "code_files": [Path(route_documents.__file__)],
        }
    for name, roles in {
        "anac": {"json": ("international_routes",)},
        "caa": {"csv": ("route_authority_research", "international_routes")},
        "aena": {
            role: ("aena",)
            for role in ("company_operations", "company_passengers", "market_operations", "market_passengers")
        },
    }.items():
        registry[name] = {
            "roles": roles,
            "primary": next(iter(roles)),
            "code_files": [Path(authorities.__file__), ROOT / "src/transform/international_routes.py"],
            "table": authorities.TABLES[name],
            "grain": authorities.GRAIN,
            "parse": getattr(authorities, name),
        }
    registry["afac_margins"]["revision_values"] = ["value", "unit", "source_cell_estimated", "source_notes"]
    registry["dictionary"]["revision_values"] = [*context_snapshots.FIELDS[1:], "unit"]
    if product not in registry:
        raise ValueError("No reviewed retained-product adapter")
    return registry[product]


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def public_original(row: dict) -> None:
    matches = [
        source for source in load_catalog().values() if row["source_system"] in source["source_systems"]
    ]
    if len(matches) != 1 or matches[0]["source_kind"] != "public" or not matches[0]["is_active"]:
        raise ValueError("Only catalogued active public-source originals may be retained")
    validate_url(row["source_url"], matches[0]["allowed_hosts"])


def retain(workspace: Path, source_root: Path, product: str, selected: dict, *, execute=False) -> dict:
    workspace = safe_workspace(workspace)
    source_root = source_root.resolve()
    definition = spec(product)
    if set(selected) != set(definition["roles"]):
        raise ValueError("Select exactly the product's explicit input roles")
    entries = {}
    with (source_root / "_manifest.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            if row["source_file"] in selected.values():
                entries[row["source_file"]] = row
    inputs = {}
    for role, relative in selected.items():
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Original path must be relative without traversal")
        path = (source_root / relative).resolve()
        if not path.is_relative_to(source_root) or not path.is_file():
            raise ValueError("Original must be a file within the selected Bronze root")
        row = entries.get(relative)
        if row is None or row["source_system"] not in definition["roles"][role]:
            raise ValueError("Original source alias or role absent from manifest")
        public_original(row)
        inputs[role] = row
    planned = {
        "mode": "retain" if execute else "dry_run",
        "product": product,
        "originals": inputs,
        "network_requests": 0,
        "paid_requests": 0,
        "new_source_capture": False,
        "source_capture_dates_preserved": True,
        "activation": "none",
        "publication": "not_authorized",
    }
    if not execute:
        return planned
    if (workspace / "data/bronze/_manifest.jsonl").exists():
        raise ValueError("Retention requires a new candidate workspace; preserve prior evidence")
    for row in inputs.values():
        path = source_root / row["source_file"]
        meta = json.loads(Path(str(path) + ".meta.json").read_text())
        if digest(path) != row["sha256"] or any(
            meta.get(key) != row[key]
            for key in (
                "sha256",
                "source_file",
                "source_url",
                "source_system",
                "logical_key",
                "downloaded_at",
            )
        ):
            raise ValueError("Original hash/sidecar/manifest mismatch before retention")
    with writer(workspace):
        manifest = workspace / "data/bronze/_manifest.jsonl"
        if manifest.exists():
            raise ValueError("Retention already exists; use a new workspace")
        for relative, row in {r["source_file"]: r for r in inputs.values()}.items():
            source = source_root / relative
            destination = workspace / "data/bronze" / relative
            if not destination.resolve().is_relative_to((workspace / "data/bronze").resolve()):
                raise ValueError("Retention destination escapes candidate")
            if destination.exists() or Path(str(destination) + ".meta.json").exists():
                raise ValueError("Retention destination already exists; preserve partial evidence")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            shutil.copyfile(Path(str(source) + ".meta.json"), Path(str(destination) + ".meta.json"))
            if digest(destination) != row["sha256"]:
                raise ValueError("Original changed while being copied; no certification")
        manifest.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False) + "\n"
                for row in {r["source_file"]: r for r in inputs.values()}.values()
            )
        )
        result = {
            **planned,
            "status": "retained_unvalidated",
            "run_id": uuid4().hex,
            "retained_at": datetime.now(UTC).isoformat(),
            "manifest_sha256": digest(manifest),
        }
        receipt = workspace / "receipts" / f"retained-{result['run_id']}.json"
        receipt.parent.mkdir(exist_ok=True)
        receipt.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    return result


def originals(workspace: Path, product: str, run_id: str, cutoff: str) -> tuple[dict, str]:
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("Expected a retained-original receipt ID")
    path = workspace / "receipts" / f"retained-{run_id}.json"
    receipt = json.loads(path.read_text())
    definition = spec(product)
    if (
        receipt.get("product") != product
        or receipt.get("status") != "retained_unvalidated"
        or set(receipt["originals"]) != set(definition["roles"])
    ):
        raise ValueError("Retention receipt product/roles/status differ")
    if receipt["manifest_sha256"] != digest(workspace / "data/bronze/_manifest.jsonl"):
        raise ValueError("Retained acquisition manifest changed")
    verified = verify_bronze(workspace)
    if set(verified) != {row["source_file"] for row in receipt["originals"].values()}:
        raise ValueError("Retained candidate contains unselected source artifacts")
    result = {}
    for role, row in receipt["originals"].items():
        actual = verified.get(row["source_file"])
        if actual != row or row["source_system"] not in definition["roles"][role]:
            raise ValueError("Retained original identity changed")
        public_original(row)
        if local_time(row["downloaded_at"]) > local_time(cutoff):
            raise ValueError("Original source capture is after requested cutoff")
        source = workspace / "data/bronze" / row["source_file"]
        meta = json.loads(Path(str(source) + ".meta.json").read_text())
        if any(
            meta.get(key) != row[key]
            for key in (
                "sha256",
                "source_file",
                "source_url",
                "source_system",
                "logical_key",
                "downloaded_at",
            )
        ):
            raise ValueError("Retained sidecar changed")
        result[role] = (source.read_bytes(), row)
    return result, digest(path)


def frames(workspace: Path, product: str, period: str, cutoff: str, run_id: str) -> tuple[dict, dict]:
    definition = spec(product)
    inputs, receipt_hash = originals(workspace, product, run_id, cutoff)
    frame, details = definition["parse"](inputs, period)
    if frame.empty or frame.duplicated(definition["grain"]).any() or frame.value.isna().any():
        raise ValueError("Empty, duplicate or missing retained-product observations")
    records = [row for _, row in inputs.values()]
    for row in (
        frame[["source_system", "source_file", "source_hash"]].drop_duplicates().itertuples(index=False)
    ):
        if not any(
            row.source_system == record["source_system"]
            and row.source_file == record["source_file"]
            and row.source_hash == record["sha256"]
            for record in records
        ):
            raise ValueError("Observation direct source not in selected originals")
    record_grain = ["source_hash", "source_locator", "parser_version", "period_id", "metric_key"]
    frame = add_record_ids(frame, table_name=definition["table"], natural_key_columns=record_grain)
    artifacts = validate_table(
        "dim_source_artifact",
        build_dim_source_artifact(
            workspace / "data/bronze/_manifest.jsonl",
            catalog_path=ROOT / "config/source_catalog.yaml",
            verify_files=True,
        ),
    )
    by_file = artifacts.set_index("source_file").artifact_id.to_dict()
    bridge = validate_table(
        "bridge_record_lineage",
        build_bridge_record_lineage(
            [
                LineageSpec(
                    record_id=row.record_id,
                    table_name=definition["table"],
                    lineage_type="direct_artifact",
                    artifact_ids=tuple(by_file.values())
                    if definition.get("support_all_originals")
                    else (by_file[row.source_file],),
                    lineage_note=(
                        f"Direct value artifact: {row.source_file}. Other selected artifacts support reconciliation, not allocation. Retained snapshot; source locator/units/scope preserved. Not new capture or human publication approval."
                        if definition.get("support_all_originals")
                        else "Retained source snapshot; source locator/units/scope preserved. Not a new capture or human publication approval."
                    ),
                )
                for row in frame.itertuples(index=False)
            ],
            artifacts,
        ),
    )
    lineage = validate_lineage_frames(
        tables={definition["table"]: frame},
        artifacts=artifacts,
        bridge=bridge,
        contracts={"tables": {definition["table"]: {"grain": record_grain}}},
    )
    outputs = {
        f"silver/source_products/{product}": frame,
        f"gold/{definition['table']}": frame.copy(),
        "gold/dim_source_artifact": artifacts,
        "gold/bridge_record_lineage": bridge,
    }
    return outputs, {
        **details,
        "lineage": lineage,
        "retention_receipt_sha256": receipt_hash,
        "scope_basis": "selected_retained_source_snapshot_not_latest_source_availability",
        "latest_available_period": None,
        "latest_published_period": None,
        "new_source_capture": False,
        "capture_dates": sorted({row["downloaded_at"] for row in records}),
        "custom_candidate_contract": True,
        "network_requests": 0,
        "paid_requests": 0,
        "approval": "human_review_required",
        "activation": "none",
        "publication": "not_authorized",
    }


def run(
    workspace: Path,
    product: str,
    period: str,
    cutoff: str,
    run_id: str,
    *,
    execute=False,
    check=False,
    baseline=None,
) -> dict:
    workspace = safe_workspace(workspace)
    definition = spec(product)
    if period_end(period) >= local_time(cutoff).date():
        raise ValueError("Require a closed observation period")
    output_names = (
        f"silver/source_products/{product}",
        f"gold/{definition['table']}",
        "gold/dim_source_artifact",
        "gold/bridge_record_lineage",
    )
    allowed = {workspace / "data" / (name + ".parquet") for name in output_names}
    if any(
        path not in allowed
        for layer in ("silver", "gold")
        for path in (workspace / "data" / layer).rglob("*.parquet")
    ):
        raise ValueError("Use an isolated product workspace")
    accepted = workspace / "receipts" / f"certified-{product}-{period}.json"
    if not execute and not check:
        return {
            "mode": "dry_run",
            "product": product,
            "outputs": list(output_names),
            "network_requests": 0,
            "paid_requests": 0,
            "new_source_capture": False,
            "activation": "none",
            "publication": "not_authorized",
        }
    prior = json.loads(accepted.read_text()) if check else None
    if check:
        previous_baseline = prior.get("revisions", {}).get("baseline_file")
        if baseline is not None and baseline != previous_baseline:
            raise ValueError("Accepted baseline selection changed")
        baseline = previous_baseline
    if execute and (accepted.exists() or any(path.exists() for path in allowed)):
        raise ValueError("Candidate outputs immutable; use a new workspace")
    with block_network():
        outputs, result = frames(workspace, product, period, cutoff, run_id)
    result.update(
        status="checks_passed",
        product=product,
        requested_period=period,
        retention_run_id=run_id,
        effective_as_of=cutoff,
        checked_at=datetime.now(UTC).isoformat(),
        code_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        code_files={
            p.relative_to(ROOT).as_posix(): digest(p) for p in [Path(__file__), *definition["code_files"]]
        },
    )
    result["revisions"] = {"status": "not_compared_no_baseline"}
    if baseline:
        path = (workspace / baseline).resolve()
        if not path.is_relative_to((workspace / "baselines").resolve()):
            raise ValueError("Baseline must remain within candidate baselines/")
        before = pd.read_parquet(path)
        result["revisions"] = {
            "baseline_file": baseline,
            "baseline_sha256": digest(path),
            **row_changes(
                before,
                outputs[output_names[0]],
                definition["grain"],
                definition.get("revision_values", ["value", "unit"]),
            ),
        }
    if check:
        if result["revisions"] != prior["revisions"]:
            raise ValueError("Accepted baseline or revisions changed")
        if (
            prior["retention_run_id"] != run_id
            or prior["retention_receipt_sha256"] != result["retention_receipt_sha256"]
        ):
            raise ValueError("Accepted retention receipt changed")
        for name, frame in outputs.items():
            try:
                pd.testing.assert_frame_equal(
                    pd.read_parquet(workspace / "data" / (name + ".parquet")), frame, check_exact=True
                )
            except AssertionError as exc:
                raise ValueError(f"Output differs from verified retained original: {name}") from exc
        result["output_sha256"] = {name: digest(workspace / "data" / (name + ".parquet")) for name in outputs}
        if result["output_sha256"] != prior["output_sha256"]:
            raise ValueError("Accepted output hash changed")
        return result
    from src.ingest.stage4_common import write_parquet_atomic

    with writer(workspace):
        if accepted.exists() or any(path.exists() for path in allowed):
            raise ValueError("Candidate outputs immutable; use a new workspace")
        for name, frame in outputs.items():
            write_parquet_atomic(frame, workspace / "data" / (name + ".parquet"))
        result["output_sha256"] = {name: digest(workspace / "data" / (name + ".parquet")) for name in outputs}
        serialized = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        (workspace / "receipts" / f"certified-{uuid4().hex}.json").write_text(serialized)
        accepted.write_text(serialized)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["retain", "certify"])
    parser.add_argument("--product", required=True)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--original", action="append", default=[], help="role=relative/Bronze/path")
    parser.add_argument("--period")
    parser.add_argument("--as-of")
    parser.add_argument("--retention")
    parser.add_argument("--baseline")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.mode == "retain":
            if args.check:
                raise ValueError("Retention does not support certification --check")
            if args.source_root is None or not args.original:
                raise ValueError("Select Bronze root and explicit role/path originals")
            pairs = [value.split("=", 1) for value in args.original]
            if any(len(pair) != 2 for pair in pairs) or len(dict(pairs)) != len(pairs):
                raise ValueError("Original roles must be unique role=path pairs")
            result = retain(args.workspace, args.source_root, args.product, dict(pairs), execute=args.execute)
        else:
            if not all((args.period, args.as_of, args.retention)):
                raise ValueError("Certification requires period, cutoff and retention receipt")
            result = run(
                args.workspace,
                args.product,
                args.period,
                args.as_of,
                args.retention,
                execute=args.execute,
                check=args.check,
                baseline=args.baseline,
            )
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "activation": "none"}))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
