"""Select the declared publication verifier; execute the chosen checkout's code."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

VERIFIERS = (
    ("aerocivil-movements-publication.json", "src.publish.movements_scope"),
    ("issuer-publication.json", "src.publish.issuer_scope"),
    ("financial-publication.json", "src.publish.financial_scope"),
    ("editorial-publication.json", "src.publish.editorial"),
)


def verifier_for(site: Path) -> str:
    manifest = json.loads((site / "publication_manifest.json").read_text(encoding="utf-8"))
    files = manifest["files"]
    if not isinstance(files, list) or any(not isinstance(item, dict) for item in files):
        raise ValueError("publication manifest files must be a list of objects")
    names = [item["path"] for item in files]
    if any(not isinstance(name, str) for name in names) or len(names) != len(set(names)):
        raise ValueError("publication manifest paths must be unique strings")
    for receipt, _ in VERIFIERS:
        if receipt in names and not (site / receipt).is_file():
            raise ValueError(f"declared publication receipt is missing: {receipt}")
    return next((module for receipt, module in VERIFIERS if receipt in names), "src.publish.verify")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    args = parser.parse_args(argv)
    try:
        module = verifier_for(args.site)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"publication verification selection failed: {exc}\n")
    # In preview this script is master's helper, but cwd and the interpreter
    # belong to the pinned checkout. Never import master's publication modules.
    return subprocess.run([sys.executable, "-m", module, str(args.site)], cwd=Path.cwd()).returncode


if __name__ == "__main__":
    raise SystemExit(main())
