"""Partition every default-named Python test module into fixed public CI jobs.

Emit NUL-delimited repository-relative paths for a shell array; never emit shell
code. Test markers and all pytest arguments remain the workflow's responsibility.
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import hashlib
import os
import stat
import sys
import tomllib
from pathlib import Path

PARTITIONS = ("core-a", "core-b", "publication")
PUBLICATION_FILES = frozenset({
    "tests/test_financial_site_parity.py",
    "tests/test_editorial_site_parity.py",
})
FILE_COLLECTION_HOOKS = {
    "pytest_ignore_collect", "pytest_collect_directory", "pytest_collect_file",
    "pytest_pycollect_makemodule", "pytest_collection",
}
IGNORE_VARIABLES = {"collect_ignore", "collect_ignore_glob"}


class PartitionError(ValueError):
    """An uncertain inventory must fail instead of dropping a test module."""


def _validate_pytest_policy(repo: Path) -> None:
    # Explicit file arguments bypass pytest's discovery filters. Require this
    # helper to be reviewed when the repository changes its collection policy.
    for name in ("pytest.ini", ".pytest.ini", "pytest.toml", ".pytest.toml", "tox.ini", "setup.cfg"):
        if (repo / name).exists():
            raise PartitionError("alternate pytest configuration requires partition review")
    config = repo / "pyproject.toml"
    if not stat.S_ISREG(config.lstat().st_mode):
        raise PartitionError("pyproject.toml must be a regular file")
    options = tomllib.loads(config.read_text(encoding="utf-8")).get("tool", {}).get("pytest", {}).get("ini_options", {})
    if options.get("testpaths") != ["tests"]:
        raise PartitionError("pytest testpaths must remain exactly ['tests']")
    if options.get("python_files", ["test_*.py", "*_test.py"]) != ["test_*.py", "*_test.py"]:
        raise PartitionError("pytest python_files must retain the default patterns")
    if {"norecursedirs", *IGNORE_VARIABLES}.intersection(options):
        raise PartitionError("custom pytest ignore rules require partition review")


def _validate_conftest(path: Path) -> None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        raise PartitionError("cannot validate conftest collection policy") from exc
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in FILE_COLLECTION_HOOKS:
            raise PartitionError("custom pytest file collection hooks require partition review")
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store) and node.id in IGNORE_VARIABLES:
            raise PartitionError("conftest ignore rules require partition review")
        if isinstance(node, (ast.Import, ast.ImportFrom)) and any(
            (alias.asname or alias.name) in FILE_COLLECTION_HOOKS | IGNORE_VARIABLES for alias in node.names
        ):
            raise PartitionError("imported pytest collection policy requires partition review")
        if isinstance(node, ast.keyword) and node.arg == "specname" and isinstance(node.value, ast.Constant):
            if node.value.value in FILE_COLLECTION_HOOKS:
                raise PartitionError("custom pytest file collection hooks require partition review")


def discover_test_files(repo: Path) -> list[str]:
    """Enumerate both pytest default filename patterns, including nested files."""
    root = repo / "tests"
    if not stat.S_ISDIR(root.lstat().st_mode):
        raise PartitionError("tests must be a regular directory")
    files = []
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                mode = entry.stat(follow_symlinks=False).st_mode
                if stat.S_ISLNK(mode):
                    raise PartitionError("symlinks are not allowed under tests")
                if stat.S_ISDIR(mode):
                    pending.append(Path(entry.path))
                elif not stat.S_ISREG(mode):
                    raise PartitionError("special files are not allowed under tests")
                elif entry.name == "conftest.py":
                    _validate_conftest(Path(entry.path))
                elif any(fnmatch.fnmatchcase(entry.name, pattern) for pattern in ("test_*.py", "*_test.py")):
                    if mode & 0o111:
                        raise PartitionError("test modules must not be executable")
                    relative = Path(entry.path).relative_to(repo).as_posix()
                    # Pytest interprets :: as a node selector even inside an
                    # explicit filename. Fail rather than pass an ambiguous path.
                    if "::" in relative:
                        raise PartitionError("test path contains a pytest node separator")
                    relative.encode("utf-8")
                    files.append(relative)
    return sorted(files)


def partition_test_files(repo: Path) -> dict[str, list[str]]:
    _validate_pytest_policy(repo)
    files = discover_test_files(repo)
    if not PUBLICATION_FILES.issubset(files):
        raise PartitionError("the two required publication test modules must exist")
    partitions = {name: [] for name in PARTITIONS}
    for name in files:
        if name in PUBLICATION_FILES:
            partition = "publication"
        else:
            parity = int.from_bytes(hashlib.sha256(name.encode("utf-8")).digest(), "big") % 2
            partition = ("core-a", "core-b")[parity]
        partitions[partition].append(name)
    if any(not names for names in partitions.values()):
        raise PartitionError("every public test partition must contain a test module")
    return partitions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--partition", required=True, choices=PARTITIONS)
    arguments = parser.parse_args(argv)
    try:
        selected = partition_test_files(arguments.repo)[arguments.partition]
        payload = b"".join(name.encode("utf-8") + b"\0" for name in selected)
        sys.stdout.buffer.write(payload)
        sys.stdout.buffer.flush()
    except (PartitionError, OSError, UnicodeError) as exc:
        print(f"cannot partition public tests: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
