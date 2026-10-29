"""Run pytest unchanged and retain CPU, simultaneous RSS and fresh inventories.

Linux CI only. RSS is the sampled sum of this profiler and its descendants;
shared pages can be counted more than once. Kernel largest-child RSS is retained
separately. Neither metric nor inventory is used to omit or accept any test.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import resource
import signal
import subprocess
import sys
import time

HERE = Path(__file__).resolve()
ROOT = HERE.parents[2]
PIN_NAMES = (
    "CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256",
    "CHAT_EVIDENCE_APPROVED_INDEX_SHA256",
)
SOURCE_PATHS = (
    "src",
    "scripts",
    "tests",
    "config",
    "contracts",
    "data",
    "site",
    "web",
    "pyproject.toml",
    "uv.lock",
    ".github/ci",
    ".github/ci-test-tools.txt",
)


def _rss_tree() -> tuple[int, int]:
    # PPid is available even on kernels without /proc/PID/task/TID/children.
    processes = {}
    children = defaultdict(list)
    page_size = os.sysconf("SC_PAGE_SIZE")
    for directory in Path("/proc").iterdir():
        if not directory.name.isdecimal():
            continue
        try:
            fields = (directory / "stat").read_text().rsplit(")", 1)[1].split()
            pid = int(directory.name)
            parent = int(fields[1])
            processes[pid] = max(0, int(fields[21])) * page_size
            children[parent].append(pid)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            continue
    if os.getpid() not in processes:
        raise RuntimeError("Cannot enumerate profiler process in /proc")
    pending = [os.getpid()]
    visited = set()
    rss = 0
    while pending:
        pid = pending.pop()
        if pid in visited:
            continue
        visited.add(pid)
        rss += processes[pid]
        pending.extend(children[pid])
    return rss, len(visited)


def _source_state() -> dict:
    tracked = subprocess.run(["git", "diff", "HEAD", "--quiet", "--", *SOURCE_PATHS], cwd=ROOT)
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "-z", "--", *SOURCE_PATHS], cwd=ROOT
    )
    return {
        "clean": tracked.returncode == 0 and not untracked,
        "untracked_count": len(untracked.split(b"\0")) - 1 if untracked else 0,
        "untracked_paths_sha256": hashlib.sha256(untracked).hexdigest(),
    }


def _inventory_errors(output: Path, label: str, workers: int) -> list[str]:
    records = {
        path.stem.removeprefix(f"{label}-inventory-"): json.loads(path.read_text())
        for path in output.glob(f"{label}-inventory-*.json")
    }
    expected = ["main"] if workers == 0 else [f"gw{i}" for i in range(workers)]
    if any(name not in records for name in expected) or "main" not in records:
        return ["A process inventory is missing"]
    runners = [records[name] for name in expected]
    selected = runners[0]["selected"]
    deselected = runners[0]["deselected"]
    errors = []
    if any(run["selected"] != selected or run["deselected"] != deselected for run in runners):
        errors.append("Worker collection differs")
    executed = []
    for run in runners:
        phases = [(item["id"], item["phase"]) for item in run["reports"]]
        if len(phases) != len(set(phases)):
            errors.append(f"Duplicate main phase report in {run['worker']}")
        executed.extend({item["id"] for item in run["reports"]})
    if len(executed) != len(set(executed)) or set(executed) != set(selected):
        errors.append("Executed main cases differ from fresh selection")
    if workers:
        worker_main = Counter(
            (item["id"], item["phase"], item["outcome"]) for run in runners for item in run["reports"]
        )
        controller_main = Counter(
            (item["id"], item["phase"], item["outcome"]) for item in records["main"]["reports"]
        )
        if worker_main != controller_main:
            errors.append("Main report transport differs from worker reports")
        worker_subtests = Counter(
            (
                item["id"],
                item["phase"],
                item["outcome"],
                json.dumps(item["transport_context"], sort_keys=True),
            )
            for run in runners
            for item in run["subtests"]
        )
        controller_subtests = Counter(
            (item["id"], item["phase"], item["outcome"], json.dumps(item["context"], sort_keys=True))
            for item in records["main"]["subtests"]
        )
        if worker_subtests != controller_subtests:
            errors.append("Subtest identity/outcome transport differs from worker reports")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--label", required=True)
    parser.add_argument("--workers", type=int, choices=(0, 2), required=True)
    parser.add_argument("--output", type=Path, default=Path("test-results"))
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", args.label):
        parser.error("label must contain only letters, digits, underscores or hyphens")
    if sys.platform != "linux":
        parser.error("process-family RSS measurement requires Linux /proc")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if list(output.glob(f"{args.label}-*")) or (output / f"{args.label}.xml").exists():
        parser.error("profile output already exists; use a fresh label or directory")
    options = args.pytest_args[1:] if args.pytest_args[:1] == ["--"] else args.pytest_args
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-n",
        str(args.workers),
        "--dist=loadfile",
        "--max-worker-restart=0",
        "-p",
        "ci_pytest_inventory",
        *options,
        f"--junitxml={output / (args.label + '.xml')}",
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, (str(HERE.parent), env.get("PYTHONPATH"))))
    env["CI_TEST_PROFILE_DIR"] = str(output)
    env["CI_TEST_PROFILE_LABEL"] = args.label
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()
    inputs = subprocess.check_output(["git", "ls-tree", "-r", "HEAD", "--", *SOURCE_PATHS], cwd=ROOT)
    source_before = _source_state()
    versions = {name: importlib.metadata.version(name) for name in ("pytest", "pytest-xdist", "execnet")}
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    own_before = resource.getrusage(resource.RUSAGE_SELF)
    started = time.perf_counter()
    peak_rss = peak_processes = samples = 0
    next_update = started + 55
    process = subprocess.Popen(command, cwd=ROOT, env=env, start_new_session=True)
    try:
        while True:
            rss, count = _rss_tree()
            peak_rss = max(peak_rss, rss)
            peak_processes = max(peak_processes, count)
            samples += 1
            status = process.poll()
            if status is not None:
                break
            now = time.perf_counter()
            if now >= next_update:
                print(
                    f"\n{args.label}: active {now - started:.0f}s, sampled tree RSS {rss / 2**20:.1f} MiB",
                    flush=True,
                )
                next_update = now + 55
            time.sleep(0.2)
    except BaseException:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            except ProcessLookupError:
                process.wait()
        raise
    elapsed = time.perf_counter() - started
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    own_after = resource.getrusage(resource.RUSAGE_SELF)
    errors = _inventory_errors(output, args.label, args.workers)
    if elapsed > 1 and peak_processes < 2:
        errors.append("No pytest descendant was observed; aggregate RSS is invalid")
    source_after = _source_state()
    result = {
        "schema_version": "ci-pytest-profile-v1",
        "label": args.label,
        "workers": args.workers,
        "revision": revision,
        "tree": tree,
        "source_input_tree_sha256": hashlib.sha256(inputs).hexdigest(),
        "source_inputs_before": source_before,
        "source_inputs_after": source_after,
        "command": command,
        "cwd": str(ROOT),
        "python": sys.version,
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "versions": versions,
        "pytest_exit_code": status,
        "inventory_errors": errors,
        "exit_code": status if status else int(bool(errors)),
        "elapsed_seconds": elapsed,
        "child_user_seconds": after.ru_utime - before.ru_utime,
        "child_system_seconds": after.ru_stime - before.ru_stime,
        "sampler_user_seconds": own_after.ru_utime - own_before.ru_utime,
        "sampler_system_seconds": own_after.ru_stime - own_before.ru_stime,
        "largest_child_max_rss_kib": after.ru_maxrss,
        "sampled_aggregate_rss_bytes": peak_rss,
        "peak_process_count": peak_processes,
        "sampling_interval_seconds": 0.2,
        "samples": samples,
        "rss_note": "Sampled sum of profiler/descendant RSS; shared pages may count more than once. Separate kernel metric is largest child, not aggregate.",
        "pin_fingerprints": {
            name: hashlib.sha256(env.get(name, "").encode()).hexdigest() for name in PIN_NAMES
        },
        "tool_inputs_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (
                ROOT / "uv.lock",
                ROOT / "pyproject.toml",
                ROOT / ".github/ci-test-tools.txt",
                HERE,
                HERE.with_name("ci_pytest_inventory.py"),
            )
        },
    }
    (output / f"{args.label}-metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        f"\n{args.label}: pytest exit={status}; inventory errors={errors}; process={elapsed:.2f}s", flush=True
    )
    return status if status else int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
