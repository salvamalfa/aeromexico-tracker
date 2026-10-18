"""Keep only required chat configuration in the Docker build context."""

import fnmatch
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

from src.web_export.contract_versions import ARCHIVED_CONTRACTS, resolve_contract

ROOT = Path(__file__).resolve().parents[1]


def _materialize_runtime_copy(tmp_path, *, contracts_only=False):
    """Model runtime-stage COPY and context admission, without a Docker daemon."""
    rules = (ROOT / ".dockerignore").read_text().splitlines()

    def admitted(path):
        for candidate in (path, *path.parents):
            if candidate == ROOT:
                break
            relative = candidate.relative_to(ROOT).as_posix()
            allowed = True
            for rule in rules:
                if not rule or rule.startswith("#"):
                    continue
                pattern = rule.lstrip("!").rstrip("/")
                if PurePosixPath(relative).full_match(pattern):
                    allowed = rule.startswith("!")
            if not allowed:
                return False
        return True

    runtime_stage = False
    for line in (ROOT / "Dockerfile.chat").read_text().splitlines():
        if line.startswith("FROM "):
            runtime_stage = line.endswith(" AS runtime")
        if not runtime_stage or not line.startswith("COPY "):
            continue
        parts = shlex.split(line)
        if not parts or parts[0] != "COPY" or parts[1].startswith("--"):
            continue
        destination = tmp_path / parts[-1]
        for source in parts[1:-1]:
            if contracts_only and not source.startswith("contracts/web"):
                continue
            for match in ROOT.glob(source):
                files = list(match.rglob("*")) if match.is_dir() else [match]
                for file in files:
                    if file.is_file() and admitted(file):
                        suffix = file.relative_to(match) if match.is_dir() else Path(file.name)
                        target = (
                            destination / suffix
                            if match.is_dir() or parts[-1].endswith("/") or len(parts[1:-1]) > 1
                            else destination
                        )
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file, target)


def test_runtime_image_contains_every_exact_retained_contract(tmp_path):
    """Exercise the resolver against files actually admitted by Docker COPY."""
    _materialize_runtime_copy(tmp_path, contracts_only=True)
    for name, versions in ARCHIVED_CONTRACTS.items():
        for digest in versions:
            resolved = resolve_contract(tmp_path / "contracts/web", name, digest)
            assert resolved == tmp_path / "contracts/web/versions" / digest / name


def test_packaged_files_load_the_public_snapshot_without_checkout_fallback(tmp_path):
    from src.conversational_analytics.data.snapshot import data_version

    _materialize_runtime_copy(tmp_path)
    assert not (tmp_path / "analysis_runs").exists()
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "src/publish/gate.py").exists()
    environment = {**os.environ, "PYTHONPATH": str(tmp_path)}
    environment.pop("OPENAI_API_KEY", None)
    code = (
        "from pathlib import Path; from src.config import PATHS; "
        "from src.conversational_analytics.data.snapshot import Snapshot; "
        "assert PATHS.root == Path.cwd(); "
        "print(Snapshot(Path('site')).version)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    expected = data_version(json.loads((ROOT / "site/publication_manifest.json").read_text()))
    assert result.stdout.strip() == expected


def test_chat_runtime_configuration_is_reincluded_in_docker_context():
    rules = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())
    dockerfile = (ROOT / "Dockerfile.chat").read_text(encoding="utf-8")

    # Docker applies ignore rules to parent directories too, so both directory
    # levels and each nested runtime input must be explicitly re-included.
    required_rules = {
        "!config/",
        "!config/chat/",
        "!config/chat/models.json",
        "!config/chat/metrics-candidates.json",
        "!config/chat/business-metrics-proposal.json",
        "!config/chat/system_prompt.txt",
        "!config/chat/prompt_approval.json",
        "!config/chat/evidence/",
        "!config/chat/evidence/approved-index.json",
        "!config/chat/prompt_candidates/",
        "!config/chat/prompt_candidates/system_prompt_r2-proposed.txt",
        "!config/chat/prompt_candidates/system_prompt_r2-proposed.json",
    }
    assert required_rules <= rules
    copied_config_files: set[str] = set()
    copied_files: set[str] = set()
    for line in dockerfile.splitlines():
        parts = line.split()
        if not parts or parts[0] != "COPY" or any(part.startswith("--from") for part in parts):
            continue
        for source in parts[1:-1]:
            matches = (
                [ROOT / source] if not any(char in source for char in "*?[") else list(ROOT.glob(source))
            )
            assert matches, f"COPY source {source} has no local build input"
            for match in matches:
                if match.is_file():
                    relpath = match.relative_to(ROOT).as_posix()
                    copied_files.add(relpath)
                    if relpath.startswith("config/chat/"):
                        copied_config_files.add(relpath)

    assert {
        "config/chat/models.json",
        "config/chat/metrics-candidates.json",
        "config/chat/business-metrics-proposal.json",
        "config/chat/system_prompt.txt",
        "config/chat/prompt_approval.json",
        "config/chat/evidence/approved-index.json",
        "config/chat/prompt_candidates/system_prompt_r2-proposed.txt",
        "config/chat/prompt_candidates/system_prompt_r2-proposed.json",
    } <= copied_config_files
    assert "config/chat/runtime.example.env" not in copied_files
    assert "config/chat/business-metrics-approval-receipt.json" not in copied_files

    # Every copied configuration file and each directory leading to it must
    # have an explicit allow rule; the broad default remains deny-all.
    for relpath in copied_config_files:
        assert any(rule.startswith("!") and fnmatch.fnmatchcase(relpath, rule[1:]) for rule in rules), relpath
        for parent in Path(relpath).parents:
            if str(parent) == ".":
                continue
            parent_rule = f"!{parent.as_posix()}/"
            assert parent_rule in rules, parent_rule

    # Keep candidate records, inbox contents, and local state out of the image.
    assert "!config/chat/evidence/**" not in rules
    assert "!config/chat/prompt_candidates/**" not in rules
    assert "!config/chat/**" not in rules
