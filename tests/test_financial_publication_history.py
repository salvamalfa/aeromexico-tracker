"""Adversarial public-history profile contracts; these fixtures approve no data."""

import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from tests import _financial_publication_history as history
from tests import conftest

BASE, CODE, HEAD = "a" * 40, "b" * 40, "c" * 40
RUNTIME = "d" * 64
REFERENCE = "data/reference/official_route_cities.csv"


def test_official_route_fingerprint_inputs_are_covered_by_the_historical_archive():
    from src.source_updates.official_routes import CODE_FILES

    missing = [
        name for name in CODE_FILES
        if not any(name == prefix or name.startswith(prefix.rstrip("/") + "/") for prefix in history.RUNTIME)
    ]
    assert not missing, f"Published map fingerprint inputs missing from the archive: {missing}"


@pytest.fixture(params=list(history.PROFILES))
def context(tmp_path, monkeypatch, request):
    module = request.param
    selected_anchor = history.PROFILES[module][0]
    repo, site = tmp_path, tmp_path / "site"
    site.mkdir()
    (site / "payload.json").write_text('{"value":1}')
    manifest = json.dumps({"code_commit": CODE}).encode()
    (site / "publication_manifest.json").write_bytes(manifest)
    anchor = json.dumps({"producer_code_version": RUNTIME}).encode()
    authority = {
        selected_anchor: anchor,
        "config/publish/revocations.json": b"{}",
        module.replace(".", "/") + ".py": b"# published strong verifier\n",
        "contracts/web/manifest.schema.json": b"{}",
        "scripts/check_pages_publication.py": b"# published selector\n",
    }
    program = {
        **authority,
        "uv.lock": b"locked",
        "pyproject.toml": b"project",
        "src/__init__.py": b"",
        "web/package.json": b'{"devDependencies":{"@types/plotly.js":"old"}}',
        "web/package-lock.json": b'{"locked":"old"}',
        REFERENCE: b"city,country\nMEX,MX\n",
    }
    for name, raw in program.items():
        path = repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    expected = history.files.site_files(site)
    state = {
        "authority": deepcopy(authority),
        "program": program,
        "module": module,
        "anchor": selected_anchor,
    }

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
            return {
                name: raw for name, raw in program.items()
                if any(name == prefix or name.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)
            }
        if prefixes == [selected_anchor, "site/publication_manifest.json"]:
            return {selected_anchor: anchor, "site/publication_manifest.json": manifest}
        return authority if commit == BASE else state["authority"]

    monkeypatch.setattr(history.files, "ancestor", ancestor)
    monkeypatch.setattr(history.files.transport, "_git", git)
    monkeypatch.setattr(history.files, "git_files", git_files)
    monkeypatch.setattr(history.files, "tree_files", lambda *args: expected)
    monkeypatch.setattr(history.files, "committed", lambda root, name: (root / name).read_bytes())
    return repo, site, state


@pytest.mark.parametrize("base", ["master", "f" * 40, BASE, True])
def test_history_requires_a_full_trusted_base_before_running_any_code(context, monkeypatch, base):
    repo, site, state = context
    if base == BASE:

        def unprotected(root, *args):
            if args == ("rev-parse", "HEAD"):
                return HEAD.encode()
            raise ValueError("BASE is not in the protected branch")

        monkeypatch.setattr(history.files.transport, "_git", unprotected)
    monkeypatch.setattr(history.subprocess, "run", lambda *a, **k: pytest.fail("Untrusted code ran"))
    assert history.verify_published(site, repo, base_commit=base, module=state["module"])


@pytest.mark.parametrize(
    "change",
    [
        "bytes",
        "extra",
        "symlink",
        "anchor",
        "revocation",
        "untracked_authority",
        "lock",
        "code_commit",
        "contract",
        "missing_producer",
        "missing_producer_anchor",
        "selector",
        "missing_producer_selector",
    ],
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
        (repo / state["anchor"]).write_text("{}")
    elif change == "revocation":
        state["authority"]["config/publish/revocations.json"] = b'{"revoked":true}'
        (repo / "config/publish/revocations.json").write_bytes(
            state["authority"]["config/publish/revocations.json"]
        )
    elif change == "untracked_authority":
        (repo / "config/publish/new-revocations.json").write_text('{"revoked":true}')
    elif change == "lock":
        (repo / "uv.lock").write_text("different dependencies")
    elif change == "contract":
        (repo / "contracts/web/manifest.schema.json").write_text('{"changed":true}')
    elif change == "missing_producer":
        state["program"].pop(state["module"].replace(".", "/") + ".py")
    elif change == "missing_producer_anchor":
        state["program"].pop(state["anchor"])
    elif change == "selector":
        (repo / "scripts/check_pages_publication.py").write_text("# changed selector\n")
    elif change == "missing_producer_selector":
        state["program"].pop("scripts/check_pages_publication.py")
    else:
        original = history.files.ancestor

        def reject_unpublished_code(root, before, after):
            if before == CODE:
                raise ValueError("Manifest code is not an ancestor of the trusted base")
            return original(root, before, after)

        monkeypatch.setattr(history.files, "ancestor", reject_unpublished_code)
    monkeypatch.setattr(history.subprocess, "run", lambda *a, **k: pytest.fail("Untrusted code ran"))
    assert history.verify_published(site, repo, base_commit=BASE, module=state["module"])


@pytest.mark.parametrize("failure", ["exit", "runtime", "verdict", "archive_changed", "reference_changed", "site_changed"])
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
        if failure == "reference_changed":
            (archive / REFERENCE).write_text("mutated")
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
    assert history.verify_published(site, repo, base_commit=BASE, module=state["module"])
    assert len(calls) == 1


def test_frontend_dependency_change_uses_only_pinned_published_producer(context, monkeypatch):
    repo, site, state = context
    # This is outside the publication authority: the candidate is type-checked
    # independently, while these exact BASE site bytes retain their old producer.
    (repo / "web/package.json").write_text('{"devDependencies":{"@types/plotly.js":"new"}}')
    (repo / "web/package-lock.json").write_text('{"lockfileVersion":3}')
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert command[-2:] == [state["module"], history.PROFILES[state["module"]][1]]
        assert kwargs["timeout"] == (600 if state["module"] == "src.publish.source_data_scope" else 120)
        assert all((kwargs["cwd"] / k).read_bytes() == v for k, v in state["program"].items())
        assert (kwargs["cwd"] / "web/package.json").read_bytes() == state["program"]["web/package.json"]
        return SimpleNamespace(returncode=0, stdout=json.dumps({"runtime": RUNTIME, "problems": []}))

    monkeypatch.setattr(history.subprocess, "run", run)
    assert history.verify_published(site, repo, base_commit=BASE, module=state["module"]) == []
    assert len(calls) == 1


def test_candidate_reference_change_does_not_replace_the_published_producer_blob(context, monkeypatch):
    repo, site, state = context
    expected = state["program"][REFERENCE]
    (repo / REFERENCE).write_text("unreviewed candidate city mapping\n")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert (kwargs["cwd"] / REFERENCE).read_bytes() == expected
        return SimpleNamespace(returncode=0, stdout=json.dumps({"runtime": RUNTIME, "problems": []}))

    monkeypatch.setattr(history.subprocess, "run", run)
    assert history.verify_published(site, repo, base_commit=BASE, module=state["module"]) == []
    assert len(calls) == 1


def test_missing_producer_reference_never_borrows_candidate_bytes_or_falls_back(context, monkeypatch):
    repo, site, state = context
    state["program"].pop(REFERENCE)
    assert (repo / REFERENCE).is_file()
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        (kwargs["cwd"] / REFERENCE).read_bytes()
        pytest.fail("The missing archived reference was replaced")

    monkeypatch.setattr(history.subprocess, "run", run)
    assert history.verify_published(site, repo, base_commit=BASE, module=state["module"])
    assert len(calls) == 1


def test_unknown_historical_profile_cannot_run_code(context, monkeypatch):
    repo, site, _ = context
    monkeypatch.setattr(history.subprocess, "run", lambda *a, **k: pytest.fail("Unknown profile ran"))
    assert history.verify_published(site, repo, base_commit=BASE, module="src.publish.unknown")


def test_candidate_source_runtime_still_requires_its_exact_reviewed_producer(monkeypatch, tmp_path):
    from src.analysis_agent import entity_adapter
    from src.publish import source_data_scope

    monkeypatch.setattr(source_data_scope, "anchor", lambda _: {"producer_code_version": RUNTIME})
    monkeypatch.setattr(entity_adapter, "code_version", lambda: "e" * 64)
    monkeypatch.setattr(
        source_data_scope,
        "verify_historical_baseline",
        lambda *a: pytest.fail("Mismatched runtime continued"),
    )
    assert source_data_scope.verify_source_data(tmp_path, tmp_path) == [
        "Invalid selective source publication: Source runtime differs from its reviewed producer"
    ]


def test_local_and_historical_profiles_are_explicit_and_mutually_exclusive():
    config = SimpleNamespace(getoption=lambda name: True)
    with pytest.raises(pytest.UsageError, match="never both"):
        conftest.pytest_configure(config)


def test_default_verifier_remains_the_current_ordinary_financial_gate():
    from src.publish.financial_scope import verify_financial

    request = SimpleNamespace(config=SimpleNamespace(getoption=lambda name: None))
    assert conftest.verify_financial_publication.__wrapped__(request) is verify_financial
