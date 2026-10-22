"""Certify retained Banxico, EIA or five-equity products offline; never acquire or publish."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from src.pipeline.offline import block_network
from src.source_updates.calendar import local_time
from src.source_updates.catalog import ROOT
from src.source_updates.checks import require_replay_cutoff, row_changes
from src.source_updates.collection import safe_workspace, writer
from src.source_updates.retained import digest, originals, retain
from src.source_updates.series_gold import frames
from src.source_updates.series_native import PRODUCTS, read, window


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
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
    ]
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(paths))}


def output_names(product: str) -> tuple:
    silver = {
        "banxico": ("macro_indicators", "fx_rates"),
        "fuel": ("fuel_prices",),
        "equities": ("market_prices",),
    }[product]
    return (
        *("silver/" + name for name in silver),
        "gold/fact_market_data" if product == "equities" else "gold/fact_macro",
        "gold/dim_carrier" if product == "equities" else "gold/dim_period",
        "gold/dim_source_artifact",
        "gold/bridge_record_lineage",
    )


def revisions(workspace: Path, baseline, product: str, outputs: dict) -> dict:
    if baseline is None:
        return {"status": "not_compared_no_baseline"}
    path = (workspace / baseline).resolve()
    if not path.is_relative_to((workspace / "baselines").resolve()):
        raise ValueError("Baseline must remain within candidate baselines/")
    name = "gold/fact_market_data" if product == "equities" else "gold/fact_macro"
    keys = ["carrier_key", "date"] if product == "equities" else ["period_id", "indicator_key", "aggregation"]
    values = (
        ["close", "adj_close", "volume", "currency", "return_1d", "return_ytd", "volatility_30d"]
        if product == "equities"
        else ["value", "unit"]
    )
    return {
        "baseline_file": baseline,
        "baseline_sha256": digest(path),
        **row_changes(pd.read_parquet(path), outputs[name], keys, values),
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
    workspace = safe_workspace(workspace)
    before = inventory(workspace) if check else None
    if product not in PRODUCTS or execute and check:
        raise ValueError("Select one supported series product and one execution mode")
    _, end, _ = window(period)
    if end >= local_time(cutoff).date():
        raise ValueError("Require a closed observation period before the explicit zoned cutoff")
    names = output_names(product)
    allowed = {workspace / "data" / (name + ".parquet") for name in names}
    if any(
        path not in allowed
        for layer in ("silver", "gold")
        for path in (workspace / "data" / layer).rglob("*.parquet")
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
        "calendar_completeness_certified": False,
        "ready_for_calendar_incorporation": False,
        "activation": "none",
        "publication": "not_authorized",
        "approval": "human_review_required",
        "scope": "all_observations_in_selected_retained_originals_not_verified_publication_calendar",
        "first_publication_date": None,
        "release_lag_days": None,
    }
    if not execute and not check:
        return {**base, "status": "planned_not_executed", "outputs": list(names)}
    accepted = workspace / "receipts" / f"series-{product}-{period}.json"
    prior = json.loads(accepted.read_text()) if check else None
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
        silver, details = read(product, inputs, period)
        outputs, evidence = frames(workspace, product, period, silver, details)
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
            "revisions": revisions(workspace, baseline, product, outputs),
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
        accepted.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
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
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "activation": "none"}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
