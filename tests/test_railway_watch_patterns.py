"""Every file the chat image copies must trigger a Railway redeploy."""

from __future__ import annotations

import fnmatch
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _patterns() -> list[str]:
    return tomllib.loads((ROOT / "railway.toml").read_text(encoding="utf-8"))["build"]["watchPatterns"]


def _copied_files() -> set[str]:
    files: set[str] = set()
    for line in (ROOT / "Dockerfile.chat").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts or parts[0] != "COPY" or any(p.startswith("--from") for p in parts):
            continue
        for source in parts[1:-1]:
            matches = [ROOT / source] if not any(c in source for c in "*?[") else list(ROOT.glob(source))
            assert matches, f"COPY source {source} matches no file"
            for match in matches:
                found = match.rglob("*") if match.is_dir() else [match]
                files.update(p.relative_to(ROOT).as_posix() for p in found if p.is_file())
    return files


def _watched(path: str, patterns: list[str]) -> bool:
    return any(
        path.startswith(pattern[:-2]) if pattern.endswith("/**") else fnmatch.fnmatchcase(path, pattern)
        for pattern in patterns
    )


def test_every_copied_file_is_watched():
    patterns = _patterns()
    copied = _copied_files() | {"Dockerfile.chat"}
    unwatched = sorted(path for path in copied if not _watched(path, patterns))
    assert not unwatched, f"add watch patterns in railway.toml for: {unwatched}"


def test_docs_and_web_changes_do_not_redeploy_the_chat():
    patterns = _patterns()
    for path in ("README.md", "docs/chat/README.md", "web/src/main.ts", "AGENTS.md", "tests/test_x.py"):
        assert not _watched(path, patterns), path
