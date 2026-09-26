"""Cheap consistency check for `justfile`: every test file path it invokes
must exist. This catches the class of drift audited under A12 (a recipe
left pointing at a test module removed or renamed by a later change)
without running the recipes themselves.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.config import PATHS

JUSTFILE = PATHS.root / "justfile"
TEST_PATH_RE = re.compile(r"tests/[A-Za-z0-9_./]+\.py")


def _referenced_test_paths() -> set[str]:
    text = JUSTFILE.read_text(encoding="utf-8")
    return set(TEST_PATH_RE.findall(text))


def test_justfile_exists() -> None:
    assert JUSTFILE.is_file()


def test_every_test_path_in_justfile_exists() -> None:
    paths = _referenced_test_paths()
    assert paths, "expected at least one tests/*.py reference in justfile"
    missing = sorted(p for p in paths if not (PATHS.root / p).is_file())
    assert not missing, f"justfile references test files that do not exist: {missing}"
