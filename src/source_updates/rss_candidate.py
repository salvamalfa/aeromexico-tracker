"""Certify retained RSS publication-declaration metadata offline, never publish news."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from src.pipeline.offline import block_network
from src.source_updates.calendar import local_time
from src.source_updates.catalog import ROOT
from src.source_updates.checks import require_replay_cutoff
from src.source_updates.collection import safe_workspace, writer
from src.source_updates.readiness import inventory
from src.source_updates.retained import digest
from src.source_updates.rss_contract import SCHEMA, envelopes, validate_bundle, validate_gold
from src.source_updates.rss_native import parse, window
from src.source_updates.rss_retention import inputs, retain

OUTPUTS = {
    "native": "silver/source_products/rss_native_metadata.json",
    "gold": "gold/fact_rss_declared_metadata.json",
    "artifacts": "gold/rss_source_artifacts.json",
    "lineage": "gold/rss_record_lineage.json",
}


def guard(workspace):
    if any(p.is_symlink() for p in workspace.rglob("*")):
        raise ValueError("RSS candidates cannot contain symlinks")


def fingerprints():
    paths = [
        *(ROOT / "src/source_updates").glob("*.py"),
        *(ROOT / "src/common").glob("*.py"),
        ROOT / "src/config.py",
        ROOT / "src/ingest/stage4_common.py",
        ROOT / "src/pipeline/offline.py",
        ROOT / "src/conversational_analytics/evidence_index.py",
        *(ROOT / "config").glob("*.yaml"),
        *(ROOT / "config").glob("source*.json"),
        SCHEMA,
        ROOT / "pyproject.toml",
        ROOT / "uv.lock",
    ]
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(set(paths))}


def semantic(row):
    fields = [
        "feed_id",
        "query_term",
        "query_url",
        "title",
        "url_as_reported",
        "guid",
        "publisher_name_as_declared",
        "publisher_url_as_declared",
        "pubdate_as_reported",
        "published_at_as_declared",
    ]
    return sorted(
        {
            json.dumps({k: r[k] for k in fields}, sort_keys=True, ensure_ascii=False)
            for r in row["contributors"]
        }
    )


def revisions(workspace, baseline, current):
    if baseline is None:
        return {"status": "not_compared_no_baseline"}
    path = (workspace / baseline).resolve()
    if not path.is_relative_to((workspace / "baselines").resolve()):
        raise ValueError("RSS baseline must remain within candidate baselines/")
    before = json.loads(path.read_text())
    validate_gold(before)
    if any(before[k] != current[k] for k in ("kind", "period", "date_basis", "query_scope")):
        raise ValueError("RSS baseline needs identical month, query scope and declaration semantics")
    key = lambda row: (row["canonical_url"], row["local_publication_date"])
    old, new = ({key(r): semantic(r) for r in p["rows"]} for p in (before, current))
    if len(old) != len(before["rows"]):
        raise ValueError("RSS baseline has duplicate natural grain")
    common = old.keys() & new.keys()
    changed = sum(old[k] != new[k] for k in common)
    return dict(
        status="metadata_comparison_not_publisher_revision_verification",
        baseline_file=baseline,
        baseline_sha256=digest(path),
        added=len(new.keys() - old.keys()),
        removed=len(old.keys() - new.keys()),
        changed=changed,
        unchanged=len(common) - changed,
        repeat_captures_do_not_count_as_metadata_revisions=True,
    )


def run(workspace: Path, period: str, cutoff: str, run_id: str, *, execute=False, check=False, baseline=None):
    workspace = safe_workspace(workspace)
    guard(workspace)
    window(period, cutoff)
    if execute and check or not isinstance(run_id, str) or not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise ValueError("Choose one RSS execution mode")
    base = dict(
        version=1,
        product="rss",
        period=period,
        effective_as_of=cutoff,
        retention_run_id=run_id,
        network_requests=0,
        paid_requests=0,
        new_source_capture=False,
        latest_source_availability_verified=False,
        first_publication_date=None,
        release_lag_days=None,
        latest_available_period=None,
        latest_validated_period=period,
        latest_published_tracker_period=None,
        ready_for_calendar_incorporation=False,
        activation="none",
        publication="not_authorized",
        approval="human_review_required",
        scope="retained_RSS_declared_metadata_partial_queries_not_publisher_body_verification",
    )
    if not execute and not check:
        return {**base, "status": "planned_not_executed", "outputs": OUTPUTS}
    accepted = workspace / "receipts" / f"rss-{period}.json"
    allowed = {workspace / "data" / n for n in OUTPUTS.values()}
    if any(
        p not in allowed
        for layer in ("silver", "gold")
        for p in (workspace / "data" / layer).rglob("*")
        if p.is_file()
    ):
        raise ValueError("Use an isolated complete RSS product workspace")
    if execute and (accepted.exists() or any(p.exists() for p in allowed)):
        raise ValueError("RSS accepted/partial outputs are immutable; use a new workspace")
    prior = json.loads(accepted.read_text()) if check else None
    before = inventory(workspace) if check else None
    if check:
        require_replay_cutoff(prior, cutoff)
        old_baseline = prior.get("revisions", {}).get("baseline_file")
        if baseline is not None and baseline != old_baseline:
            raise ValueError("Accepted RSS baseline selection changed")
        baseline = old_baseline

    def evaluate():
        originals, receipt_hash = inputs(workspace, run_id, cutoff)
        tables, details = parse(originals, period, cutoff)
        outputs = envelopes(tables, period, details["query_scope"])
        lineage = validate_bundle(outputs)
        result = {
            **base,
            **details,
            "status": "checks_passed",
            "lineage": lineage,
            "rows": {OUTPUTS[k]: len(p["rows"]) for k, p in outputs.items()},
            "retention_receipt_sha256": receipt_hash,
            "code_files": fingerprints(),
            "revisions": revisions(workspace, baseline, outputs["gold"]),
            "capture_dates": sorted({r["downloaded_at"] for _, r in originals}),
        }
        serialized = {
            OUTPUTS[k]: json.dumps(p, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
            for k, p in outputs.items()
        }
        return serialized, result

    if check:
        with block_network():
            outputs, result = evaluate()
            for name, text in outputs.items():
                if (workspace / "data" / name).read_text() != text:
                    raise ValueError(f"RSS output differs from complete physical-source replay: {name}")
            result["output_sha256"] = {n: digest(workspace / "data" / n) for n in outputs}
        if result != {k: v for k, v in prior.items() if k not in {"checked_at", "code_head"}}:
            raise ValueError("Accepted RSS sources, code, cutoff, baseline, receipt or outputs changed")
        if inventory(workspace) != before:
            raise ValueError("RSS candidate changed during readonly replay")
        return result
    with writer(workspace), block_network():
        if accepted.exists() or any(p.exists() for p in allowed):
            raise ValueError("RSS outputs immutable; use a new workspace")
        outputs, result = evaluate()  # Complete verification before any Silver/Gold output.
        for name, text in outputs.items():
            path = workspace / "data" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + ".tmp")
            temporary.write_text(text)
            temporary.replace(path)
        result["output_sha256"] = {n: digest(workspace / "data" / n) for n in outputs}
        result["checked_at"] = datetime.now(UTC).isoformat()
        result["code_head"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        accepted.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return result


def batch(recipe, workspace, *, execute=False):
    if (
        not isinstance(recipe, dict)
        or set(recipe) != {"version", "as_of", "source_root", "period", "originals"}
        or type(recipe["version"]) is not int
        or recipe["version"] != 1
    ):
        raise ValueError("RSS batch needs exact version1 recipe fields")
    window(recipe["period"], recipe["as_of"])
    workspace = safe_workspace(workspace)
    child = workspace / f"rss-{recipe['period']}"
    root = Path(recipe["source_root"])
    plan = retain(child, root, recipe["originals"])
    if any(local_time(r["downloaded_at"]) > local_time(recipe["as_of"]) for r in plan["originals"]):
        raise ValueError("RSS batch source capture is after cutoff")
    result = dict(
        status="planned_not_executed",
        retention=plan,
        certification=run(child, recipe["period"], recipe["as_of"], "0" * 32),
        workspace=str(child),
        recipe=recipe,
        network_requests=0,
        paid_requests=0,
        new_source_capture=False,
        activation="none",
        publication="not_authorized",
    )
    if not execute:
        return result
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError("RSS batch requires a new empty workspace")
    action = "retain"
    with writer(workspace):
        if any(p.name != ".source-update.lock" for p in workspace.iterdir()):
            raise ValueError("RSS batch changed before writer lock")
        try:
            saved = retain(child, root, recipe["originals"], execute=True)
            args = (child, recipe["period"], recipe["as_of"], saved["run_id"])
            action = "certify"
            certified = run(*args, execute=True)
            action = "offline_replay"
            verified = run(*args, check=True)
            if certified["output_sha256"] != verified["output_sha256"]:
                raise ValueError("RSS batch replay differs")
            result.update(status="checks_passed", result=certified, offline_replay_identical=True)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            result.update(
                status="blocked",
                failed_action=action,
                failed_target=str(child),
                error_type=type(exc).__name__,
                reason=str(exc),
                outcome="partial_evidence_preserved_no_publication",
            )
        result["finished_at"] = datetime.now(UTC).isoformat()
        (workspace / f"rss-round-{uuid4().hex}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["retain", "certify", "batch"])
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--original", action="append", default=[])
    parser.add_argument("--period")
    parser.add_argument("--as-of")
    parser.add_argument("--retention")
    parser.add_argument("--baseline")
    parser.add_argument("--recipe", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.mode == "batch":
            if args.recipe is None or args.check:
                raise ValueError("RSS batch requires recipe; replay accepted candidate with certify --check")
            result = batch(json.loads(args.recipe.read_text()), args.workspace, execute=args.execute)
        elif args.mode == "retain":
            if args.source_root is None or args.check:
                raise ValueError("RSS retention needs source-root; --check is certification only")
            result = retain(args.workspace, args.source_root, args.original, execute=args.execute)
        else:
            if not all((args.period, args.as_of, args.retention)):
                raise ValueError("RSS certification needs period, cutoff and retention receipt")
            result = run(
                args.workspace,
                args.period,
                args.as_of,
                args.retention,
                execute=args.execute,
                check=args.check,
                baseline=args.baseline,
            )
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(
            json.dumps(
                dict(status="blocked", error_type=type(exc).__name__, reason=str(exc), activation="none")
            )
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return int(result.get("status") == "blocked")


if __name__ == "__main__":
    raise SystemExit(main())
