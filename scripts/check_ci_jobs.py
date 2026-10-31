"""Keep the required test/web checks closed unless every component succeeded."""

from __future__ import annotations

import argparse
import json
import os


COMMON = {"change-plan", "pages-preflight", "docker-preflight", "static", "chat-runtime"}
GATES = {"test": COMMON | {"public-tests"}, "web": COMMON | {"web-checks"}}


def check(gate: str, results: object) -> list[str]:
    required = GATES[gate]
    if not isinstance(results, dict):
        return ["Job results must be an object"]
    errors = []
    if set(results) != required:
        errors.append(f"Unexpected dependency set: missing={sorted(required - set(results))}, "
                      f"extra={sorted(set(results) - required)}")
    for name in sorted(required):
        result = results.get(name)
        if not isinstance(result, dict) or result.get("result") != "success":
            conclusion = result.get("result") if isinstance(result, dict) else "invalid job result"
            errors.append(f"{name}: required success, got {conclusion!r}")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gate", choices=sorted(GATES))
    args = parser.parse_args(argv)
    try:
        errors = check(args.gate, json.loads(os.environ["CI_REQUIRED_RESULTS"]))
    except (ValueError, KeyError) as exc:
        parser.exit(1, f"Invalid CI results: {exc}\n")
    if errors:
        parser.exit(1, "CI gate failed: " + "; ".join(errors) + "\n")
    print(f"{args.gate}: every required component succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
