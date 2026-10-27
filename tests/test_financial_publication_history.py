"""Adversarial public-history profile contracts; these fixtures approve no data."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from tests import _financial_publication_history as history
from tests import conftest

BASE, CODE, HEAD = "a" * 40, "b" * 40, "c" * 40
RUNTIME = "d" * 64


@pytest.fixture
def context(tmp_path, monkeypatch):
    repo, site = tmp_path, tmp_path / "site"
    site.mkdir()
    (site / "payload.json").write_text('{"value":1}')
    manifest = json.dumps({"code_commit": CODE}).encode()
    (site / "publication_manifest.json").write_bytes(manifest)
    anchor = json.dumps({"producer_code_version": RUNTIME}).encode()
    authority = {history.ANCHOR: anchor, "config/publish/revocations.json": b"{}"}
    program = {**authority, "uv.lock": b"locked", "pyproject.toml": b"project", "src/__init__.py": b""}
    for name, raw in program.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    expected = history.files.site_files(site)
    state = {"authority": deepcopy(authority), "program": program}

    def ancestor(root, before, after):
        if (before, after) not in {(BASE, HEAD), (CODE, BASE)}:
            raise ValueError("Untrusted commit ancestry")

    def git(root, *args):
        if args == ("rev-parse", "HEAD"):
            return HEAD.encode()
        assert args == ("merge-base", "--is-ancestor", BASE, "refs/remotes/origin/master")
        return b""

    def git_files(root, commit, prefixes):
        if commit == CODE:
            return program
        if prefixes == [history.ANCHOR, "site/publication_manifest.json"]:
            return {history.ANCHOR: anchor, "site/publication_manifest.json": manifest}
        return authority if commit == BASE else state["authority"]

    monkeypatch.setattr(history.files, "ancestor", ancestor)
    monkeypatch.setattr(history.files.transport, "_git", git)
    monkeypatch.setattr(history.files, "git_files", git_files)
    monkeypatch.setattr(history.files, "tree_files", lambda *args: expected)
    monkeypatch.setattr(history.files, "committed", lambda root, name: (root / name).read_bytes())
    return repo, site, state


@pytest.mark.parametrize("base", ["master", "f" * 40, BASE])
def test_history_requires_a_full_trusted_base_before_running_any_code(context, monkeypatch, base):
    repo, site, _ = context
    if base == BASE:

        def unprotected(root, *args):
            if args == ("rev-parse", "HEAD"):
                return HEAD.encode()
            raise ValueError("BASE is not in the protected branch")

        monkeypatch.setattr(history.files.transport, "_git", unprotected)
    monkeypatch.setattr(history.subprocess, "run", lambda *a, **k: pytest.fail("Untrusted code ran"))
    assert history.verify_published(site, repo, base_commit=base)


@pytest.mark.parametrize(
    "change",
    ["bytes", "extra", "symlink", "anchor", "revocation", "untracked_authority", "lock", "code_commit"],
)
def test_changed_public_inputs_block_before_archived_verification(context, monkeypatch, change):
    repo, site, state = context
    if change == "bytes":
        (site / "payload.json").write_text('{"value":2}')
    elif change == "extra":
        (site / "unlisted.json").write_text("{}")
    elif change == "symlink":
        (site / "alias.json").symlink_to(site / "payload.json")
    elif change == "anchor":
        (repo / history.ANCHOR).write_text("{}")
    elif change == "revocation":
        state["authority"]["config/publish/revocations.json"] = b'{"revoked":true}'
        (repo / "config/publish/revocations.json").write_bytes(
            state["authority"]["config/publish/revocations.json"]
        )
    elif change == "untracked_authority":
        (repo / "config/publish/new-revocations.json").write_text('{"revoked":true}')
    elif change == "lock":
        (repo / "uv.lock").write_text("different dependencies")
    else:
        original = history.files.ancestor

        def reject_unpublished_code(root, before, after):
            if before == CODE:
                raise ValueError("Manifest code is not an ancestor of the trusted base")
            return original(root, before, after)

        monkeypatch.setattr(history.files, "ancestor", reject_unpublished_code)
    monkeypatch.setattr(history.subprocess, "run", lambda *a, **k: pytest.fail("Untrusted code ran"))
    assert history.verify_published(site, repo, base_commit=BASE)


@pytest.mark.parametrize("failure", ["exit", "runtime", "verdict", "archive_changed", "site_changed"])
def test_verifier_failure_or_mutation_never_falls_back(context, monkeypatch, failure):
    repo, site, state = context
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert "PYTHONPATH" not in kwargs["env"] and "PYTHONHOME" not in kwargs["env"]
        archive = kwargs["cwd"]
        assert all((archive / k).read_bytes() == v for k, v in state["program"].items())
        assert str(archive) not in str(repo)
        if failure == "archive_changed":
            (archive / "uv.lock").write_text("mutated")
        if failure == "site_changed":
            (site / "payload.json").write_text("{}")
        return SimpleNamespace(
            returncode=int(failure == "exit"),
            stdout=json.dumps(
                {
                    "runtime": "e" * 64 if failure == "runtime" else RUNTIME,
                    "problems": ["rejected"] if failure == "verdict" else [],
                }
            ),
        )

    monkeypatch.setenv("PYTHONPATH", "/untrusted-head")
    monkeypatch.setenv("PYTHONHOME", "/untrusted-head")
    monkeypatch.setattr(history.subprocess, "run", run)
    assert history.verify_published(site, repo, base_commit=BASE)
    assert len(calls) == 1


def test_local_and_historical_profiles_are_explicit_and_mutually_exclusive():
    config = SimpleNamespace(getoption=lambda name: True)
    with pytest.raises(pytest.UsageError, match="never both"):
        conftest.pytest_configure(config)


def test_default_verifier_remains_the_current_ordinary_financial_gate():
    from src.publish.financial_scope import verify_financial

    request = SimpleNamespace(config=SimpleNamespace(getoption=lambda name: None))
    assert conftest.verify_financial_publication.__wrapped__(request) is verify_financial
