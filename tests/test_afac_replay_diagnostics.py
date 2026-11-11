from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

import pytest

from src.publish import afac_history_scope, afac_history_update
from src.publish import presentation_release as release


def _git(repo, *arguments):
    return subprocess.check_output(
        ["git", "-c", "user.name=Replay test", "-c", "user.email=replay-test@example.invalid",
         "-C", str(repo), *arguments], text=True
    ).strip()


def _negative_producer(tmp_path, monkeypatch, mode):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / ".gitignore").write_text("analysis_runs/\ndata/\ntmp/\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    _git(repo, "commit", "-m", "Negative replay fixture")
    commit = _git(repo, "rev-parse", "HEAD")
    for relative in ("analysis_runs", "data/bronze", "tmp/source-updates"):
        (repo / relative).mkdir(parents=True, exist_ok=True)
    request = repo / "tmp/source-updates/request.json"
    request.write_bytes(b"{}")
    fingerprint = "f" * 64

    # Only the producer metadata/program is synthetic. The child subprocess
    # really rejects (or times out), and Git worktree creation/removal are real.
    # No fixture returns an approval, passes a verifier, or intercepts cleanup.
    monkeypatch.setattr(afac_history_scope, "producer_version_at_commit", lambda *_: fingerprint)
    monkeypatch.setattr(afac_history_update, "request_inputs", lambda *_: (request, {}))
    program = """
import sys, time
from pathlib import Path
folder = Path("tmp/approval-replay-diagnostics/parent")
folder.mkdir(parents=True)
(folder / "original.stderr.txt").write_bytes("Original parent: aprobación rechazada\\r\\n".encode("utf-8"))
print("producer output", flush=True)
print("Original parent refused replay", file=sys.stderr, flush=True)
"""
    if mode == "reject":
        program += "sys.exit(23)\n"
    elif mode == "timeout":
        program += "time.sleep(30)\n"
        original_run = subprocess.run

        def short_timeout(command, **kwargs):
            if command[0] == sys.executable and "-c" in command:
                kwargs["timeout"] = 0.8
            return original_run(command, **kwargs)

        monkeypatch.setattr(release.subprocess, "run", short_timeout)
    monkeypatch.setattr(release, "_AFAC_REPLAY_PROGRAM", program)
    profile = {
        "afac_producer_commit": commit,
        "afac_request": {
            "path": request.relative_to(repo).as_posix(),
            "sha256": hashlib.sha256(request.read_bytes()).hexdigest(),
        },
    }
    return repo, profile, {"scope": {"producer_code_version": fingerprint}}


@pytest.mark.parametrize("mode", ["reject", "malformed", "timeout"])
def test_failed_producer_evidence_survives_real_worktree_cleanup(tmp_path, monkeypatch, mode):
    repo, profile, anchor = _negative_producer(tmp_path, monkeypatch, mode)
    error_type = subprocess.TimeoutExpired if mode == "timeout" else ValueError
    with pytest.raises(error_type) as raised:
        release.replay_afac_sources(repo, profile, anchor)
    if mode == "reject":
        assert "Pinned AFAC producer replay failed" in str(raised.value)
        assert "Original parent refused replay" in str(raised.value)
    elif mode == "malformed":
        assert "no machine-readable result" in str(raised.value)
    else:
        assert any("private diagnostics=" in note for note in raised.value.__notes__)
    assert _git(repo, "worktree", "list", "--porcelain").count("worktree ") == 1

    reports = list((repo / "tmp/approval-replay-diagnostics").glob("afac-replay-*/manifest.json"))
    assert len(reports) == 1
    report = json.loads(reports[0].read_bytes())
    assert report["producer_commit"] == profile["afac_producer_commit"]
    assert report["returncode"] == {"reject": 23, "malformed": 0, "timeout": "timeout"}[mode]
    assert report["failure_kind"] == {
        "reject": "nonzero_exit", "malformed": "invalid_result", "timeout": "timeout"
    }[mode]
    expected = {
        "producer.stdout.txt": b"producer output\n",
        "producer.stderr.txt": b"Original parent refused replay\n",
        "nested/parent/original.stderr.txt": "Original parent: aprobación rechazada\r\n".encode(),
    }
    assert {entry["path"] for entry in report["files"]} == set(expected)
    for entry in report["files"]:
        content = (reports[0].parent / entry["path"]).read_bytes()
        assert content == expected[entry["path"]]
        assert entry["bytes"] == len(content)
        assert entry["sha256"] == hashlib.sha256(content).hexdigest()
    assert _git(repo, "ls-files", "--", "tmp/approval-replay-diagnostics") == ""


@pytest.mark.parametrize("link_location", ["source", "destination"])
def test_retention_refuses_linked_paths_without_copying_external_files(tmp_path, link_location):
    repo, checkout, external = (tmp_path / name for name in ("repo", "producer", "external"))
    for path in (repo, checkout, external):
        path.mkdir()
    (external / "outside.stderr.txt").write_bytes(b"outside the replay workspace")
    source = checkout / "tmp/approval-replay-diagnostics"
    source.mkdir(parents=True)
    if link_location == "source":
        link = source / "linked"
    else:
        (repo / "tmp").mkdir()
        link = repo / "tmp/approval-replay-diagnostics"
    try:
        os.symlink(external, link, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"Symlink privilege unavailable: {error}")
    note = release._afac_replay_diagnostic_note(
        repo, checkout, "f" * 40, 23, "original stdout", "original stderr"
    )
    assert "retention failed" in note
    assert "symlink or junction" in note
    assert sorted(path.name for path in external.iterdir()) == ["outside.stderr.txt"]
    if link_location == "source":
        assert not (repo / "tmp/approval-replay-diagnostics").exists()

