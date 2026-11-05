"""Rebuild an inspectable native AFAC candidate without publishing or approving."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.config import PATHS
from src.publish.afac_history_projection import GRANULAR_PATHS, TARGETS, encoded, replay, sha


def build(profile_path, parent, out):
    profile_path, parent, out = map(Path, (profile_path, parent, out))
    out.resolve().relative_to((PATHS.root / "tmp/source-updates").resolve())
    result = replay(json.loads(profile_path.read_bytes()), parent)
    out.mkdir(parents=True, exist_ok=False)
    for name, raw in result["outputs"].items():
        target = out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    proof = {
        "schema_version": "afac_history_candidate_review_v1",
        "status": "candidate_reproduced_not_authorized_not_published",
        "source_profile_sha256": sha(profile_path.read_bytes()),
        "source_binding": result["source_binding"],
        "granular_paths": GRANULAR_PATHS,
        "parent_data": [{"path": name, "sha256": sha((parent / name).read_bytes())} for name in TARGETS],
        "data_files": [
            {"path": name, "sha256": sha(raw), "bytes": len(raw)}
            for name, raw in sorted(result["outputs"].items())
        ],
        "input_files": [
            {
                "path": str(Path(path).relative_to(PATHS.root)),
                "sha256": sha(Path(path).read_bytes()),
                "bytes": Path(path).stat().st_size,
            }
            for path in result["input_files"]
        ],
        "authorization": None,
        "ledger_events_written": 0,
        "provider_calls": 0,
    }
    (out / "projection.json").write_bytes(encoded(result["projection"]))
    (out / "review-proof.json").write_bytes(encoded(proof))
    return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--parent", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    proof = build(args.profile, args.parent, args.out)
    print(json.dumps({key: proof[key] for key in ("status", "data_files", "authorization")}, indent=2))


if __name__ == "__main__":
    main()
