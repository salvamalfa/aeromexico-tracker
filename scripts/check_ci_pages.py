"""Exercise the exact locked Pages profile before the expensive CI suites.

The report records process timings and log hashes, never log or environment
contents. A dry run launches neither uv nor a publication verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
INSTALL = ("uv", "sync", "--locked", "--no-group", "dev", "--extra", "analytics")
VERIFY = (
    "uv", "run", "--locked", "--no-group", "dev", "--extra", "analytics",
    "python", "scripts/check_pages_publication.py", "site/",
)
# Match the public historical-test eligibility boundary. Historical strong
# verification is opt-in; the default retains the public suite's responsibility.
AUTHORITY = (
    "config/publish", "config/chat", "src/publish",
    ".agents/skills/aeromexico-tracker-analysis/SKILL.md",
)
LOCAL_ONLY = {
    "config/publish/financial-continuity-local.json",
    "src/publish/financial_continuity.py",
    "src/publish/financial_continuity_inputs.py",
    "src/publish/README.md",
}
BOUND_ROOTS = ("site", *AUTHORITY, "uv.lock", "pyproject.toml")
ENVIRONMENT_PROBE = (
    "from importlib import import_module; from pathlib import Path; "
    "from scripts.check_pages_publication import verifier_for; "
    "module=verifier_for(Path('site'),Path.cwd()); import_module(module); print(module)"
)
ENVIRONMENT_VERIFY = (*VERIFY[:-2], "-c", ENVIRONMENT_PROBE)
PUBLISHED_CONFIG = (AUTHORITY[0], AUTHORITY[1], AUTHORITY[3])
DEPENDENCIES = ("uv.lock", "pyproject.toml")


class HistoricalCleanupError(ValueError):
    """A temporary Git worktree could not be removed safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_identity(raw: bytes) -> dict:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def git_head(root: Path) -> str:
    head = git(root, "rev-parse", "HEAD").decode("ascii").strip()
    if not re.fullmatch(r"[a-f0-9]{40}", head):
        raise ValueError("Checkout HEAD must be an exact Git commit")
    return head


def git(root: Path, *arguments: str) -> bytes:
    # A detached worktree must belong to this checkout, without ambient Git
    # redirects, replacement objects or checkout hooks changing its inputs.
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    return subprocess.run(
        [
            "git", "--no-replace-objects", "-c", f"core.hooksPath={os.devnull}",
            "-c", "core.fsmonitor=false", *arguments,
        ],
        cwd=root, env=environment, capture_output=True, check=True,
    ).stdout


def runtime_path(name: str) -> bool:
    """Cover code_version inputs without importing the candidate's runtime."""
    path = PurePosixPath(name)
    if name.startswith("src/") and path.suffix == ".py":
        return True
    if name.startswith("contracts/web/"):
        return True
    if name.startswith("web/src/"):
        tests = {"test", "tests", "spec", "specs", "__tests__", "__specs__"}
        return (
            path.suffix in {".ts", ".tsx", ".js", ".jsx", ".json", ".css"}
            and not tests.intersection(path.parts[2:])
            and not re.search(r"(?:^|[._-])(?:test|spec)(?:[._-]|$)", path.name)
        )
    return name in {
        "web/index.html", "web/package.json", "web/package-lock.json", "web/vite.config.ts",
    } or bool(re.fullmatch(r"web/tsconfig[^/]*\.json", name))


def excluded_bound_path(name: str) -> bool:
    if name in LOCAL_ONLY:
        return True
    return not name.startswith("site/") and (
        "__pycache__" in PurePosixPath(name).parts or name.endswith(".pyc")
    )


def git_files(
    root: Path, reference: str, roots: tuple[str, ...], *, runtime_only: bool = False,
    exclude_local_only: bool = True,
) -> dict:
    expected = {}
    for item in git(root, "ls-tree", "-r", "-z", reference, "--", *roots).split(b"\0"):
        if not item:
            continue
        header, raw_name = item.split(b"\t", 1)
        mode, kind, identity = header.decode("ascii").split()
        name = raw_name.decode("utf-8")
        if (runtime_only and not runtime_path(name)) or (
            exclude_local_only and not runtime_only and name in LOCAL_ONLY
        ):
            continue
        if kind != "blob" or mode not in {"100644", "100755"}:
            raise ValueError("Bound Git input is not a regular file")
        expected[name] = identity
    return expected


def bound_worktree(root: Path, head: str) -> str:
    """Require the complete current site/authority/dependency bytes from Git."""
    expected = git_files(root, head, BOUND_ROOTS)
    actual = set()
    for name in BOUND_ROOTS:
        directory = root / name
        if any(part.is_symlink() for part in (directory, *directory.parents) if part != root.parent):
            raise ValueError("Bound input contains a symlink")
        paths = directory.rglob("*") if directory.is_dir() else (directory,)
        for path in paths:
            relative = path.relative_to(root).as_posix()
            if excluded_bound_path(relative):
                continue
            if path.is_symlink():
                raise ValueError("Bound input contains a symlink")
            if not path.exists() or path.is_dir():
                continue
            if not stat.S_ISREG(path.stat().st_mode):
                raise ValueError("Bound input is not a regular file")
            if relative not in expected:
                raise ValueError("Bound worktree contains an untracked input")
            raw = path.read_bytes()
            identity = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
            if expected.get(relative) != identity:
                raise ValueError("Bound worktree bytes differ from Git HEAD")
            actual.add(relative)
    if actual != set(expected):
        raise ValueError("Bound worktree inventory differs from Git HEAD")
    return hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()


def verification_policy(root: Path, base: str | None, head: str) -> dict:
    policy = {"mode": "current_site_strong", "base": base, "head": head, "reason": "no_trusted_base"}
    if not isinstance(base, str) or not re.fullmatch(r"[a-f0-9]{40}", base):
        return policy
    try:
        git(root, "cat-file", "-e", base + "^{commit}")
        git(root, "merge-base", "--is-ancestor", base, head)
        git(root, "merge-base", "--is-ancestor", base, "refs/remotes/origin/master")
        if git_files(root, base, BOUND_ROOTS) != git_files(root, head, BOUND_ROOTS):
            return policy | {"reason": "publication_authority_or_dependencies_changed"}
        runtime_roots = ("src", "web", "contracts/web")
        if git_files(root, base, runtime_roots, runtime_only=True) == git_files(
            root, head, runtime_roots, runtime_only=True,
        ):
            return policy | {"reason": "reviewed_runtime_inputs_unchanged"}
        snapshot = bound_worktree(root, head)
        return policy | {
            "mode": "environment_only",
            "reason": "unchanged_published_site_with_conserved_authority_and_dependencies",
            "bound_inputs_sha256": snapshot,
        }
    except (OSError, ValueError, subprocess.CalledProcessError, UnicodeError):
        return policy | {"reason": "eligibility_uncertain_use_current_strong"}


def isolated_environment(root: Path, environment: dict[str, str]) -> Path:
    value = environment.get("UV_PROJECT_ENVIRONMENT", "").strip()
    if not value:
        raise ValueError("UV_PROJECT_ENVIRONMENT must identify the isolated Pages environment")
    path = Path(value)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    # The shared test/development environment must not accidentally supply
    # dependencies missing from the actual locked Pages profile.
    if path == root.resolve() / ".venv" or root.resolve() in path.parents:
        raise ValueError("The Pages environment must be outside the checkout")
    return path


def published_base_plan(root: Path, policy: dict) -> dict:
    """Bind the published producer to trusted BASE without running its code."""
    manifest = json.loads((root / "site/publication_manifest.json").read_bytes())
    producer = manifest.get("code_commit") if isinstance(manifest, dict) else None
    if not isinstance(producer, str) or not re.fullmatch(r"[a-f0-9]{40}", producer):
        raise ValueError("Historical verification requires an exact published producer commit")
    git(root, "merge-base", "--is-ancestor", producer, policy["base"])
    # Producer code can predate later code-only merges in BASE. Its complete
    # publication configuration and locked dependencies must still be current.
    for roots in (PUBLISHED_CONFIG, DEPENDENCIES):
        if git_files(root, producer, roots) != git_files(root, policy["head"], roots):
            raise ValueError("Published producer configuration or locked dependencies changed")
    selector = "scripts/check_pages_publication.py"
    if selector not in git_files(root, producer, (selector,)):
        raise ValueError("Published producer has no strong publication selector")
    return {
        "base": policy["base"],
        "producer": producer,
        "checkout": "temporary_detached_producer_worktree",
        "site": "complete_bound_current_site_copied_byte_for_byte",
        "command": list(VERIFY),
        "approval_scope": "historical_site_only",
    }


def revalidate_policy(root: Path, policy: dict) -> None:
    if (
        git_head(root) != policy["head"]
        or verification_policy(root, policy["base"], policy["head"]) != policy
    ):
        raise ValueError("Historical verification policy or checkout changed")


def historical_snapshot(root: Path, producer: str, expected: dict, marker: bytes) -> str:
    """Bind every producer file plus the overlaid site, including ignored files."""
    git_marker = root / ".git"
    if git_marker.is_symlink() or not git_marker.is_file() or git_marker.read_bytes() != marker:
        raise ValueError("Historical worktree Git marker changed")
    if git_head(root) != producer:
        raise ValueError("Historical worktree producer changed")
    actual = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        if relative == ".git":
            continue
        if path.is_symlink():
            raise ValueError("Historical worktree contains a symlink")
        if not path.is_file():
            if not path.is_dir():
                raise ValueError("Historical worktree contains a nonregular input")
            continue
        raw = path.read_bytes()
        actual[relative] = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if actual != expected:
        raise ValueError("Historical worktree inputs changed")
    return hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest()


@contextmanager
def published_worktree(root: Path, policy: dict, plan: dict):
    """Use a disposable detached producer checkout; never create a branch."""
    with tempfile.TemporaryDirectory(prefix="ci-pages-published-") as folder:
        checkout = Path(folder) / "checkout"
        added = False
        try:
            git(root, "worktree", "add", "--detach", str(checkout), plan["producer"])
            added = True
            expected = git_files(root, plan["producer"], (), exclude_local_only=False)
            expected = {name: identity for name, identity in expected.items() if not name.startswith("site/")}
            expected.update(git_files(root, policy["head"], ("site",), exclude_local_only=False))
            site = checkout / "site"
            if site.is_symlink() or (site.exists() and not site.is_dir()):
                raise ValueError("Historical site is not a regular directory")
            if site.exists():
                shutil.rmtree(site)
            shutil.copytree(root / "site", site, symlinks=True)
            marker = (checkout / ".git").read_bytes()
            historical_snapshot(checkout, plan["producer"], expected, marker)
            yield checkout, expected, marker
        finally:
            if added or checkout.exists():
                try:
                    git(root, "worktree", "remove", "--force", str(checkout))
                except (OSError, subprocess.CalledProcessError) as exc:
                    raise HistoricalCleanupError("Temporary historical worktree removal failed") from exc


def run_phase(name: str, command: tuple[str, ...], root: Path, environment: dict[str, str]) -> dict:
    started = utc_now()
    clock = time.perf_counter()
    try:
        completed = subprocess.run(command, cwd=root, env=environment, capture_output=True, check=False)
        code = completed.returncode
        stdout, stderr = completed.stdout, completed.stderr
        error_type = None
    except OSError as exc:
        code, stdout, stderr = 127, b"", b""
        error_type = type(exc).__name__
    return {
        "phase": name,
        "command": list(command),
        "started_at": started,
        "completed_at": utc_now(),
        "elapsed_seconds": time.perf_counter() - clock,
        "exit_code": code,
        "error_type": error_type,
        "stdout": log_identity(stdout),
        "stderr": log_identity(stderr),
    }


def preflight(
    root: Path, *, execute: bool, cache_state: str, environment: dict[str, str], base: str | None = None,
    verify_published_base: bool = False,
) -> dict:
    root = root.resolve()
    report = {
        "schema_version": "ci_pages_preflight_v2",
        "status": "planned",
        "execution_requested": execute,
        "executed": False,
        "checkout": str(root),
        "head": None,
        "cache_state_declared": cache_state,
        "cache_state_observed": "not_inferred",
        "measurement_scope": "process wall time; no claim about download caches or global CI savings",
        "environment_path": None,
        "environment_existed_before": None,
        "commands": [list(INSTALL), list(VERIFY)],
        "verification_policy": None,
        "site_verification": "not_executed",
        "current_site_strong_verified": False,
        "current_runtime_approved": False,
        "phases": [],
        "failed_phase": None,
        "started_at": utc_now(),
        "completed_at": None,
        "elapsed_seconds": None,
    }
    if verify_published_base:
        report.update(historical_site_strong_verified=False, historical_verification_plan=None)
    clock = time.perf_counter()
    error_phase = "configuration"
    try:
        report["head"] = git_head(root)
        policy = verification_policy(root, base, report["head"])
        report["verification_policy"] = policy
        environment_only = policy["mode"] == "environment_only"
        verify_command = ENVIRONMENT_VERIFY if environment_only else VERIFY
        report["commands"] = [list(INSTALL), list(verify_command)]
        path = isolated_environment(root, environment)
        report["environment_path"] = str(path)
        report["environment_existed_before"] = path.exists()
        historical = environment_only and verify_published_base
        if historical:
            error_phase = "historical_setup"
            report["historical_verification_plan"] = published_base_plan(root, policy)
            report["commands"].append(list(VERIFY))
        if execute:
            child_environment = dict(environment)
            child_environment["UV_PROJECT_ENVIRONMENT"] = str(path)
            # Pages never needs a provider credential; dependency downloads
            # retain the configured proxy, CA and runtime guard variables.
            child_environment.pop("OPENAI_API_KEY", None)
            child_environment.pop("PYTHONPATH", None)
            child_environment.pop("PYTHONHOME", None)
            if historical:
                child_environment = {
                    key: value for key, value in child_environment.items() if not key.startswith("GIT_")
                }
                child_environment.update(
                    GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1", GIT_NO_REPLACE_OBJECTS="1",
                    PYTHONDONTWRITEBYTECODE="1",
                )
            phases = (("install", INSTALL), ("imports" if environment_only else "verify", verify_command))
            for name, command in phases:
                report["executed"] = True
                phase = run_phase(name, command, root, child_environment)
                report["phases"].append(phase)
                if phase["exit_code"] != 0:
                    report["status"] = "failed"
                    report["failed_phase"] = name
                    break
                if environment_only and (
                    git_head(root) != report["head"]
                    or verification_policy(root, base, report["head"]) != policy
                ):
                    report["status"] = "failed"
                    report["failed_phase"] = "policy_revalidation"
                    break
            else:
                if historical:
                    error_phase = "policy_revalidation"
                    revalidate_policy(root, policy)
                    error_phase = "historical_setup"
                    plan = report["historical_verification_plan"]
                    with published_worktree(root, policy, plan) as (checkout, expected, marker):
                        error_phase = "policy_revalidation"
                        revalidate_policy(root, policy)
                        error_phase = "historical_revalidation"
                        historical_snapshot(checkout, plan["producer"], expected, marker)
                        error_phase = "historical_verify"
                        phase = run_phase("historical_verify", VERIFY, checkout, child_environment)
                        report["phases"].append(phase)
                        if phase["exit_code"] != 0:
                            report["status"] = "failed"
                            report["failed_phase"] = "historical_verify"
                        error_phase = "historical_revalidation"
                        historical_snapshot(checkout, plan["producer"], expected, marker)
                        error_phase = "policy_revalidation"
                        revalidate_policy(root, policy)
                    if report["status"] != "failed":
                        report["historical_site_strong_verified"] = True
                if report["status"] != "failed":
                    report["status"] = "passed"
                    report["site_verification"] = (
                        "historical_site_strong_verified" if historical
                        else "historical_site_not_reapproved" if environment_only
                        else "current_site_strong_verified"
                    )
                    report["current_site_strong_verified"] = not environment_only
    except (OSError, ValueError, subprocess.CalledProcessError, UnicodeError) as exc:
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        report["failed_phase"] = (
            "historical_cleanup" if isinstance(exc, HistoricalCleanupError) else error_phase
        )
    finally:
        report["completed_at"] = utc_now()
        report["elapsed_seconds"] = time.perf_counter() - clock
    return report


def write_report(path: Path, report: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--base", help="Exact event BASE SHA; uncertainty always retains current strong verification",
    )
    parser.add_argument(
        "--verify-published-base", action="store_true",
        help="Strongly verify an unchanged historical site with its producer in environment-only mode",
    )
    parser.add_argument("--cache-state", choices=("cold", "warm", "unknown"), default="unknown")
    args = parser.parse_args(argv)
    report = preflight(
        ROOT, execute=args.execute, cache_state=args.cache_state, environment=dict(os.environ),
        base=args.base,
        verify_published_base=args.verify_published_base,
    )
    if args.report is not None:
        write_report(args.report, report)
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
