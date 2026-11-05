"""Copy a pinned retained selection to a fresh review workspace; default is a dry run."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from src.config import PATHS
from src.source_updates.official_routes import prepare
from src.source_updates.official_routes_sources import physical


def stage(inputs: Path, out: Path, *, execute=False, retained_approvals=None):
    source, out = inputs.resolve(), out.resolve()
    out.relative_to((PATHS.root / "tmp").resolve())
    if out.exists():
        raise ValueError("Use a fresh candidate directory; preserve prior preparations")
    selection = json.loads(source.read_bytes())
    refs = [selection[k] for k in ("cities", "airports", "geonames")]
    refs += [item[k] for item in selection["afac"] for k in ("routes", "carriers")]
    refs += [item["archive"] for item in selection["bts"]]
    paths = {physical(ref, source.parent) for ref in refs}
    paths |= {path.with_suffix(path.suffix + ".meta.json") for path in paths
              if path.with_suffix(path.suffix + ".meta.json").is_file()}
    result = dict(status="official_routes_stage_dry_run", files=len(paths) + 1, network_requests=0,
                  paid_requests=0, destination=str(out), activation="none", publication="not_authorized")
    if execute:
        for path in sorted(paths):
            target = out / path.relative_to(source.parent)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
        target = out / "selection.json"
        target.write_bytes(source.read_bytes())
        result = prepare(target, execute=True, retained_approvals=retained_approvals)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--retained-approvals", type=Path)
    args = parser.parse_args()
    approvals = json.loads(args.retained_approvals.read_bytes()) if args.retained_approvals else None
    print(json.dumps(stage(args.inputs, args.out, execute=args.execute, retained_approvals=approvals),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
