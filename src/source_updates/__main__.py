"""Run with python -m src.source_updates. Defaults never acquire or mutate data."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from src.source_updates import calendar
from src.source_updates.build import build
from src.source_updates.catalog import FAMILIES, ROOT, plan
from src.source_updates.checks import check_candidate
from src.source_updates.collection import collect
from src.source_updates.recipes import catalog_selection, describe, macro_round


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    planned = commands.add_parser("plan")
    planned.add_argument("--round", choices=["monthly", "quarterly", "combined"], required=True)
    planned.add_argument("--as-of", required=True)
    planned.add_argument("--quarter")
    planned.add_argument("--family", choices=list(FAMILIES))
    recipes = commands.add_parser("recipe")
    recipes.add_argument("--product", required=True)
    recipes.add_argument("--output", choices=["instructions", "selection", "round"], default="instructions")
    recipes.add_argument("--period")
    recipes.add_argument("--as-of")
    recipes.add_argument("--catalog-file", type=Path)
    recipes.add_argument("--ticker", action="append", choices=["AERO", "VOLAR"])
    dates = commands.add_parser("calendar")
    dates.add_argument("--start", required=True, help="YYYY-MM")
    dates.add_argument("--months", type=int, default=3)
    dates.add_argument("--quarter")
    dates.add_argument("--releases", type=Path)
    dates.add_argument("--as-of", required=True)
    dates.add_argument("--holidays", type=Path, default=ROOT / "config/source_update_holidays.json")
    retry = commands.add_parser("retry")
    retry.add_argument("--today", required=True)
    retry.add_argument("--reschedules", type=int, required=True)
    retry.add_argument("--reason", choices=["announced", "technical", "unknown"], required=True)
    retry.add_argument("--announced-date")
    retry.add_argument("--holidays", type=Path, default=ROOT / "config/source_update_holidays.json")
    for name in ("collect", "build", "round"):
        command = commands.add_parser(name)
        command.add_argument("--workspace", type=Path, required=True)
        mode = command.add_mutually_exclusive_group()
        mode.add_argument("--execute", action="store_true")
        mode.add_argument("--dry-run", action="store_true")
        if name == "build":
            command.add_argument("--steps", required=True)
        else:
            command.add_argument("--selection" if name == "collect" else "--recipe", type=Path, required=True)
    checks = commands.add_parser("check")
    checks.add_argument("--workspace", type=Path, required=True)
    checks.add_argument("--specification", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "plan":
            result = plan(args.round, args.as_of, args.quarter, args.family)
        elif args.command == "recipe":
            if args.output == "selection":
                if args.catalog_file:
                    from src.source_updates.discovery import select_documents

                    if not args.period:
                        raise ValueError("Catalogue-file selection requires --period")
                    result = select_documents(args.product, args.catalog_file, args.period, args.ticker)
                else:
                    result = catalog_selection(args.product)
            elif args.output == "round":
                if not args.period or not args.as_of:
                    raise ValueError("A runnable recipe requires --period and --as-of")
                result = macro_round(args.product, args.period, args.as_of)
            else:
                result = describe(args.product)
        elif args.command == "calendar":
            cutoff = calendar.local_time(args.as_of)
            if not 1 <= args.months <= 12:
                raise ValueError("Calendar needs 1..12 months")
            start = date.fromisoformat(args.start + "-01")
            holidays = read_json(args.holidays)
            rounds = []
            for offset in range(args.months):
                index = start.year * 12 + start.month - 1 + offset
                rounds.append(
                    {
                        "kind": "monthly",
                        "date": calendar.monthly(index // 12, index % 12 + 1, holidays).isoformat(),
                    }
                )
            if args.quarter:
                releases = read_json(args.releases)["releases"] if args.releases else []
                rounds.append(
                    {"kind": "quarterly", **calendar.quarterly(args.quarter, releases, args.as_of, holidays)}
                )
            result = {
                "mode": "dry_run",
                "as_of": cutoff.isoformat(),
                "timezone": "America/Mexico_City",
                "rounds": calendar.combine(rounds),
                "scheduled_executions": 0,
                "holiday_years_verified": sorted(holidays["years"]),
            }
        elif args.command == "retry":
            result = calendar.retry_date(
                today=date.fromisoformat(args.today),
                attempts=args.reschedules,
                reason=args.reason,
                holidays=read_json(args.holidays),
                announced_date=date.fromisoformat(args.announced_date) if args.announced_date else None,
            )
        elif args.command == "collect":
            result = collect(read_json(args.selection), args.workspace, execute=args.execute)
        elif args.command == "build":
            result = build(args.workspace, args.steps.split(","), execute=args.execute)
        elif args.command == "check":
            result = check_candidate(args.workspace, read_json(args.specification))
        else:
            recipe = read_json(args.recipe)
            collected = collect(recipe["selection"], args.workspace, execute=args.execute)
            result = {
                "mode": "round" if args.execute else "dry_run",
                "collection": collected,
                "activation": "none",
                "publication": "not_authorized",
            }
            if args.execute and collected["status"] != "collected_unvalidated":
                result["status"] = "blocked_collection"
            else:
                built = build(args.workspace, recipe["steps"], execute=args.execute)
                result["build"] = built
                if args.execute:
                    if built.get("status") != "completed":
                        result["status"] = "blocked_build"
                    else:
                        result["checks"] = check_candidate(args.workspace, recipe["checks"])
                        result["status"] = result["checks"]["status"]
                else:
                    result["period_checks"] = recipe["checks"]
                    result["status"] = "planned_not_executed"
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        status = result.get("status", "")
        return 1 if status.startswith(("blocked", "failed")) or status == "incomplete" else 0
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "activation": "none"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
