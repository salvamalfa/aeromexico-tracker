"""Verify full deterministic test-file coverage without collecting each shard."""

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import ci_public_test_files as partitioner


def write(repo, name):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("def test_example(): pass\n", encoding="utf-8")
    return path


@pytest.fixture
def repository(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]\n')
    for name in partitioner.PUBLICATION_FILES:
        write(tmp_path, name)
    # These modules populate both independently hashed core partitions.
    for name in ("tests/test_a.py", "tests/test_b.py", "tests/nested/item_test.py"):
        write(tmp_path, name)
    return tmp_path


def run_cli(repo, partition):
    return subprocess.run(
        [sys.executable, partitioner.__file__, "--repo", str(repo), "--partition", partition],
        capture_output=True,
    )


def test_partitions_are_complete_disjoint_sorted_and_deterministic(repository):
    expected = {
        "tests/test_financial_site_parity.py", "tests/test_editorial_site_parity.py",
        "tests/test_a.py", "tests/test_b.py", "tests/nested/item_test.py",
    }
    partitions = partitioner.partition_test_files(repository)
    flattened = [name for names in partitions.values() for name in names]
    assert set(flattened) == expected
    assert len(flattened) == len(expected)
    assert partitions["publication"] == sorted(partitioner.PUBLICATION_FILES)
    for partition in ("core-a", "core-b"):
        assert partitions[partition]
        assert partitions[partition] == sorted(partitions[partition])
        for name in partitions[partition]:
            expected_partition = ("core-a", "core-b")[int(hashlib.sha256(name.encode()).hexdigest(), 16) % 2]
            assert partition == expected_partition
    assert partitions == partitioner.partition_test_files(repository)


@pytest.mark.parametrize("name", [
    "tests/deeply/nested/test_new.py", "tests/nested/new_test.py", "tests/test_both_test.py",
    "tests/test_ spaces;$[]'().py", "tests/nested/test_line\nbreak.py", "tests/test_ñ.py",
])
def test_new_modules_and_special_characters_are_preserved_once(repository, name):
    before = partitioner.partition_test_files(repository)
    write(repository, name)
    after = partitioner.partition_test_files(repository)
    flattened = [item for names in after.values() for item in names]
    assert flattened.count(name) == 1
    for partition, names in before.items():
        assert set(names) <= set(after[partition])
    combined = []
    for partition in partitioner.PARTITIONS:
        completed = run_cli(repository, partition)
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.endswith(b"\0")
        combined.extend(completed.stdout.decode("utf-8").split("\0")[:-1])
    assert sorted(combined) == sorted(flattened)


def test_only_pytest_default_filename_patterns_are_partitioned(repository):
    for name in ("tests/conftest.py", "tests/test_helpers.txt", "tests/example.py", "tests/test_x.pyc", "outside/test_x.py"):
        write(repository, name)
    assert len(partitioner.discover_test_files(repository)) == 5


def test_similarly_named_nested_publication_module_is_a_core_module(repository):
    name = "tests/nested/test_financial_site_parity.py"
    write(repository, name)
    partitions = partitioner.partition_test_files(repository)
    assert partitions["publication"] == sorted(partitioner.PUBLICATION_FILES)
    assert name in partitions["core-a"] + partitions["core-b"]


@pytest.mark.parametrize("kind", ["symlink_file", "symlink_directory", "executable", "fifo", "node_separator"])
def test_unsafe_inventory_fails_before_any_output(repository, kind):
    path = repository / "tests/test_unsafe.py"
    if kind == "symlink_file":
        path.symlink_to("test_a.py")
    elif kind == "symlink_directory":
        path.symlink_to("nested", target_is_directory=True)
    elif kind == "executable":
        write(repository, "tests/test_unsafe.py").chmod(0o755)
    elif kind == "fifo":
        import os
        os.mkfifo(path)
    else:
        write(repository, "tests/test_unsafe::node.py")
    completed = run_cli(repository, "core-a")
    assert completed.returncode == 1
    assert completed.stdout == b""
    assert b"cannot partition public tests" in completed.stderr


@pytest.mark.parametrize("fault", ["missing_tests", "symlink_root", "missing_publication", "empty_core"])
def test_incomplete_inventory_cannot_silently_skip_a_partition(repository, tmp_path, fault):
    if fault == "missing_tests":
        repository = tmp_path / "nonexistent"
    elif fault == "symlink_root":
        moved = repository / "moved"
        (repository / "tests").rename(moved)
        (repository / "tests").symlink_to(moved, target_is_directory=True)
    elif fault == "missing_publication":
        (repository / sorted(partitioner.PUBLICATION_FILES)[0]).unlink()
    else:
        for name in partitioner.discover_test_files(repository):
            if name not in partitioner.PUBLICATION_FILES:
                (repository / name).unlink()
    completed = run_cli(repository, "publication")
    assert completed.returncode == 1
    assert completed.stdout == b""


def test_cli_rejects_unknown_partition(repository):
    completed = run_cli(repository, "arbitrary")
    assert completed.returncode == 2
    assert completed.stdout == b""


@pytest.mark.parametrize("options", [
    'testpaths = ["tests", "other"]', 'testpaths = "tests"',
    'testpaths = ["tests"]\npython_files = ["check_*.py"]',
    'testpaths = ["tests"]\nnorecursedirs = ["ignored"]',
    'testpaths = ["tests"]\ncollect_ignore = ["test_a.py"]',
])
def test_collection_configuration_drift_fails_before_output(repository, options):
    (repository / "pyproject.toml").write_text("[tool.pytest.ini_options]\n" + options)
    completed = run_cli(repository, "core-a")
    assert completed.returncode == 1
    assert completed.stdout == b""


@pytest.mark.parametrize("body", [
    "def pytest_ignore_collect(path): return True\n",
    "def pytest_collect_file(path): return None\n",
    "collect_ignore = ['test_a.py']\n", "collect_ignore_glob: list[str] = []\n",
    "from policy import pytest_collect_directory\n",
    '@pytest.hookimpl(specname="pytest_collect_file")\ndef custom(): pass\n',
    "def broken(:\n",
])
@pytest.mark.parametrize("location", ["tests/conftest.py", "tests/nested/conftest.py"])
def test_conftest_file_collection_policy_requires_review(repository, body, location):
    path = write(repository, location)
    path.write_text(body)
    completed = run_cli(repository, "core-b")
    assert completed.returncode == 1
    assert completed.stdout == b""


def test_default_patterns_and_ordinary_conftest_hooks_remain_supported(repository):
    (repository / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\npython_files = ["test_*.py", "*_test.py"]\n'
    )
    write(repository, "tests/conftest.py").write_text(
        '"""collect_ignore = [] is documentation."""\n'
        "# def pytest_ignore_collect(path): pass\n"
        "def pytest_collection_modifyitems(items): pass\n"
    )
    assert partitioner.partition_test_files(repository)


def test_alternate_pytest_configuration_requires_review(repository):
    (repository / "pytest.ini").write_text("[pytest]\n")
    completed = run_cli(repository, "publication")
    assert completed.returncode == 1
    assert completed.stdout == b""


def test_real_repository_inventory_is_partitioned_exactly_once():
    repo = Path(__file__).resolve().parent.parent
    partitions = partitioner.partition_test_files(repo)
    all_files = [name for names in partitions.values() for name in names]
    expected = {
        path.relative_to(repo).as_posix() for path in (repo / "tests").rglob("*.py")
        if path.name.startswith("test_") or path.name.endswith("_test.py")
    }
    assert set(all_files) == expected
    assert len(all_files) == len(expected)
