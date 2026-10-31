"""Select the declared publication verifier; execute the chosen checkout's code."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

VERIFIERS = (
    ("aerocivil-movements-publication.json", "src.publish.movements_scope"),
    ("source-data-publication.json", "src.publish.source_data_scope"),
    ("issuer-publication.json", "src.publish.issuer_scope"),
    ("financial-publication.json", "src.publish.financial_scope"),
    ("editorial-publication.json", "src.publish.editorial"),
)


def verifier_for(site: Path, repo: Path | None = None) -> str:
    manifest = json.loads((site / "publication_manifest.json").read_text(encoding="utf-8"))
    files = manifest.get("files")
    if not isinstance(files, list) or any(not isinstance(item, dict) for item in files):
        raise ValueError("publication manifest files must be a list of objects")
    names = [item["path"] for item in files]
    if any(not isinstance(name, str) for name in names) or len(names) != len(set(names)):
        raise ValueError("publication manifest paths must be unique strings")
    for receipt, _ in VERIFIERS:
        if receipt in names and not (site / receipt).is_file():
            raise ValueError(f"declared publication receipt is missing: {receipt}")
    known = {receipt for receipt, _ in VERIFIERS}
    if any(
        ((site / receipt).exists() or (site / receipt).is_symlink()) and receipt not in names
        for receipt in known
    ):
        raise ValueError("Undeclared publication receipt is present; cannot select a looser verifier")
    if any(re.fullmatch(r"[^/]+-publication\.json", name) and name not in known for name in names):
        raise ValueError("Unknown declared publication proof; add its explicit strong verifier")
    selected = [(receipt, module) for receipt, module in VERIFIERS if receipt in names]
    if not selected:
        return "src.publish.verify"
    # Retained proofs describe prior publications. Choose the unique latest
    # witnessed Git baseline, then let its strong verifier validate all claims.
    # Ties, missing history and unrelated branches are decisions, never fallback.
    repo = Path.cwd() if repo is None else Path(repo)
    commits = {}
    for receipt, module in selected:
        if (site / receipt).is_symlink():
            raise ValueError("Publication selection proof cannot be a symlink")
        raw = (site / receipt).read_bytes()
        pin = next(item for item in files if item["path"] == receipt)
        if (
            pin.get("sha256") != hashlib.sha256(raw).hexdigest()
            or type(pin.get("bytes")) is not int
            or pin["bytes"] != len(raw)
        ):
            raise ValueError("Publication selection proof differs from manifest pins")
        commit = json.loads(raw).get("remote_witness", {}).get("baseline_commit")
        if not isinstance(commit, str) or not re.fullmatch("[a-f0-9]{40}", commit):
            raise ValueError("Publication selection requires exact witnessed Git baselines")
        if subprocess.run(
            ["git", "cat-file", "-e", commit + "^{commit}"], cwd=repo, capture_output=True
        ).returncode:
            raise ValueError("Publication selection is missing witnessed Git history")
        commits[module] = commit
    candidates = [
        module
        for module, commit in commits.items()
        if all(
            other != commit
            and subprocess.run(
                ["git", "merge-base", "--is-ancestor", other, commit], cwd=repo, capture_output=True
            ).returncode
            == 0
            for peer, other in commits.items()
            if peer != module
        )
    ]
    if len(candidates) != 1:
        raise ValueError("Publication proofs have ambiguous or unrelated baseline precedence")
    return candidates[0]


def verify_site(site, repo):
    """Run the selected strong verifier in this checkout; never downgrade a failure."""
    from importlib import import_module

    module = verifier_for(site, repo)
    name = {
        "src.publish.source_data_scope": "verify_source_data",
        "src.publish.issuer_scope": "verify_issuer",
        "src.publish.movements_scope": "verify_movements",
        "src.publish.financial_scope": "verify_financial",
        "src.publish.editorial": "verify_editorial",
        "src.publish.verify": "verify_site",
    }[module]
    return getattr(import_module(module), name)(site)


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
