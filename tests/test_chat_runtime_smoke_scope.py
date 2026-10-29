"""The synthetic smoke cannot silently replace the published trust check."""

import asyncio
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import check_chat_runtime as smoke

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("fixture_only", [False, True])
def test_snapshot_selection_is_explicit_and_failure_does_not_fallback(monkeypatch, fixture_only):
    calls = []
    monkeypatch.setattr(smoke, "_preflight_missing_approval_pin", lambda _path: None)

    def refuse(path):
        calls.append(path)
        raise ValueError("snapshot rejected")

    monkeypatch.setattr(smoke, "Snapshot", refuse)
    with pytest.raises(ValueError, match="snapshot rejected"):
        asyncio.run(smoke._check(fixture_only=fixture_only))
    assert calls == [ROOT / ("tests/fixtures/chat/site" if fixture_only else "site")]


@pytest.mark.parametrize("fixture_only", [False, True])
def test_cli_scope_is_reported_only_after_success(monkeypatch, capsys, fixture_only):
    calls = []

    async def checked(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(smoke, "_check", checked)
    smoke.main(["--fixture-only"] if fixture_only else [])
    assert calls == [{"fixture_only": fixture_only}]
    output = capsys.readouterr().out
    assert ("published snapshot NOT checked" in output) == fixture_only


def test_unrecognized_mode_cannot_run_any_smoke(monkeypatch):
    async def unexpected(**kwargs):
        raise AssertionError("must not run")

    monkeypatch.setattr(smoke, "_check", unexpected)
    with pytest.raises(SystemExit) as error:
        smoke.main(["--skip-approval"])
    assert error.value.code == 2


def test_real_cli_still_rejects_missing_pin_while_fixture_runs_without_network():
    env = dict(os.environ)
    env.pop("CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256", None)
    env.pop("CHAT_EVIDENCE_APPROVED_INDEX_SHA256", None)
    script = """import runpy,socket,sys
def refuse(*args,**kwargs):
    raise AssertionError('network is forbidden in runtime smoke')
socket.create_connection=refuse
socket.socket.connect=refuse
sys.argv=['scripts.check_chat_runtime',*sys.argv[1:]]
runpy.run_module('scripts.check_chat_runtime',run_name='__main__')
"""
    original = (ROOT / "site/publication_manifest.json").read_bytes()
    for args, success in [([], False), (["--fixture-only"], True)]:
        result = subprocess.run(
            [sys.executable, "-c", script, *args],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=90,
        )
        assert (result.returncode == 0) == success, result.stdout + result.stderr
        if success:
            assert "fixture-only; published snapshot NOT checked" in result.stdout
            assert "auth, worker, compare_metrics; no provider calls" in result.stdout
        else:
            assert "must pin the approved receipt SHA-256" in result.stderr
            assert "chat runtime smoke: ok" not in result.stdout
    assert (ROOT / "site/publication_manifest.json").read_bytes() == original


@pytest.mark.parametrize("pin", [None, " \t "])
def test_missing_financial_pin_rejects_before_snapshot_construction(monkeypatch, pin):
    name = "CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256"
    if pin is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, pin)

    def unexpected(_path):
        raise AssertionError("missing configuration must reject before reader construction")

    monkeypatch.setattr(smoke, "Snapshot", unexpected)
    with pytest.raises(ValueError, match="must pin the approved receipt SHA-256"):
        asyncio.run(smoke._check())


def test_nonblank_pin_still_requires_the_complete_snapshot(monkeypatch):
    monkeypatch.setenv("CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256", "not-an-approval")
    calls = []

    def refuse(path):
        calls.append(path)
        raise ValueError("snapshot rejected")

    monkeypatch.setattr(smoke, "Snapshot", refuse)
    with pytest.raises(ValueError, match="snapshot rejected"):
        asyncio.run(smoke._check())
    assert calls == [ROOT / "site"]


def test_fixture_mode_does_not_preflight_the_published_receipt(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke, "ROOT", tmp_path)
    monkeypatch.delenv("CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256", raising=False)
    receipt = tmp_path / "site/data/v1/business_metrics.approval.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("invalid published receipt", encoding="utf-8")
    calls = []

    def refuse(path):
        calls.append(path)
        raise ValueError("fixture snapshot rejected")

    monkeypatch.setattr(smoke, "Snapshot", refuse)
    with pytest.raises(ValueError, match="fixture snapshot rejected"):
        asyncio.run(smoke._check(fixture_only=True))
    assert calls == [tmp_path / "tests/fixtures/chat/site"]


def test_preflight_leaves_paths_outside_the_snapshot_to_its_verifier(monkeypatch, tmp_path):
    monkeypatch.delenv("CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256", raising=False)
    root = tmp_path / "site"
    root.mkdir()
    receipt = root / "data/v1/business_metrics.approval.json"
    outside = tmp_path / "outside.json"
    outside.write_text("must not read", encoding="utf-8")
    resolve = Path.resolve

    def resolved(path, *args, **kwargs):
        return outside if path == receipt else resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolved)
    # Reading the outside file would fail JSON parsing, so this must return.
    smoke._preflight_missing_approval_pin(root)
