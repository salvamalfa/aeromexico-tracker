"""Replay an explicit candidate round offline; never acquire, schedule or publish."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

from src.pipeline.offline import block_network
from src.source_updates.calendar import local_time
from src.source_updates.catalog import product_map
from src.source_updates.checks import period_end
from src.source_updates.collection import safe_workspace, writer

ADAPTER_PRODUCTS = {
    "am_traffic_ir": "am_traffic_ir",
    "h10": "h10",
    "aerocivil": "aerocivil",
    "gdelt": "gdelt",
}
RECEIPT_NAMES = {
    "am_traffic_ir": "am-traffic-{period}.json",
    "h10": "h10-{period}.json",
    "aerocivil": "aerocivil-{period}.json",
    "gdelt": "gdelt-{period}.json",
    "retained": "certified-{product}-{period}.json",
    "government": "government-{product}-{period}.json",
    "series": "series-{product}-{period}.json",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recipe_hash(recipe: dict) -> str:
    return hashlib.sha256(json.dumps(recipe, sort_keys=True, allow_nan=False).encode()).hexdigest()


def preflight(recipe: dict, workspace: Path) -> list[dict]:
    """Validate all static inputs without reading a receipt, table or source body."""
    workspace = safe_workspace(workspace)
    if not isinstance(recipe, dict) or type(recipe.get("version")) is not int or recipe["version"] != 1:
        raise ValueError("Readiness recipe requires version1")
    if set(recipe) != {"version", "as_of", "required_items", "items"}:
        raise ValueError("Readiness recipe fields must be explicit")
    if not isinstance(recipe["as_of"], str):
        raise ValueError("Readiness cutoff requires a zoned timestamp")
    cutoff = local_time(recipe["as_of"])
    items, required = recipe["items"], recipe["required_items"]
    if not isinstance(items, list) or not 1 <= len(items) <= 84:
        raise ValueError("Choose1..84 explicit source/product/period tasks")
    if (
        not isinstance(required, list)
        or not required
        or any(not isinstance(key, str) or not key for key in required)
        or len(set(required)) != len(required)
    ):
        raise ValueError("Declare unique nonempty required task IDs before execution")
    plans, ids, locations, grains = [], set(), set(), set()
    products = product_map()
    for item in items:
        if not isinstance(item, dict) or set(item) != {
            "id",
            "product",
            "period",
            "adapter",
            "workspace",
            "receipt_id",
            "required",
            "candidate_as_of",
        }:
            raise ValueError("Each readiness task needs its exact fields")
        if (
            not isinstance(item["id"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]+", item["id"])
            or item["id"] in ids
        ):
            raise ValueError("Readiness task IDs must be safe and unique")
        if type(item["required"]) is not bool:
            raise ValueError("Task required must be a boolean")
        if not all(
            isinstance(item[key], str)
            for key in ("product", "period", "adapter", "workspace", "receipt_id", "candidate_as_of")
        ):
            raise ValueError("Task identities, period, workspace and receipt ID must be strings")
        product, adapter, period = item["product"], item["adapter"], item["period"]
        candidate_cutoff = local_time(item["candidate_as_of"])
        if candidate_cutoff > cutoff:
            raise ValueError("Candidate cutoff is after the round verification cutoff")
        if product not in products or adapter not in RECEIPT_NAMES:
            raise ValueError("Unknown source product or offline adapter")
        if (
            not re.fullmatch(r"20\d{2}(?:M(?:0[1-9]|1[0-2])|Q[1-4])", period)
            or period_end(period) >= candidate_cutoff.date()
        ):
            raise ValueError("Every observation/review period must be closed before cutoff")
        if adapter in {"retained", "government", "series"}:
            from src.source_updates.retained import spec

            definition = spec(product)
            expected_adapter = definition.get("certifier", "retained")
            if adapter != expected_adapter:
                raise ValueError(f"Use {expected_adapter} adapter for complete product certification")
        elif ADAPTER_PRODUCTS[adapter] != product:
            raise ValueError("Dedicated adapter does not support the declared product")
        if adapter not in {"retained", "series"} and "M" not in period:
            raise ValueError("Dedicated monthly adapter needs an explicit month")
        if not re.fullmatch(r"[0-9a-f]{32}", item["receipt_id"]):
            raise ValueError("Expected an exact acquisition/retention receipt ID")
        candidate = safe_workspace(Path(item["workspace"]))
        if (
            candidate == workspace
            or candidate.is_relative_to(workspace)
            or workspace.is_relative_to(candidate)
        ):
            raise ValueError("Readiness receipt and source candidates must have disjoint workspaces")
        if any(
            candidate == prior or candidate.is_relative_to(prior) or prior.is_relative_to(candidate)
            for prior in locations
        ):
            raise ValueError("Each source task needs a separate disjoint candidate workspace")
        if (product, period) in grains:
            raise ValueError("Duplicate source product/review period")
        ids.add(item["id"])
        locations.add(candidate)
        grains.add((product, period))
        plans.append({**item, "workspace": str(candidate)})
    if set(required) != {item["id"] for item in items if item["required"]}:
        raise ValueError("Required task list differs from declared tasks; omitted tasks cannot pass")
    return plans


def inventory(workspace: Path) -> dict:
    if (workspace / ".source-update.lock").exists():
        raise ValueError("Source candidate has an active writer")
    return {
        str(path.relative_to(workspace)): sha(path) for path in sorted(workspace.rglob("*")) if path.is_file()
    }


def check_task(item: dict, cutoff: str) -> dict:
    candidate = Path(item["workspace"])
    before = inventory(candidate)
    retained = item["adapter"] in {"retained", "government", "series"}
    prefix = "retained" if retained else "collection"
    acquisition = candidate / "receipts" / f"{prefix}-{item['receipt_id']}.json"
    acquired = json.loads(acquisition.read_text())
    expected_status = "retained_unvalidated" if retained else "collected_unvalidated"
    if acquired.get("status") != expected_status:
        statuses = [row.get("http_status") for row in acquired.get("items", [])]
        raise ValueError(
            f"Selected acquisition is incomplete, HTTP statuses={statuses}; no valid source candidate"
        )
    name = RECEIPT_NAMES[item["adapter"]].format(product=item["product"], period=item["period"])
    accepted_path = candidate / "receipts" / name
    accepted = json.loads(accepted_path.read_text())
    key = "retention_run_id" if retained else "collection_run_id"
    if accepted.get(key) != item["receipt_id"]:
        raise ValueError("Accepted receipt does not match the explicitly selected acquisition")
    if (
        accepted.get("status") != "checks_passed"
        or accepted.get("activation") != "none"
        or accepted.get("publication") != "not_authorized"
    ):
        raise ValueError(
            "Accepted source receipt must record passed candidate checks without activation/publication"
        )
    if not isinstance(accepted.get("effective_as_of"), str) or not accepted["effective_as_of"].strip():
        raise ValueError("Accepted source receipt requires its explicit zoned cutoff")
    if local_time(accepted["effective_as_of"]) != local_time(cutoff):
        raise ValueError("Replay cutoff differs from accepted candidate; use its exact cutoff")
    with block_network():
        if item["adapter"] in {"government", "series"}:
            run = import_module(f"src.source_updates.{item['adapter']}_candidate").run

            result = run(candidate, item["product"], item["period"], cutoff, item["receipt_id"], check=True)
        elif item["adapter"] == "retained":
            from src.source_updates.retained import run

            result = run(candidate, item["product"], item["period"], cutoff, item["receipt_id"], check=True)
        elif item["adapter"] == "h10":
            from src.source_updates.h10 import run

            result = run(candidate, item["period"], cutoff, check=True)
        else:
            name = {"aerocivil": "aerocivil", "am_traffic_ir": "am_traffic_candidate", "gdelt": "gdelt"}[
                item["adapter"]
            ]
            module = import_module(f"src.source_updates.{name}")
            result = module.run(candidate, item["period"], cutoff, item["receipt_id"], check=True)
    if inventory(candidate) != before:
        raise ValueError("Offline checker changed source candidate files")
    if result.get("status") != "checks_passed" or not result.get("output_sha256"):
        raise ValueError("Candidate did not pass its actual offline checks with output hashes")
    if result.get("activation") != "none" or result.get("publication") != "not_authorized":
        raise ValueError("Offline checker returned an activation/publication claim")
    code_files, code_sha = result.get("code_files"), result.get("code_sha256")
    if (
        code_files is not None
        and (
            not isinstance(code_files, dict)
            or not code_files
            or any(
                not isinstance(key, str)
                or not isinstance(value, str)
                or not re.fullmatch(r"[0-9a-f]{64}", value)
                for key, value in code_files.items()
            )
        )
        or code_sha is not None
        and (not isinstance(code_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", code_sha))
        or code_files is None
        and code_sha is None
    ):
        raise ValueError("Offline checker must report its actual code fingerprints")
    conditions = []
    if retained:
        conditions.append("retained_original_does_not_verify_current_source_availability")
    if result.get("calendar_completeness_certified") is False:
        conditions.append("publication_calendar_completeness_not_verified")
    if result.get("service_code_mapping_verified") is False:
        conditions.append("official_service_code_legend_pending")
    if result.get("complete_month_certified") is False:
        conditions.append("source_does_not_certify_complete_month")
    return {
        "id": item["id"],
        "product": item["product"],
        "period": item["period"],
        "candidate_as_of": cutoff,
        "adapter": item["adapter"],
        "required": item["required"],
        "status": "checks_passed",
        "scope": result.get("scope", result.get("scope_basis", "explicit_observation_metadata_only")),
        "rows": result.get("rows", result.get("accepted_rows")),
        "accepted_receipt_sha256": sha(accepted_path),
        "acquisition_receipt_sha256": sha(acquisition),
        "output_sha256": result["output_sha256"],
        "checker_code_files": code_files,
        "checker_code_sha256": code_sha,
        "source_candidate_files_unchanged": len(before),
        "collection_basis": "retained" if retained else "previously_captured_originals",
        "source_conditions": conditions,
        "latest_source_availability_verified": False,
        "activation": "none",
        "publication": "not_authorized",
    }


def execute(recipe: dict, workspace: Path, *, write=False, check=False) -> dict:
    if write and check:
        raise ValueError("Choose write or read-only check")
    plans = preflight(recipe, workspace)
    workspace = safe_workspace(workspace)
    output = {
        "version": 1,
        "mode": "offline_check" if check else "execute" if write else "dry_run",
        "recipe_sha256": recipe_hash(recipe),
        "verifier_code_sha256": sha(Path(__file__)),
        "as_of": recipe["as_of"],
        "timezone": "America/Mexico_City",
        "plan": plans,
        "scope": "explicit_recipe_tasks_only_not_full_source_catalogue",
        "catalogue_products_not_exercised": sorted(set(product_map()) - {item["product"] for item in plans}),
        "network_requests": 0,
        "paid_requests": 0,
        "new_source_capture": False,
        "ready_for_review": False,
        "ready_for_calendar_incorporation": False,
        "ready_for_automatic_execution": False,
        "scheduled_executions": 0,
        "latest_source_availability_verified": False,
        "activation": "none",
        "publication": "not_authorized",
    }
    if not write and not check:
        return {**output, "status": "planned_not_executed"}
    accepted = workspace / "readiness.json"
    prior = json.loads(accepted.read_text()) if check else None
    if check and prior.get("recipe_sha256") != output["recipe_sha256"]:
        raise ValueError("Readiness recipe differs from immutable receipt")
    if check and prior.get("verifier_code_sha256") != output["verifier_code_sha256"]:
        raise ValueError("Readiness verifier changed; prepare a new review receipt")
    if write and workspace.exists() and any(workspace.iterdir()):
        raise ValueError("Readiness receipt requires a new empty workspace")

    def verify_all():
        results, stopped = [], False
        for item in plans:
            if stopped:
                results.append(
                    {
                        "id": item["id"],
                        "required": item["required"],
                        "status": "not_started_after_required_failure",
                    }
                )
                continue
            try:
                results.append(check_task(item, item["candidate_as_of"]))
            except Exception as exc:
                results.append(
                    {
                        "id": item["id"],
                        "product": item["product"],
                        "period": item["period"],
                        "required": item["required"],
                        "status": "blocked",
                        "error_type": type(exc).__name__,
                        "reason": str(exc),
                    }
                )
                stopped = item["required"]
        output["results"] = results
        output["ready_for_review"] = all(
            row["status"] == "checks_passed" for row in results if row["required"]
        )
        output["status"] = "checks_passed" if output["ready_for_review"] else "blocked_required_source"
        output["optional_tasks_blocked"] = [
            row["id"] for row in results if not row["required"] and row["status"] != "checks_passed"
        ]

    if check:
        verify_all()
        ignored = {"mode", "finished_at"}
        if {k: v for k, v in output.items() if k not in ignored} != {
            k: v for k, v in prior.items() if k not in ignored
        }:
            raise ValueError("Readiness replay differs from recorded source checks")
        output["receipt_sha256"] = sha(accepted)
        return output
    with writer(workspace):
        if any(path.name != ".source-update.lock" for path in workspace.iterdir()):
            raise ValueError("Readiness workspace changed before writer lock")
        verify_all()
        output["finished_at"] = datetime.now(UTC).isoformat()
        accepted.write_text(json.dumps(output, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = execute(
            json.loads(args.recipe.read_text()), args.workspace, write=args.execute, check=args.check
        )
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "activation": "none"}))
        return 1
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return int(result["status"].startswith("blocked"))


if __name__ == "__main__":
    raise SystemExit(main())
