"""Materialize only pinned issuer evidence for a historical approval replay."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path, PurePosixPath


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _relative(value, *, workspace=False):
    if not isinstance(value, str):
        raise ValueError("Issuer replay path must be explicit")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(p in {".", ".."} for p in value.split("/")):
        raise ValueError("Issuer replay path escapes its private workspace")
    if workspace and (path.parts[:2] != ("tmp", "source-updates") or len(path.parts) < 3):
        raise ValueError("Issuer replay only materializes isolated source-update evidence")
    return Path(*path.parts)


def _plain(path):
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("Issuer replay evidence cannot traverse symlinks")


def _inventory(folder):
    _plain(folder)
    if not folder.is_dir() or (folder / ".source-update.lock").exists():
        raise ValueError("Issuer source evidence is absent or has an active writer")
    result = {}
    for path in sorted(folder.rglob("*")):
        _plain(path)
        if path.is_file():
            raw = path.read_bytes()
            _plain(path)
            result[path.relative_to(folder)] = (_sha(raw), len(raw))
        elif not path.is_dir():
            raise ValueError("Issuer replay requires ordinary files and directories")
    return result


def materialize_issuer_inputs(record_paths, repo: Path, destination: Path):
    """Copy immutable evidence; the pinned verifier still reproduces every input.

    The ordinary analysis/data links remain unchanged. Issuer workspaces cannot
    be symlinked because their dedicated verifier requires physical isolation.
    No source collection, approval, timestamp renewal or code execution occurs.
    """
    repo, destination = Path(repo).resolve(), Path(destination).resolve()
    materialized = []
    for record_path in record_paths:
        record = json.loads(Path(record_path).read_bytes())
        draft = record["draft"]
        if draft.get("source_profile") != "issuer_quarter_v1":
            continue
        package_id = draft.get("package_id", "")
        if not re.fullmatch(r"(?:VIVA_AEROBUS|VOLARIS)_\d{4}Q[1-4]_[a-f0-9]{64}", package_id):
            raise ValueError("Invalid issuer replay package identity")
        package_path = repo / "analysis_runs/evidence" / (package_id + ".json")
        # analysis_runs may be the intentional read-only link in a verifier.
        package = json.loads(package_path.read_bytes())
        if any(draft.get(k) != package.get(k) for k in ("package_id", "entity_key", "period_id")):
            raise ValueError("Issuer replay package differs from the selected record")
        relative = _relative(package["workspace"], workspace=True)
        source, target = repo / relative, destination / relative
        inventory = _inventory(source)
        binding = package["source_binding"]
        for name, expected in binding["output_sha256"].items():
            item = Path("data") / _relative(name + ".parquet")
            if inventory.get(item, (None,))[0] != expected:
                raise ValueError("Issuer replay output differs from its approved binding")
        retention = package["retention_id"]
        if not re.fullmatch(r"[a-f0-9]{32}", retention):
            raise ValueError("Invalid issuer retention identity")
        receipt = Path("receipts") / f"retained-{retention}.json"
        if inventory.get(receipt, (None,))[0] != package["retention_receipt_sha256"]:
            raise ValueError("Issuer retention receipt changed")
        for original in package["sources"]:
            name = Path("data/bronze") / _relative(original["source_file"])
            if inventory.get(name, (None,))[0] != original["artifact_sha256"] or Path(
                str(name) + ".meta.json"
            ) not in inventory:
                raise ValueError("Issuer original or capture metadata is missing or changed")
        _plain(target)
        if target.exists():
            if _inventory(target) != inventory:
                raise ValueError("Preserve conflicting issuer evidence in the replay destination")
        else:
            target.mkdir(parents=True, exist_ok=False)
            for name, expected in inventory.items():
                original, copied = source / name, target / name
                descriptor = os.open(original, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                with os.fdopen(descriptor, "rb") as stream:
                    raw = stream.read()
                if (_sha(raw), len(raw)) != expected:
                    raise ValueError("Issuer source changed before its isolated copy")
                copied.parent.mkdir(parents=True, exist_ok=True)
                with copied.open("xb") as stream:
                    stream.write(raw)
                shutil.copystat(original, copied, follow_symlinks=False)
        if _inventory(target) != inventory or _inventory(source) != inventory:
            raise ValueError("Issuer evidence changed while materializing the pinned replay")
        materialized.append({"workspace": relative.as_posix(), "files": len(inventory)})
    return materialized
