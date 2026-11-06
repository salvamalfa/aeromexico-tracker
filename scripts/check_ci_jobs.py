"""Keep the required test/web checks closed unless every component succeeded."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


COMMON = {"change-plan", "pages-preflight", "docker-preflight", "static", "chat-runtime"}
GATES = {"test": COMMON | {"public-tests"}, "web": COMMON | {"web-checks"}}
WAIVED = {
    "full": set(),
    "docs_only": {"docker-preflight", "chat-runtime", "public-tests", "web-checks"},
    "web_only": {"docker-preflight", "chat-runtime", "public-tests"},
}


def check(gate: str, results: object, *, execution: str = "full") -> list[str]:
    required = GATES[gate]
    if execution not in WAIVED:
        return ["Unknown execution profile"]
    if not isinstance(results, dict):
        return ["Job results must be an object"]
    errors = []
    if set(results) != required:
        errors.append(f"Unexpected dependency set: missing={sorted(required - set(results))}, "
                      f"extra={sorted(set(results) - required)}")
    for name in sorted(required):
        result = results.get(name)
        expected = "skipped" if name in WAIVED[execution] else "success"
        if not isinstance(result, dict) or result.get("result") != expected:
            conclusion = result.get("result") if isinstance(result, dict) else "invalid job result"
            errors.append(f"{name}: required {expected}, got {conclusion!r}")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", choices=sorted(GATES))
    args = parser.parse_args(argv)
    try:
        if __package__:
            from .ci_change_plan import build_plan
        else:
            from ci_change_plan import build_plan

        # Recompute from this job's exact checkout. Neither an artifact nor a
        # selector output alone is permission to omit a required component.
        force_full = os.environ.get("CI_PLAN_FORCE_FULL", "false")
        if force_full not in {"true", "false"}:
            raise ValueError("Invalid force-full setting")
        plan = build_plan(
            Path.cwd(), os.environ.get("CI_PLAN_BASE", ""), os.environ.get("CI_PLAN_HEAD", ""),
            event=os.environ.get("CI_PLAN_EVENT", ""), enable_selection=force_full == "false",
        )
        results = json.loads(os.environ["CI_REQUIRED_RESULTS"])
        execution = plan["actual_execution"]
        errors = check(args.gate, results, execution=execution)
        selector = results.get("change-plan") if isinstance(results, dict) else None
        outputs = selector.get("outputs") if isinstance(selector, dict) else None
        reported = outputs.get("execution") if isinstance(outputs, dict) else None
        if reported != execution:
            errors.append("Selector execution disagrees with the independently recomputed checkout plan")
    except (ValueError, KeyError) as exc:
        parser.exit(1, f"Invalid CI results: {exc}\n")
    if errors:
        parser.exit(1, "CI gate failed: " + "; ".join(errors) + "\n")
    print(f"{args.gate}: {execution}; every selected component succeeded and all omissions were verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
