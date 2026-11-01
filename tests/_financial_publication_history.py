"""Explicit public-test profile for an unchanged, already published release.

This verifies BASE's site with BASE's published code. It never authorizes the
current runtime, invokes a publication entry point or consumes local continuity.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from src.publish import financial_continuity_inputs as files
from src.publish.financial_scope import ANCHOR

PROFILES = {
    "src.publish.financial_scope": (ANCHOR, "verify_financial"),
    "src.publish.source_data_scope": ("config/publish/source-data-release.json", "verify_source_data"),
}

AUTHORITY = (
    "config/publish",
    "config/chat",
    "src/publish",
    "contracts/web",
    "scripts/check_pages_publication.py",
    ".agents/skills/aeromexico-tracker-analysis/SKILL.md",
)
LOCAL_ONLY = {
    "config/publish/financial-continuity-local.json",
    "src/publish/financial_continuity.py",
    "src/publish/financial_continuity_inputs.py",
    "src/publish/README.md",
}
RUNTIME = (
    "src",
    "contracts",
    "config",
    "web",
    "uv.lock",
    "pyproject.toml",
    ".agents",
    "scripts/check_pages_publication.py",
)


def _authority_paths(repo):
    result = set()
    for name in AUTHORITY:
        root = repo / name
        if repo.is_symlink() or any((repo / part).is_symlink() for part in (Path(name), *Path(name).parents)):
            raise ValueError("Public authority root contains a symlink")
        paths = [root] if root.is_file() else root.rglob("*")
        for path in paths:
            if path.is_symlink():
                raise ValueError("Public authority contains a symlink")
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            relative = path.relative_to(repo).as_posix()
            if relative not in LOCAL_ONLY:
                result.add(relative)
    return result


def _bound_inputs(site, repo, base, module):
    if module not in PROFILES:
        raise ValueError("Unsupported historical publication profile")
    anchor, _ = PROFILES[module]
    if not isinstance(base, str) or not re.fullmatch("[a-f0-9]{40}", base):
        raise ValueError("Published-test BASE must be a full trusted commit SHA")
    head = files.transport._git(repo, "rev-parse", "HEAD").decode().strip()
    files.ancestor(repo, base, head)
    # The caller supplies the CI event's base SHA. It must also belong to the
    # fetched protected branch; HEAD/manifest cannot nominate another history.
    files.transport._git(repo, "merge-base", "--is-ancestor", base, "refs/remotes/origin/master")
    expected = files.tree_files(repo, base, "site")
    if files.site_files(site) != expected:
        raise ValueError("Historical profile requires every site byte to equal Git BASE")
    original = files.git_files(repo, base, [anchor, "site/publication_manifest.json"])
    if files.committed(repo, anchor) != original[anchor]:
        raise ValueError("Historical profile cannot change publication authority")
    before = files.git_files(repo, base, list(AUTHORITY))
    current = files.git_files(repo, "HEAD", list(AUTHORITY))
    before = {k: v for k, v in before.items() if k not in LOCAL_ONLY}
    current = {k: v for k, v in current.items() if k not in LOCAL_ONLY}
    if (
        current != before
        or _authority_paths(repo) != set(current)
        or any(files.regular(repo / k, repo) != v for k, v in current.items())
    ):
        raise ValueError("Public authority/revocation inputs changed; historical profile is unavailable")
    manifest = json.loads(original["site/publication_manifest.json"])
    code = manifest["code_commit"]
    files.ancestor(repo, code, base)
    program = files.git_files(repo, code, list(RUNTIME))
    if program.get(anchor) != original[anchor]:
        raise ValueError("Published code does not contain the original publication anchor")
    if f"{module.replace('.', '/')}.py" not in program:
        raise ValueError("Published publication verifier is absent")
    if "scripts/check_pages_publication.py" not in program:
        raise ValueError("Published strong publication selector is absent")
    for name in ("uv.lock", "pyproject.toml"):
        if files.committed(repo, name) != program[name]:
            raise ValueError("Historical dependency inputs differ from the active locked environment")
    return expected, original[anchor], program


def verify_published(site, repo, *, base_commit, module="src.publish.financial_scope"):
    """Return problems for historical verification only; no fallback on failure."""
    try:
        repo, site = Path(repo).absolute(), Path(site).absolute()
        if site != repo / "site":
            raise ValueError("Historical profile requires this repository's site")
        expected, anchor_raw, program = _bound_inputs(site, repo, base_commit, module)
        spec = json.loads(anchor_raw)
        with tempfile.TemporaryDirectory(prefix="published-financial-check-") as folder:
            archive = Path(folder)
            for name, raw in program.items():
                target = archive / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            (archive / ".git").symlink_to(repo / ".git")
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            env.pop("PYTHONHOME", None)
            command = """import json,socket,sys
from pathlib import Path
def offline(*a,**k):raise RuntimeError('Historical verifier network is forbidden')
socket.create_connection=offline;socket.getaddrinfo=offline
socket.socket.connect=offline;socket.socket.connect_ex=offline
from importlib import import_module
from src.analysis_agent import entity_adapter
publication=import_module(sys.argv[3])
root=Path.cwd().resolve()
assert Path(publication.__file__).resolve().is_relative_to(root)
assert Path(entity_adapter.__file__).resolve().is_relative_to(root)
runtime=entity_adapter.code_version()
assert runtime==sys.argv[2], 'Published runtime does not match its reviewed producer'
print(json.dumps({'runtime':runtime,'problems':getattr(publication,sys.argv[4])(Path(sys.argv[1]),root)}))
"""
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    command,
                    str(site),
                    spec["producer_code_version"],
                    module,
                    PROFILES[module][1],
                ],
                cwd=archive,
                env=env,
                capture_output=True,
                text=True,
                # SourceData replays the complete chain of issuer releases;
                # existing CI observes >240 s for that strong historical check.
                timeout=600 if module == "src.publish.source_data_scope" else 120,
            )
            if result.returncode:
                raise ValueError("Original published financial verifier failed; no fallback permitted")
            verdict = json.loads(result.stdout)
            if verdict["runtime"] != spec["producer_code_version"] or verdict["problems"]:
                raise ValueError("Original published financial verification rejected this site")
            if any((archive / k).read_bytes() != v for k, v in program.items()):
                raise ValueError("Archived financial verification inputs changed")
        if _bound_inputs(site, repo, base_commit, module) != (expected, anchor_raw, program):
            raise ValueError("Published verification inputs changed during the check")
        return []
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        return [f"Invalid historical financial test profile: {exc}"]
