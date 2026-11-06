"""Use the released eight-analysis continuity API, with its unchanged original replay."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from src.publish.afac_history_parent import ledger_inventory, parent_inventory


def retained_files(profile, repo):
    value = profile.get("retained_approvals")
    if not isinstance(value, dict) or set(value) != {"baseline_commit", "parent_inputs"}:
        raise ValueError("Official-map exposure requires its closed retained approval dossier")
    inputs = value["parent_inputs"]
    root, _, inventory = parent_inventory(repo, inputs)
    ledger = Path(repo) / "analysis_runs/lifecycle"
    files = [Path(repo) / inputs["inventory"]["path"], *[root / name for name in inventory]]
    files.extend(ledger / name for name in ledger_inventory(ledger))
    return files


def record_paths(profile, baseline, repo):
    root, _, _ = parent_inventory(repo, profile["retained_approvals"]["parent_inputs"])
    paths = []
    for entry in baseline["analysis_manifest"]:
        path = root / "analysis_runs/drafts"
        if "entity_key" in entry:
            path /= entry["entity_key"]
        paths.append(path / entry["period_id"] / (entry["version"] + ".json"))
    if any(not p.is_file() or p.is_symlink() for p in paths):
        raise ValueError("Exact retained baseline record is missing")
    return paths


def verify(records, repo, baseline_commit, baseline, ledger_root, profile):
    from src.publish.afac_history_scope import replay_retained_approvals

    retained_files(profile, repo)
    original = profile["retained_approvals"]["baseline_commit"]
    subprocess.run(["git", "merge-base", "--is-ancestor", original, baseline_commit],
                   cwd=repo, check=True, capture_output=True)
    frozen = json.loads(subprocess.check_output(
        ["git", "show", f"{original}:site/publication_manifest.json"], cwd=repo,
    ))
    if frozen["analysis_manifest"] != baseline["analysis_manifest"]:
        raise ValueError("Retained approval identities differ from the actually served baseline")
    if {Path(p).resolve() for p in records} != {p.resolve() for p in record_paths(profile, baseline, repo)}:
        raise ValueError("Official map requires every exact retained baseline record")
    site = Path(repo) / "site"
    if json.loads((site / "publication_manifest.json").read_bytes()) != baseline:
        raise ValueError("Retained approval replay is not bound to the actually selected baseline")
    # This API validates parent inventory/request hashes against the committed
    # AFAC history scope, copies the original producer and current real ledger,
    # and replays all eight analyses, sixteen outputs and four retained Q2 cases.
    return replay_retained_approvals(repo, site, profile["retained_approvals"]["parent_inputs"], ledger_root)
