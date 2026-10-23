"""Explicit offline batch orchestration for retained source snapshots, never a scheduled refresh."""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from src.source_updates.calendar import local_time
from src.source_updates.checks import period_end
from src.source_updates.collection import safe_workspace, writer
from src.source_updates.retained import retain, run, spec


def execute(recipe: dict, workspace: Path, *, write=False) -> dict:
    workspace = safe_workspace(workspace)
    if (
        recipe.get("version") != 1
        or not isinstance(recipe.get("items"), list)
        or not 1 <= len(recipe["items"]) <= 42
    ):
        raise ValueError("Retained batch v1 requires 1..42 explicit source products")
    cutoff = recipe["as_of"]
    local_time(cutoff)
    source_root = Path(recipe["source_root"])
    plans = []
    children = set()
    for item in recipe["items"]:
        product, period = item["product"], item["period"]
        definition = spec(product)
        if (
            not re.fullmatch(r"20\d{2}(?:M(?:0[1-9]|1[0-2])|Q[1-4])", period)
            or period_end(period) >= local_time(cutoff).date()
        ):
            raise ValueError(
                "Explicit closed review month/quarter required; "
                "reference snapshots keep native time semantics"
            )
        child = workspace / f"{product}-{period}"
        if child in children:
            raise ValueError("Duplicate retained product/review-period batch item")
        children.add(child)
        plan = retain(child, source_root, product, item["originals"])
        plans.append(
            dict(
                product=product,
                period=period,
                adapter=definition.get("certifier", "retained"),
                workspace=str(child),
                retention=plan,
                stages=[
                    "retain_exact_originals",
                    "verify_Bronze",
                    "parse_Silver",
                    "validate_candidate_Gold_lineage",
                    "offline_replay",
                ],
                baseline=item.get("baseline"),
            )
        )
        if item.get("baseline") is not None:
            raise ValueError(
                "Batch has no implicit baseline; use individual candidate with explicit baseline file"
            )
    output = dict(
        mode="execute" if write else "dry_run",
        new_source_capture=False,
        batch_id=uuid4().hex if write else None,
        as_of=cutoff,
        timezone="America/Mexico_City",
        products=len(plans),
        plan=plans,
        network_requests=0,
        paid_requests=0,
        latest_source_availability_verified=False,
        activation="none",
        publication="not_authorized",
    )
    if not write:
        return output
    if workspace.exists() and any(workspace.iterdir()):
        raise ValueError("Retained batch requires a new empty workspace")
    results = []
    with writer(workspace):
        if any(p.name != ".source-update.lock" for p in workspace.iterdir()):
            raise ValueError("Retained batch workspace changed before writer lock")
        for plan, item in zip(plans, recipe["items"], strict=True):
            child = Path(plan["workspace"])
            product = plan["product"]
            period = plan["period"]
            action = "retain"
            try:
                saved = retain(child, source_root, product, item["originals"], execute=True)
                args = (child, product, period, cutoff, saved["run_id"])
                if plan["adapter"] in {"series", "government"}:
                    from importlib import import_module

                    certify = import_module(f"src.source_updates.{plan['adapter']}_candidate").run
                else:
                    certify = run
                action = "certify"
                certified = certify(*args, execute=True)
                action = "offline_replay"
                verified = certify(*args, check=True)
                if certified["output_sha256"] != verified["output_sha256"]:
                    raise ValueError("Offline output replay changed")
                results.append(
                    dict(
                        product=product,
                        review_period=period,
                        status="checks_passed",
                        workspace=str(child),
                        rows=certified["rows"],
                        scope=certified["scope"],
                        output_sha256=certified["output_sha256"],
                        code_head=certified["code_head"],
                        records=certified["lineage"]["records_expected"],
                        artifacts=certified["lineage"]["artifact_count"],
                        retention_run_id=saved["run_id"],
                        offline_replay_identical=True,
                    )
                )
            except Exception as exc:
                output.update(
                    status="blocked",
                    failed_action=action,
                    error_type=type(exc).__name__,
                    failed_target=str(child),
                    reason=str(exc),
                    results=results,
                    remaining_products_not_started=len(plans) - len(results) - 1,
                    outcome="partial_evidence_preserved_no_publication",
                )
                break
        else:
            output.update(status="checks_passed", results=results)
        output["finished_at"] = datetime.now(UTC).isoformat()
        (workspace / f"retained-round-{output['batch_id']}.json").write_text(
            json.dumps(output, ensure_ascii=False, indent=2) + "\n"
        )
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = execute(json.loads(args.recipe.read_text()), args.workspace, write=args.execute)
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps(dict(status="blocked", reason=str(exc), activation="none")))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result.get("status") == "blocked")


if __name__ == "__main__":
    raise SystemExit(main())
