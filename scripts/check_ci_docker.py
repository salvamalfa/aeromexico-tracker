"""Build and exercise Dockerfile.chat before running the expensive CI suites.

The default is a dry run. Cache state is an operator declaration, not a measured
claim: --no-cache disables Docker stage reuse, not registry or package caches.
The JSON report records log hashes and lengths, never log text or environment
values. The runtime receives only the two public approval pins, by name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PINS = (
    "CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256",
    "CHAT_EVIDENCE_APPROVED_INDEX_SHA256",
)
DOCKER = ["docker", "--host=unix:///var/run/docker.sock"]
IMAGE_LABEL = "org.opencontainers.image.revision"
RUNTIME_PROBE = """import asyncio
import hashlib
import json
import secrets
import tempfile
from pathlib import Path
import scripts.start_chat_runtime
from src.config import PATHS
from src.conversational_analytics.api import create_app
from src.conversational_analytics.auth import hash_password
from src.conversational_analytics.config import ChatConfig
from src.conversational_analytics.data.snapshot import Snapshot
from src.web_export.contract_versions import ARCHIVED_CONTRACTS, resolve_contract

root = Path.cwd()
assert PATHS.root == root, "runtime imported code from outside the image"
assert not (root / "tests").exists(), "test fixtures entered the runtime image"
assert not (root / "analysis_runs").exists(), "private analysis entered the runtime image"
assert not (root / "data/warehouse.duckdb").exists(), "warehouse entered the runtime image"
retained_contracts_verified = 0
for name, versions in ARCHIVED_CONTRACTS.items():
    for expected in versions:
        archived = root / "contracts/web/versions" / expected / name
        assert archived.is_file(), "a retained runtime contract is missing"
        assert hashlib.sha256(archived.read_bytes()).hexdigest() == expected
        resolved = resolve_contract(root / "contracts/web", name, expected)
        assert hashlib.sha256(resolved.read_bytes()).hexdigest() == expected
        retained_contracts_verified += 1
# Construct explicitly before create_app: its unavailable-snapshot mode must
# never turn a missing contract or invalid published payload into smoke success.
snapshot = Snapshot(root / "site")
assert snapshot.version != "unavailable", "published snapshot is unavailable"

async def check_worker():
    with tempfile.TemporaryDirectory(prefix="ci-docker-runtime-") as temporary:
        config = ChatConfig(
            state_path=Path(temporary) / "chat.sqlite3",
            auth_mode="password",
            password_users={"owner": hash_password(secrets.token_urlsafe(24))},
            allowed_origins=("https://ci.example.invalid",),
            provider="mock",
            openai_enabled=False,
        )
        app = create_app(config, snapshot=snapshot, start_worker=True)
        async with app.router.lifespan_context(app):
            assert app.state.snapshot_available
            assert app.state.chat_worker and app.state.chat_worker.running
        assert not app.state.chat_worker.running

asyncio.run(check_worker())
print(json.dumps({
    "status": "docker_runtime_verified",
    "snapshot_version": snapshot.version,
    "manifest_sha256": hashlib.sha256((root / "site/publication_manifest.json").read_bytes()).hexdigest(),
    "provider": "mock",
    "worker_started_and_stopped": True,
    "retained_contracts_verified": retained_contracts_verified,
}))
"""


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def docker_environment() -> dict[str, str]:
    """Use the local daemon and keep its existing registry/proxy configuration."""
    environment = dict(os.environ)
    for key in (
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "DOCKER_TLS",
        "DOCKER_TLS_VERIFY",
        "DOCKER_CERT_PATH",
        "OPENAI_API_KEY",
    ):
        environment.pop(key, None)
    for key in list(environment):
        if key.startswith("CHAT_") and key not in PINS:
            environment.pop(key)
    return environment


def git(root: Path, *arguments: str) -> bytes:
    return subprocess.check_output(["git", *arguments], cwd=root, stderr=subprocess.PIPE)


def source_identity(root: Path) -> dict:
    head = git(root, "rev-parse", "HEAD").decode().strip()
    if not re.fullmatch(r"[a-f0-9]{40}", head):
        raise ValueError("Docker preflight requires an exact Git commit")
    if Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() != root:
        raise ValueError("Docker context must be the Git checkout root")
    changed = git(root, "diff", "--binary", "HEAD", "--")
    names = (
        "Dockerfile.chat",
        ".dockerignore",
        "pyproject.toml",
        "uv.lock",
        "site/publication_manifest.json",
    )
    return {
        "head": head,
        "tracked_tree": git(root, "rev-parse", "HEAD^{tree}").decode().strip(),
        "tracked_worktree_dirty": bool(changed),
        "tracked_worktree_diff_sha256": sha256(changed),
        "input_sha256": {name: sha256((root / name).read_bytes()) for name in names},
    }


def build_command(root: Path, head: str, tag: str, no_cache: bool) -> list[str]:
    return [
        *DOCKER,
        "build",
        "--file",
        str(root / "Dockerfile.chat"),
        "--target",
        "runtime",
        "--label",
        f"{IMAGE_LABEL}={head}",
        "--tag",
        tag,
        *(["--no-cache"] if no_cache else []),
        str(root),
    ]


def runtime_command(image_id: str) -> list[str]:
    return [
        *DOCKER,
        "run",
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--workdir=/app",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,mode=1777",
        "--tmpfs",
        "/data:rw,nosuid,nodev,mode=700",
        "--env",
        "CHAT_PROVIDER=mock",
        "--env",
        "CHAT_OPENAI_ENABLED=false",
        "--env",
        "PYTHONPATH=/app",
        "--env",
        "PYTHONDONTWRITEBYTECODE=1",
        *[value for name in PINS for value in ("--env", name)],
        "--entrypoint=python",
        image_id,
        "-c",
        RUNTIME_PROBE,
    ]


def run_phase(
    name: str, command: list[str], root: Path, environment: dict, timeout: int
) -> tuple[dict, bytes]:
    started = time.monotonic()
    result = {"name": name, "command": command}
    try:
        completed = subprocess.run(command, cwd=root, env=environment, capture_output=True, timeout=timeout)
        stdout, stderr = completed.stdout, completed.stderr
        result["exit_code"] = completed.returncode
    except subprocess.TimeoutExpired as exc:
        stdout, stderr = exc.stdout or b"", exc.stderr or b""
        result.update(exit_code=None, error="timeout")
    except OSError as exc:
        stdout, stderr = b"", b""
        result.update(exit_code=None, error=type(exc).__name__)
    result.update(
        elapsed_seconds=round(time.monotonic() - started, 6),
        stdout_sha256=sha256(stdout),
        stdout_bytes=len(stdout),
        stderr_sha256=sha256(stderr),
        stderr_bytes=len(stderr),
    )
    return result, stdout


def preflight(root: Path, *, execute: bool, cache_state: str, no_cache: bool) -> dict:
    root = root.resolve()
    source = source_identity(root)
    tag = f"airlines-ci-preflight:{source['head']}"
    build = build_command(root, source["head"], tag, no_cache)
    inspect = [
        *DOCKER,
        "image",
        "inspect",
        "--format",
        f'{{{{.Id}}}} {{{{index .Config.Labels "{IMAGE_LABEL}"}}}}',
        tag,
    ]
    report = {
        "schema_version": "ci_docker_preflight_v1",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "status": "planned" if not execute else "running",
        "source": source,
        "cache": {
            "declared_state": cache_state,
            "docker_stage_cache_disabled": no_cache,
            "effective_cache_measured": False,
        },
        "probe_sha256": sha256(RUNTIME_PROBE.encode()),
        "runtime_network": "none",
        "runtime_host_mounts": [],
        "approval_environment_names": list(PINS),
        "plan": {"build": build, "inspect": inspect, "runtime": runtime_command("<built-image-id>")},
        "phases": [],
    }
    if not execute:
        return report
    environment = docker_environment()
    for name, command, timeout in (("build", build, 1800), ("inspect", inspect, 30)):
        phase, output = run_phase(name, command, root, environment, timeout)
        report["phases"].append(phase)
        if phase["exit_code"] != 0:
            return report | {"status": "failed", "failed_phase": name}
    identity = output.decode("utf-8", errors="replace").strip().split()
    if (
        len(identity) != 2
        or not re.fullmatch(r"sha256:[a-f0-9]{64}", identity[0])
        or identity[1] != source["head"]
    ):
        return report | {"status": "failed", "failed_phase": "inspect", "error": "image_identity_mismatch"}
    image_id = identity[0]
    report["image_id"] = image_id
    phase, output = run_phase("runtime", runtime_command(image_id), root, environment, 120)
    report["phases"].append(phase)
    if phase["exit_code"] != 0:
        return report | {"status": "failed", "failed_phase": "runtime"}
    try:
        observed = json.loads(output)
        if (
            observed.get("status") != "docker_runtime_verified"
            or observed.get("manifest_sha256") != source["input_sha256"]["site/publication_manifest.json"]
            or not re.fullmatch(r"[a-f0-9]{64}", observed.get("snapshot_version", ""))
            or observed.get("provider") != "mock"
            or observed.get("worker_started_and_stopped") is not True
            or type(observed.get("retained_contracts_verified")) is not int
            or observed["retained_contracts_verified"] < 1
        ):
            raise ValueError("runtime observation mismatch")
    except (ValueError, TypeError, AttributeError):
        return report | {
            "status": "failed",
            "failed_phase": "runtime",
            "error": "invalid_runtime_observation",
        }
    if source_identity(root) != source:
        return report | {
            "status": "failed",
            "failed_phase": "source",
            "error": "checkout_changed_during_preflight",
        }
    return report | {"status": "passed", "runtime": observed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--cache-state", choices=("cold", "warm", "unknown"), default="unknown")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args(argv)
    if args.execute and args.dry_run:
        parser.error("choose --execute or --dry-run")
    try:
        report = preflight(
            args.root, execute=args.execute, cache_state=args.cache_state, no_cache=args.no_cache
        )
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        report = {
            "schema_version": "ci_docker_preflight_v1",
            "status": "failed",
            "failed_phase": "source",
            "error": type(exc).__name__,
        }
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    sys.stdout.write(payload)
    return 1 if report["status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
