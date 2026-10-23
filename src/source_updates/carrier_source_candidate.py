"""Certify retained Volaris/AFAC carrier source dossiers offline; never acquire or publish."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src.pipeline.offline import block_network
from src.source_updates.calendar import local_time
from src.source_updates.carrier_source_contract import CONTRACT, NATIVE, TABLES, validate
from src.source_updates.carrier_source_gold import MODULES, frames
from src.source_updates.carrier_source_inputs import guard, retain
from src.source_updates.carrier_source_inputs import inputs as originals
from src.source_updates.catalog import ROOT
from src.source_updates.checks import period_end, require_replay_cutoff, row_changes
from src.source_updates.collection import safe_workspace, writer
from src.source_updates.retained import digest

PRODUCTS = set(TABLES)


def fingerprints() -> dict:
    # Include transitive implementation/contracts, not just the thin CLI wrapper.
    paths = [
        *(ROOT / "src/source_updates").glob("*.py"),
        *(ROOT / "src/transform").glob("*.py"),
        *(ROOT / "src/ingest/macro").glob("*.py"),
        ROOT / "src/ingest/market/prices.py",
        ROOT / "src/ingest/stage4_common.py",
        ROOT / "src/pipeline/offline.py",
        *(ROOT / "contracts").rglob("*.yaml"),
        *(ROOT / "config").glob("source*.json"),
        *(ROOT / "config").glob("*.yaml"),
        ROOT / "config/source_catalog.yaml",
        *(ROOT / "contracts/source_updates").glob("*.json"),
        ROOT / "data/reference/carrier_crosswalk.csv",
        ROOT / "src/config.py",
        *(ROOT / "src/common").glob("*.py"),
        CONTRACT,
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
    ]
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(paths))}


def period_check(product, period):
    if product == "volaris_sec":
        if period != "2026Q2":
            raise ValueError("Volaris 2026Q2 report only; monthly SEC evidence is not certified")
    elif product == "afac_carriers":
        from src.source_updates.afac_carrier_source import month

        month(period)
    else:
        raise ValueError("Unknown complete carrier source product")


def output_names(product: str) -> tuple:
    return (
        f"silver/{NATIVE[product]}",
        f"gold/{TABLES[product]}",
        "gold/dim_source_artifact",
        "gold/bridge_record_lineage",
    )


def revisions(workspace: Path, baseline, product: str, outputs: dict, cutoff: str) -> dict:
    if baseline is None:
        return {"status": "not_compared_no_baseline"}
    path = (workspace / baseline).resolve()
    if not path.is_relative_to((workspace / "baselines").resolve()):
        raise ValueError("Baseline must remain within candidate baselines/")
    before = pd.read_parquet(path)
    validate(before, product)
    baseline_root = path.parent.parent.parent
    if path.relative_to(baseline_root).as_posix() != f"data/silver/{NATIVE[product]}.parquet":
        raise ValueError("Baseline must be a full retained snapshot under baselines/<snapshot>/data/silver/")
    guard(baseline_root)
    receipt_paths = list((baseline_root / "receipts").glob("retained-*.json"))
    if len(receipt_paths) != 1:
        raise ValueError("Baseline requires its unique original retention receipt")
    acquisition = json.loads(receipt_paths[0].read_text(encoding="utf-8"))
    # Rebuild all native cells from baseline's physical originals, not a trusted
    # Parquet or caller-supplied digest. Current code is deliberately used.
    selected, _ = originals(baseline_root, product, acquisition["run_id"], cutoff)
    rebuilt, _ = MODULES[product].read(selected, next(iter(set(before.edition))))
    from src.source_updates.carrier_source_contract import identifier

    rebuilt["record_id"] = rebuilt.apply(identifier, axis=1)
    try:
        pd.testing.assert_frame_equal(before, rebuilt.reset_index(drop=True), check_exact=True)
    except AssertionError as exc:
        raise ValueError("Baseline native observations differ from its verified original dossier") from exc
    current = outputs[f"silver/{NATIVE[product]}"]
    if set(before.edition) != set(current.edition) or set(before["product"]) != {product}:
        raise ValueError("Carrier baseline needs the identical product and reviewed edition")
    # Keep physical positions as well as semantic identity: historical DB rows can
    # repeat a semantic grain. Reordering is conservatively added/removed, never
    # guessed equivalent or silently collapsed.
    grain = [
        "statement",
        "period_id",
        "metric_key",
        "entity_as_reported",
        "segment",
        "service_type",
        "source_group",
        "source_row_number",
        "source_column",
    ]
    values = [
        "value",
        "unit",
        "scale",
        "source_value",
        "period_type",
        "period_start_date",
        "period_end_date",
        "carrier_key",
        "mapping_evidence",
        "is_preliminary",
        "is_unaudited",
        "source_estimated",
        "source_notes",
        "aviation_scope",
    ]
    return {
        "baseline_file": baseline,
        "baseline_table": f"silver/{NATIVE[product]}",
        "baseline_sha256": digest(path),
        "baseline_provenance_sha256": inventory(baseline_root),
        "comparison_basis": "complete_native_source_observations_not_official_revision_verification",
        "row_reordering": "added_removed_not_assumed_equivalent",
        **row_changes(before, current, grain, values),
    }


def inventory(workspace: Path) -> dict:
    if (workspace / ".source-update.lock").exists():
        raise ValueError("Source candidate has an active writer")
    return {str(p.relative_to(workspace)): digest(p) for p in sorted(workspace.rglob("*")) if p.is_file()}


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
    guard(workspace)
    workspace = safe_workspace(workspace)
    before = inventory(workspace) if check else None
    if product not in PRODUCTS or execute and check:
        raise ValueError("Select one supported carrier product and one execution mode")
    period_check(product, period)
    end = period_end(period)
    if end >= local_time(cutoff).date():
        raise ValueError("Require a closed observation period before the explicit zoned cutoff")
    names = output_names(product)
    allowed = {workspace / "data" / (name + ".parquet") for name in names}
    if any(
        path not in allowed
        for layer in ("silver", "gold")
        for path in (workspace / "data" / layer).rglob("*")
        if path.is_file()
    ):
        raise ValueError("Use a separate isolated product/window workspace")
    base = {
        "version": 1,
        "product": product,
        "period": period,
        "retention_run_id": run_id,
        "effective_as_of": cutoff,
        "network_requests": 0,
        "paid_requests": 0,
        "new_source_capture": False,
        "latest_source_availability_verified": False,
        "latest_available_period": None,
        "latest_validated_period": period,
        "latest_published_tracker_period": None,
        "ready_for_calendar_incorporation": False,
        "activation": "none",
        "publication": "not_authorized",
        "approval": "human_review_required",
        "scope": "selected_retained_carrier_source_dossier_not_latest_source_availability",
        "first_publication_date": None,
        "release_lag_days": None,
    }
    if not execute and not check:
        return {**base, "status": "planned_not_executed", "outputs": list(names)}
    accepted = workspace / "receipts" / f"carrier-source-{product}-{period}.json"
    prior = json.loads(accepted.read_text(encoding="utf-8")) if check else None
    if check:
        require_replay_cutoff(prior, cutoff)
        recorded = prior.get("revisions", {}).get("baseline_file")
        if baseline is not None and baseline != recorded:
            raise ValueError("Accepted baseline selection changed")
        baseline = recorded
    if execute and (accepted.exists() or any(p.exists() for p in allowed)):
        raise ValueError("Accepted candidates and partial outputs are immutable; use a new workspace")

    def evaluate():
        inputs, receipt_hash = originals(workspace, product, run_id, cutoff)
        native, details = MODULES[product].read(inputs, period)
        outputs, evidence = frames(workspace, product, period, native, details)
        if set(outputs) != set(names):
            raise ValueError("Product output inventory differs from its full certification contract")
        result = {
            **base,
            **evidence,
            "status": "checks_passed",
            "rows": {name: len(frame) for name, frame in outputs.items()},
            "retention_receipt_sha256": receipt_hash,
            "capture_dates": sorted({r["downloaded_at"] for _, r in inputs.values()}),
            "code_files": fingerprints(),
            "revisions": revisions(workspace, baseline, product, outputs, cutoff),
        }
        return outputs, result

    if check:
        with block_network():
            outputs, result = evaluate()
            for name, frame in outputs.items():
                try:
                    pd.testing.assert_frame_equal(
                        pd.read_parquet(workspace / "data" / (name + ".parquet")), frame, check_exact=True
                    )
                except AssertionError as exc:
                    raise ValueError(f"Output differs from verified original: {name}") from exc
            result["output_sha256"] = {n: digest(workspace / "data" / (n + ".parquet")) for n in names}
        ignored = {"checked_at", "code_head"}
        if result != {k: v for k, v in prior.items() if k not in ignored}:
            raise ValueError("Accepted source, code, contract, cutoff, baseline or output evidence changed")
        if inventory(workspace) != before:
            raise ValueError("Source candidate changed during offline replay")
        return result
    from src.ingest.stage4_common import write_parquet_atomic

    with writer(workspace), block_network():
        if accepted.exists() or any(p.exists() for p in allowed):
            raise ValueError("Candidate outputs immutable; use a new workspace")
        # Validate the complete product before creating any Silver/Gold output.
        outputs, result = evaluate()
        for name, frame in outputs.items():
            write_parquet_atomic(frame, workspace / "data" / (name + ".parquet"))
        result["output_sha256"] = {n: digest(workspace / "data" / (n + ".parquet")) for n in names}
        result["checked_at"] = datetime.now(UTC).isoformat()
        result["code_head"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        accepted.write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
        )
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["retain", "certify"])
    parser.add_argument("--product", choices=sorted(PRODUCTS), required=True)
    parser.add_argument("--workspace", type=Path, required=True)
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
            if args.check or args.source_root is None or not args.original:
                raise ValueError(
                    "Retention requires Bronze root and explicit roles; --check is certification only"
                )
            pairs = [value.split("=", 1) for value in args.original]
            if any(len(p) != 2 for p in pairs) or len(dict(pairs)) != len(pairs):
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
    except Exception as exc:  # CLI reports malformed PDF/ZIP/schema failures without accepting outputs.
        print(json.dumps({"status": "blocked", "reason": str(exc), "activation": "none"}))
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
