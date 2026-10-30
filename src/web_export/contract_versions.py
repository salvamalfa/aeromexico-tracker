"""Resolve a manifest's exact contract bytes, never the nearest schema version.

Retained flights, market, airport demand and analysis citation contracts are versioned.
Privacy and approval contracts
still require the current file's exact hash; an archive is not an approval.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ARCHIVED_CONTRACTS = {
    "market.schema.json": frozenset({"3ac4a80fbeadea2b6c4eea6ee6d906acf24b1cf1202b295bde0b86b32b2d0008"}),
    "market_demand.schema.json": frozenset(
        {"420bdc05ef4035fe2f99a5e6e5fce3b0d4d5129abdfefa298a78a1c620dc95bf"}
    ),
    "analysis.schema.json": frozenset({"c0e3b0fb5e3f840087bbb3bed0e222e477f90f5dc9ab9840802916f1ed5eb8c2"}),
    "flights.schema.json": frozenset(
        {
            "3eb5e9425dd346a38088ddef500ff0ff5f71d62dad6559bba7b486135f8ccc58",
            "17fb7e131da94435190bea925fe9733e298754d04e9b9c5e76fbbea8bef119a7",
            "15768d277f9cb31d361d2b976602e4b65e7ed20d6419a38699557b0c13aafef6",
        }
    ),
}


def resolve_contract(contracts_dir: Path, name: str, expected_sha256: str) -> Path:
    """Return only an in-tree, non-symlink contract matching the requested hash."""

    if not re.fullmatch(r"[a-z][a-z0-9_.]*\.(?:json|yaml)", name):
        raise ValueError(f"Unsafe contract name: {name!r}")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError(f"Invalid contract SHA-256: {name}")
    root = Path(contracts_dir).resolve()

    def matches(path: Path) -> bool:
        if any(part.is_symlink() for part in (path, *path.parents) if part != root and root in part.parents):
            raise ValueError(f"Symlink contract path: {name}")
        if root not in path.resolve().parents:
            raise ValueError(f"Contract path outside contracts/web: {name}")
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256

    current = root / name
    if matches(current):
        return current
    if expected_sha256 in ARCHIVED_CONTRACTS.get(name, ()):
        archived = root / "versions" / expected_sha256 / name
        if matches(archived):
            return archived
    raise ValueError(f"Contract hash mismatch or exact version unavailable: {name}")
