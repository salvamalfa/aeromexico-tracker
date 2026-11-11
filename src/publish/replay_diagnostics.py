"""Private evidence retention for failed disposable AFAC producer replays."""

from __future__ import annotations

import hashlib
import json
import stat
import tempfile
from pathlib import Path


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _retain_afac_replay_diagnostics(repo, checkout, commit, returncode, stdout, stderr) -> str:
    """Keep failed subprocess evidence outside its disposable producer checkout."""
    repo, checkout = Path(repo).resolve(), Path(checkout).resolve()
    source = checkout / "tmp/approval-replay-diagnostics"
    destination = repo / "tmp/approval-replay-diagnostics"

    def linked(path):
        return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())

    def checked_parents(path, root):
        if not path.is_relative_to(root):
            raise ValueError("Replay diagnostic path leaves its workspace")
        while path != root:
            if linked(path):
                raise ValueError("Replay diagnostic path traverses a symlink or junction")
            path = path.parent

    def raw(value):
        return value if isinstance(value, bytes) else (value or "").encode("utf-8")

    # Validate and read the complete source inventory before creating any output.
    # In particular, never follow a nested diagnostic link outside the producer.
    payloads = {"producer.stdout.txt": raw(stdout), "producer.stderr.txt": raw(stderr)}
    checked_parents(source, checkout)
    if source.exists():
        if not source.is_dir():
            raise ValueError("Replay diagnostic source is not a directory")
        for path in sorted(source.rglob("*")):
            checked_parents(path, checkout)
            if path.is_dir():
                continue
            if not stat.S_ISREG(path.lstat().st_mode):
                raise ValueError("Replay diagnostic input is not a regular file")
            payloads["nested/" + path.relative_to(source).as_posix()] = path.read_bytes()
    checked_parents(destination, repo)
    destination.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="afac-replay-", dir=destination))
    entries = []
    for name, content in sorted(payloads.items()):
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        entries.append({"path": name, "bytes": len(content), "sha256": _sha(content)})
    report = folder / "manifest.json"
    report.write_text(
        json.dumps(
            {
                "schema_version": "afac_replay_diagnostics_v1",
                "producer_commit": commit,
                "returncode": returncode,
                "failure_kind": (
                    "timeout" if returncode == "timeout" else
                    "invalid_result" if returncode == 0 else "nonzero_exit"
                ),
                "files": entries,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )
    return report.relative_to(repo).as_posix()


def _afac_replay_diagnostic_note(repo, checkout, commit, returncode, stdout, stderr) -> str:
    try:
        path = _retain_afac_replay_diagnostics(repo, checkout, commit, returncode, stdout, stderr)
    except (OSError, ValueError) as error:
        # Retention can fail, but can never turn the producer's refusal into success.
        return f"private diagnostic retention failed: {error}"
    return f"private diagnostics={path}"
