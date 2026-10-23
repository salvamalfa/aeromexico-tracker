"""Fail-closed global policy over actual, read-only source-candidate replays.

A subset receipt is never a complete round. Unknown availability and unsupported
whole-product adapters stay blocked; user-supplied check results are not inputs.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from src.pipeline.offline import block_network
from src.source_updates import readiness
from src.source_updates.calendar import business_day, local_time, monthly, quarterly
from src.source_updates.catalog import ROOT, product_map
from src.source_updates.checks import period_end
from src.source_updates.collection import safe_workspace, writer

REQUIRED = {
    "monthly": frozenset(
        (
            "am_traffic_ir volaris_sec viva_traffic afac_carriers afac_airports bts_segments "
            "gap_traffic asur_traffic oma_traffic aicm_traffic aifa_traffic banxico fuel equities rss gdelt"
        ).split()
    ),
    "quarterly": frozenset(
        "am_financials volaris_sec viva_financials banxico fuel equities aerocivil".split()
    ),
}
CONDITIONAL = {
    "monthly": frozenset("am_sec afac_countries afac_margins h10 derived".split()),
    "quarterly": frozenset(
        (
            "am_sec bmv_xbrl h10 aicm_slots airports_reference dictionary peer_profiles "
            "curated_context derived aena"
        ).split()
    ),
}
OPTIONAL = {
    "monthly": frozenset(),
    "quarterly": frozenset(
        "delta_sec ryanair_sec ryanair_ir anac caa am_routes oma_routes colima aifa_roster iasa".split()
    ),
}
FINANCIALS = {"AEROMEXICO": "am_financials", "VOLARIS": "volaris_sec", "VIVA_AEROBUS": "viva_financials"}
GUARDS = {("quarterly", "aerocivil"), ("monthly", "gdelt")}
ITEM_FIELDS = {
    "id",
    "product",
    "cadence",
    "period",
    "used",
    "depends_on",
    "adapter",
    "workspace",
    "receipt_id",
    "candidate_as_of",
}
RECIPE_FIELDS = {"version", "round", "as_of", "monthly_period", "quarterly_period", "items", "releases"}
RELEASE_FIELDS = {
    "entity",
    "period",
    "kind",
    "confirmed",
    "published_at",
    "document_url",
    "source_sha256",
    "task_id",
}


def policy() -> dict:
    """Catalogue drift requires a deliberate policy review, never a silent omission."""
    all_products = set()
    for cadence in REQUIRED:
        groups = [REQUIRED[cadence], CONDITIONAL[cadence], OPTIONAL[cadence]]
        if any(left & right for i, left in enumerate(groups) for right in groups[i + 1 :]):
            raise ValueError("Overlapping global policy classifications")
        classified = set().union(*groups)
        if classified != {
            name for name, definition in product_map().items() if definition["cadence"] in (cadence, "both")
        }:
            raise ValueError("Global policy cadence differs from catalogue")
        all_products.update(classified)
    if all_products | {"news_errors"} != set(product_map()):
        raise ValueError("Global policy differs from catalogue; review classifications")
    return {
        cadence: {
            name: sorted(group[cadence])
            for name, group in (("required", REQUIRED), ("conditional", CONDITIONAL), ("optional", OPTIONAL))
        }
        for cadence in REQUIRED
    }


def preflight(recipe: dict) -> list[dict]:
    policy()
    if (
        not isinstance(recipe, dict)
        or set(recipe) != RECIPE_FIELDS
        or type(recipe["version"]) is not int
        or recipe["version"] != 1
    ):
        raise ValueError(
            "Global recipe requires exact version1 fields; results/required overrides are forbidden"
        )
    if recipe["round"] not in {"monthly", "quarterly", "combined"}:
        raise ValueError("Unknown round")
    cutoff = local_time(recipe["as_of"])
    for cadence, pattern in (("monthly", r"20\d{2}M(?:0[1-9]|1[0-2])"), ("quarterly", r"20\d{2}Q[1-4]")):
        period = recipe[cadence + "_period"]
        if (
            not isinstance(period, str)
            or not re.fullmatch(pattern, period)
            or period_end(period) >= cutoff.date()
        ):
            raise ValueError("Both context periods must be explicit and closed before cutoff")
    if not isinstance(recipe["items"], list) or len(recipe["items"]) > 84:
        raise ValueError("Expected at most84 explicit candidate tasks")
    if not isinstance(recipe["releases"], list):
        raise ValueError("Releases must be an explicit list, empty when unknown")
    ids, grains = set(), set()
    for item in recipe["items"]:
        if not isinstance(item, dict) or set(item) not in (ITEM_FIELDS, ITEM_FIELDS | {"source_period"}):
            raise ValueError(
                "Each global task needs exact fields, with no metric/filter/equivalence override"
            )
        if (
            not isinstance(item["id"], str)
            or not re.fullmatch(r"[A-Za-z0-9_-]+", item["id"])
            or item["id"] in ids
        ):
            raise ValueError("Unique safe task IDs required")
        cadence, product = item["cadence"], item["product"]
        if cadence not in REQUIRED or product not in (
            REQUIRED[cadence] | CONDITIONAL[cadence] | OPTIONAL[cadence]
        ):
            raise ValueError("Product/cadence outside approved policy")
        if item["period"] != recipe[cadence + "_period"]:
            raise ValueError("Task period differs from its declared cadence context")
        source_period = item.get("source_period", item["period"])
        if not isinstance(source_period, str) or not re.fullmatch(
            r"20\d{2}(?:M(?:0[1-9]|1[0-2])|Q[1-4])", source_period
        ):
            raise ValueError("Native source period must be an explicit month or quarter")
        source_end, target_end = period_end(source_period), period_end(item["period"])
        lagged = {
            "afac_carriers",
            "afac_airports",
            "afac_countries",
            "afac_margins",
            "bts_segments",
            "aicm_traffic",
            "aifa_traffic",
        }
        if source_period != item["period"]:
            if product == "aerocivil":
                quarter_start_month = (int(item["period"][-1]) - 1) * 3 + 1
                if (
                    "M" not in source_period
                    or source_period[:4] != item["period"][:4]
                    or not quarter_start_month <= int(source_period[5:]) <= quarter_start_month + 2
                ):
                    raise ValueError(
                        "Aerocivil native month must belong to the declared quarter; no full-quarter claim"
                    )
            elif (
                cadence != "monthly"
                or product not in lagged
                or "M" not in source_period
                or source_end > target_end
            ):
                raise ValueError("Native period is not equivalent to the requested product period")
        if (cadence, product) in grains:
            raise ValueError("Duplicate product/cadence; separate monthly and quarterly periods")
        if type(item["used"]) is not bool:
            raise ValueError("used must be boolean")
        if (
            not isinstance(item["depends_on"], list)
            or any(not isinstance(x, str) for x in item["depends_on"])
            or len(set(item["depends_on"])) != len(item["depends_on"])
        ):
            raise ValueError("Dependencies must be unique task IDs")
        if item["adapter"] not in {*readiness.RECEIPT_NAMES, "unsupported"}:
            raise ValueError(
                "Only whole-product offline adapters are accepted, never caller-selected generic checks"
            )
        for key in ("workspace", "receipt_id", "candidate_as_of"):
            if not isinstance(item[key], str):
                raise ValueError("Candidate bindings must be strings")
        stamp = local_time(item["candidate_as_of"])
        if stamp > cutoff or period_end(item.get("source_period", item["period"])) >= stamp.date():
            raise ValueError("Candidate cutoff must cover its closed period and not exceed round cutoff")
        ids.add(item["id"])
        grains.add((cadence, product))
    by_id = {item["id"]: item for item in recipe["items"]}
    visiting, visited = set(), set()

    def visit(key):
        if key in visiting:
            raise ValueError("Dependency cycle")
        if key in visited:
            return
        visiting.add(key)
        item = by_id[key]
        for parent in item["depends_on"]:
            if parent not in by_id or not by_id[parent]["used"]:
                raise ValueError("Missing/unused dependency; dependencies cannot hide used data")
            visit(parent)
        visiting.remove(key)
        visited.add(key)

    for key in by_id:
        visit(key)
    for release in recipe["releases"]:
        if not isinstance(release, dict) or set(release) != RELEASE_FIELDS:
            raise ValueError("Release requires exact physical-artifact binding fields")
        if (
            release["entity"] not in FINANCIALS
            or release["period"] != recipe["quarterly_period"]
            or release["kind"] != "financial_report"
            or release["confirmed"] is not True
        ):
            raise ValueError("Release must be a reviewed actual central report of the exact quarter")
        item = by_id.get(release["task_id"])
        if not item or (item["cadence"], item["product"], item["used"]) != (
            "quarterly",
            FINANCIALS[release["entity"]],
            True,
        ):
            raise ValueError("Release bound to wrong financial entity/task")
        if not isinstance(release["source_sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", release["source_sha256"]
        ):
            raise ValueError("Release requires source SHA-256")
        stamp = local_time(release["published_at"])
        if not period_end(release["period"]) < stamp.date() or stamp > local_time(item["candidate_as_of"]):
            raise ValueError("Release timestamp outside closed-quarter/candidate cutoff")
    return recipe["items"]


def evaluate(recipe: dict, outcomes: dict) -> dict:
    """Pure policy decision; outcomes come only from our actual checkers in execute.

    Synthetic outcomes in unit tests exercise the decision contract, not sources.
    """
    items = preflight(recipe)
    cadences = set(REQUIRED) if recipe["round"] == "combined" else {recipe["round"]}
    indexed = {(i["cadence"], i["product"]): i for i in items}
    blockers, core_blockers, calendar_blockers = [], [], []
    required = {(c, p) for c in cadences for p in REQUIRED[c]}
    for cadence, product in sorted(required):
        item = indexed.get((cadence, product))
        if item is None:
            core_blockers.append(f"{cadence}:{product}:missing")
        elif not item["used"]:
            core_blockers.append(f"{cadence}:{product}:required_cannot_be_unused")
    for item in items:
        if not item["used"]:
            continue
        result = outcomes.get(item["id"], {})
        reason = None
        if result.get("status") != "checks_passed":
            reason = "not_verified"
        elif item["product"] == "aerocivil" and (
            result.get("semantic_acceptance_verified") is not True
            or "official_service_code_legend_pending" in result.get("source_conditions", [])
        ):
            reason = "official_service_code_legend_pending"
        if reason:
            message = f"{item['cadence']}:{item['product']}:{reason}"
            blockers.append(message)
            if (item["cadence"], item["product"]) in required:
                core_blockers.append(message)
        if result.get("latest_source_availability_verified") is not True:
            calendar_blockers.append(f"{item['id']}:current_source_availability_not_verified")
    # A required result is invalid when any transitive used dependency fails.
    by_id = {i["id"]: i for i in items}

    dependency_cache = {}

    def dependencies_verified(item):
        if item["id"] in dependency_cache:
            return dependency_cache[item["id"]]
        valid = all(
            outcomes.get(key, {}).get("status") == "checks_passed"
            and (
                by_id[key]["product"] != "aerocivil"
                or (
                    outcomes[key].get("semantic_acceptance_verified") is True
                    and "official_service_code_legend_pending"
                    not in outcomes[key].get("source_conditions", [])
                )
            )
            and dependencies_verified(by_id[key])
            for key in item["depends_on"]
        )
        dependency_cache[item["id"]] = valid
        return valid

    for item in items:
        if item["used"] and not dependencies_verified(item):
            reason = f"{item['cadence']}:{item['product']}:dependency_not_verified"
            blockers.append(reason)
            if (item["cadence"], item["product"]) in required:
                core_blockers.append(reason)
    blockers = sorted(set(blockers + core_blockers))
    for key in sorted(GUARDS):
        item = indexed.get(key)
        result = outcomes.get(item["id"], {}) if item else {}
        if (
            not item
            or not item["used"]
            or result.get("status") != "checks_passed"
            or (
                key[1] == "aerocivil"
                and (
                    result.get("semantic_acceptance_verified") is not True
                    or "official_service_code_legend_pending" in result.get("source_conditions", [])
                )
            )
        ):
            calendar_blockers.append(f"{key[0]}:{key[1]}:required_calendar_prerequisite_not_verified")
    holidays = json.loads((ROOT / "config/source_update_holidays.json").read_text())
    try:
        # Check year even on a weekend: business_day checks verified year first.
        business_day(local_time(recipe["as_of"]).date(), holidays)
    except ValueError as exc:
        calendar_blockers.append(str(exc))
    monthly_due, quarterly_due = None, None
    if "monthly" in cadences:
        try:
            end = period_end(recipe["monthly_period"])
            next_month = end + timedelta(days=1)
            monthly_due = monthly(next_month.year, next_month.month, holidays)
        except ValueError as exc:
            calendar_blockers.append(str(exc))
    if "quarterly" in cadences:
        accepted_releases = []
        for release in recipe["releases"]:
            result = outcomes.get(release["task_id"], {})
            identity = {"source_url": release["document_url"], "sha256": release["source_sha256"]}
            if result.get("status") == "checks_passed" and identity in result.get(
                "contributing_artifacts", []
            ):
                accepted_releases.append(release)
            else:
                calendar_blockers.append(
                    f"{release['entity']}:release_not_bound_to_verified_contributing_artifact"
                )
        try:
            schedule = quarterly(recipe["quarterly_period"], accepted_releases, recipe["as_of"], holidays)
            if schedule["date"]:
                quarterly_due = date.fromisoformat(schedule["date"])
            if schedule["missing_central_reports"]:
                calendar_blockers.append(
                    "missing_verified_central_reports:" + ",".join(schedule["missing_central_reports"])
                )
        except ValueError as exc:
            calendar_blockers.append(str(exc))
    if recipe["round"] == "combined" and monthly_due and quarterly_due:
        if abs((monthly_due - quarterly_due).days) > 7:
            calendar_blockers.append("combined_rounds_more_than_seven_calendar_days_apart")
    return {
        "monthly_date": monthly_due.isoformat() if monthly_due else None,
        "quarterly_date": quarterly_due.isoformat() if quarterly_due else None,
        "core_ready": not core_blockers,
        "requested_bundle_ready": not blockers,
        "ready_for_calendar_incorporation": not blockers and not calendar_blockers,
        "ready_for_automatic_execution": False,
        "blockers": blockers,
        "calendar_blockers": sorted(set(calendar_blockers)),
        "activation": "none",
        "publication": "not_authorized",
    }


def fingerprints() -> dict:
    # Freeze complete reusable verifier/parsers/contracts, not only this wrapper.
    paths = [
        p
        for folder in ("src", "config", "contracts")
        for p in (ROOT / folder).rglob("*")
        if p.is_file() and p.suffix in {".py", ".yaml", ".json"} and "__pycache__" not in p.parts
    ]
    return {p.relative_to(ROOT).as_posix(): readiness.sha(p) for p in sorted(paths)}


def verify(item: dict, workspace: Path) -> dict:
    if item["adapter"] == "unsupported":
        raise ValueError("No whole-product offline adapter; subset checks cannot certify required metrics")
    task = {
        k: item[k]
        for k in ("id", "product", "period", "adapter", "workspace", "receipt_id", "candidate_as_of")
    }
    task["period"] = item.get("source_period", item["period"])
    task["required"] = True
    readiness.preflight(
        {"version": 1, "as_of": item["candidate_as_of"], "required_items": [item["id"]], "items": [task]},
        workspace,
    )
    candidate = Path(item["workspace"])
    before = readiness.inventory(candidate)
    result = readiness.check_task(task, item["candidate_as_of"])
    result.update(target_period=item["period"], source_period=task["period"])
    if item["product"] == "aerocivil":
        # Actual adapter currently reports pending legend/attribution. Never
        # infer semantic acceptance from its numeric checks or missing flags.
        result["semantic_acceptance_verified"] = False
    # Only artifacts actually used by verified record lineage can bind a release.
    # This records documentary identity; the publication timestamp is still the
    # explicit human review assertion, never inferred from download time.
    outputs = result["output_sha256"]
    if {"gold/dim_source_artifact", "gold/bridge_record_lineage"} <= set(outputs):
        import pandas as pd

        artifacts = pd.read_parquet(candidate / "data/gold/dim_source_artifact.parquet")
        bridge = pd.read_parquet(candidate / "data/gold/bridge_record_lineage.parquet")
        if item["product"] == "viva_financials":
            # Q1 support is present in native Silver lineage, but cannot bind a Q2 release.
            # Here contributing_artifacts means release-eligible artifacts, not all support.
            # Only the fully checked, directly reported Q2-edition Gold facts confer that role.
            from src.source_updates.viva_financial_spec import TABLE

            bridge = bridge.loc[bridge.table_name.eq(TABLE)]
        used = artifacts.loc[artifacts.artifact_id.isin(bridge.artifact_id.dropna())]
        result["contributing_artifacts"] = sorted(
            ({"source_url": r.source_url, "sha256": r.artifact_sha256} for r in used.itertuples(index=False)),
            key=lambda row: (row["source_url"], row["sha256"]),
        )
    if readiness.inventory(candidate) != before:
        raise ValueError("Source files changed during checker/release binding")
    return result


def execute(recipe: dict, workspace: Path, *, write=False, check=False) -> dict:
    if write and check:
        raise ValueError("Choose write or check")
    plans = preflight(recipe)
    workspace = safe_workspace(workspace)
    # Check workspace disjointness before any source checker is called.
    locations = []
    for item in plans:
        if not item["used"] or item["adapter"] == "unsupported":
            continue
        path = safe_workspace(Path(item["workspace"]))
        if (
            path == workspace
            or path.is_relative_to(workspace)
            or workspace.is_relative_to(path)
            or any(path == p or path.is_relative_to(p) or p.is_relative_to(path) for p in locations)
        ):
            raise ValueError("Source candidates and global receipt must have disjoint workspaces")
        task = {
            k: item[k]
            for k in ("id", "product", "period", "adapter", "workspace", "receipt_id", "candidate_as_of")
        }
        task.update(period=item.get("source_period", item["period"]), required=True)
        readiness.preflight(
            {"version": 1, "as_of": item["candidate_as_of"], "required_items": [item["id"]], "items": [task]},
            workspace,
        )
        locations.append(path)
    output = {
        "version": 1,
        "as_of": recipe["as_of"],
        "timezone": "America/Mexico_City",
        "mode": "offline_check" if check else "execute" if write else "dry_run",
        "recipe_sha256": readiness.recipe_hash(recipe),
        "verifier_files": fingerprints(),
        "policy": policy(),
        "plan": plans,
        "network_requests": 0,
        "paid_requests": 0,
        "scheduled_executions": 0,
        "new_source_capture": False,
    }
    if not write and not check:
        return {**output, **evaluate(recipe, {}), "status": "planned_not_executed"}
    accepted = workspace / "global-readiness.json"
    prior = json.loads(accepted.read_text()) if check else None
    if check and (
        prior.get("recipe_sha256") != output["recipe_sha256"]
        or prior.get("verifier_files") != output["verifier_files"]
    ):
        raise ValueError(
            "Global recipe or verifier/contract/catalogue/calendar changed; new receipt required"
        )
    if write and workspace.exists() and any(workspace.iterdir()):
        raise ValueError("Global receipt requires a new empty workspace")

    def replay():
        results = {}
        with block_network():
            for item in plans:
                if not item["used"]:
                    continue
                try:
                    results[item["id"]] = verify(item, workspace)
                except Exception as exc:
                    results[item["id"]] = {
                        "status": "blocked",
                        "reason": str(exc),
                        "error_type": type(exc).__name__,
                    }
        output.update(evaluate(recipe, results))
        output["results"] = results
        output["status"] = (
            "checks_passed" if output["ready_for_calendar_incorporation"] else "blocked_global_policy"
        )

    if check:
        replay()
        ignore = {"mode", "finished_at"}
        if {k: v for k, v in output.items() if k not in ignore} != {
            k: v for k, v in prior.items() if k not in ignore
        }:
            raise ValueError("Global source replay differs from immutable receipt")
        return {**output, "receipt_sha256": readiness.sha(accepted)}
    with writer(workspace):
        if any(p.name != ".source-update.lock" for p in workspace.iterdir()):
            raise ValueError("Global workspace changed before writer lock")
        replay()
        output["finished_at"] = datetime.now(UTC).isoformat()
        accepted.write_text(json.dumps(output, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
    return output


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    for option in ("execute", "check", "dry-run"):
        mode.add_argument("--" + option, action="store_true")
    args = parser.parse_args(argv)
    try:
        result = execute(
            json.loads(args.recipe.read_text()), args.workspace, write=args.execute, check=args.check
        )
    except (ValueError, OSError, KeyError, TypeError) as exc:
        result = {"status": "blocked", "reason": str(exc), "activation": "none"}
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return int(result["status"].startswith("blocked"))


if __name__ == "__main__":
    raise SystemExit(main())
