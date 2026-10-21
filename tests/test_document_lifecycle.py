import json
import subprocess

import pytest

from scripts.check_document_lifecycle import changed_documents, validate_dispositions


def summary(*entries):
    return "<!-- document-lifecycle:v1\n" + json.dumps({"files": entries}) + "\n-->"


def test_doc_change_requires_explicit_disposition_and_reason(tmp_path):
    (tmp_path / "README.md").write_text("Current guide")
    assert validate_dispositions(tmp_path, ["README.md"], "Code change only")
    assert validate_dispositions(
        tmp_path, ["README.md"], summary({"path": "README.md", "disposition": "keep"})
    )
    assert not validate_dispositions(
        tmp_path,
        ["README.md"],
        summary({"path": "README.md", "disposition": "update", "reason": "Describes current behavior"}),
    )


def test_disposition_does_not_hide_a_broken_link(tmp_path):
    (tmp_path / "README.md").write_text("[missing](missing.md)")
    result = validate_dispositions(
        tmp_path,
        ["README.md"],
        summary({"path": "README.md", "disposition": "keep", "reason": "Active guide"}),
    )
    assert any("Broken" in error for error in result)


def test_pending_cleanup_can_be_reported_without_deletion(tmp_path):
    (tmp_path / "history.md").write_text("Retained evidence")
    assert not validate_dispositions(
        tmp_path,
        ["history.md"],
        summary(
            {
                "path": "history.md",
                "disposition": "pending",
                "reason": "Read-only audit; retain approval evidence",
            }
        ),
    )
    assert (tmp_path / "history.md").exists()


def git(root, *args):
    return (
        subprocess.check_output(
            [
                "git",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "core.hooksPath=/dev/null",
                "-c",
                "user.name=Fixture",
                "-c",
                "user.email=fixture@example.invalid",
                *args,
            ],
            cwd=root,
        )
        .decode()
        .strip()
    )


def commit(root):
    git(root, "add", "--all")
    git(root, "commit", "-qm", "Synthetic lifecycle fixture")
    return git(root, "rev-parse", "HEAD")


def retire_fixture(root, consumer, content):
    git(root, "init", "-q")
    (root / "docs").mkdir()
    (root / "docs/retired.md").write_text("Synthetic retired document")
    target = root / consumer
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    baseline = commit(root)
    (root / "docs/retired.md").unlink()
    commit(root)
    return baseline


@pytest.mark.parametrize(
    "consumer,content",
    [
        ("README.md", "[guide](docs/retired.md#section)"),
        ("README.md", '[guide](docs/retired.md "Guide")'),
        ("README.md", '[guide](<docs/retired.md> "Guide")'),
        (
            "README.md",
            "[guide](https://github.com/salvamalfa/aeromexico-tracker/blob/master/docs/retired.md)",
        ),
        ("docs/index.md", "[guide](retired.md)"),
        ("docs/index.md", "[guide][old]\n\n[old]: retired.md"),
        ("tests/test_prompt.py", 'Path("docs/retired.md").read_text()'),
        ("tests/test_prompt.py", 'Path("docs\\\\retired.md").read_text()'),
        ("src/consumer.py", 'Path("../docs/retired.md").read_text()'),
        ("config/prompts.yaml", "prompt_file: docs/retired.md"),
        ("README.md", "See docs/retired.md."),
        ("README.md", "See docs/retired.md-"),
        ("README.md", "See docs/retired.md--"),
        ("README.md", "See docs/retired.md_"),
        ("README.md", "Ver docs/retired.md…"),
        ("docs/index.md", "Ver ../docs/retired.md?!"),
        (
            "README.md",
            "See https://raw.githubusercontent.com/salvamalfa/aeromexico-tracker/master/docs/retired.md.",
        ),
        ("config/prompts.yaml", "prompt_file: ../docs/retired.md"),
        ("scripts/check.sh", "check --input ../docs/retired.md"),
        (
            "README.md",
            "[guide](https://raw.githubusercontent.com/salvamalfa/aeromexico-tracker/master/docs/retired.md)",
        ),
        (
            "config/prompts.yaml",
            "url: https://raw.githubusercontent.com/salvamalfa/aeromexico-tracker/refs/heads/master/docs/retired.md",
        ),
        (
            "README.md",
            "[guide](https://github.com/salvamalfa/aeromexico-tracker/raw/refs/heads/master/docs/retired.md)",
        ),
    ],
)
def test_deleted_doc_checks_unchanged_inbound_consumers(tmp_path, consumer, content):
    baseline = retire_fixture(tmp_path, consumer, content)
    paths = changed_documents(tmp_path, baseline)
    assert paths == ["docs/retired.md"]
    errors = validate_dispositions(
        tmp_path,
        paths,
        summary(
            {
                "path": "docs/retired.md",
                "disposition": "archive",
                "reason": "Synthetic test only",
            }
        ),
    )
    assert any("Inbound" in error and consumer in error for error in errors)


def test_rename_retains_the_old_path_and_requires_link_updates(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/old.md").write_text("Synthetic moved document")
    (tmp_path / "README.md").write_text("[guide](docs/old.md)")
    baseline = commit(tmp_path)
    (tmp_path / "docs/old.md").rename(tmp_path / "docs/current.md")
    commit(tmp_path)
    paths = changed_documents(tmp_path, baseline)
    assert paths == ["docs/current.md", "docs/old.md"]
    disposition = summary(
        {"path": "docs/old.md", "disposition": "archive", "reason": "Synthetic move"},
        {"path": "docs/current.md", "disposition": "keep", "reason": "Current synthetic guide"},
        {"path": "README.md", "disposition": "update", "reason": "Updated link"},
    )
    assert validate_dispositions(tmp_path, paths, disposition)
    (tmp_path / "README.md").write_text("[guide](docs/current.md)")
    commit(tmp_path)
    assert not validate_dispositions(tmp_path, changed_documents(tmp_path, baseline), disposition)


def test_immutable_archive_link_and_other_same_name_doc_remain_valid(tmp_path):
    consumer = (
        "[docs/retired.md](https://github.com/example/repo/blob/" + "a" * 40 + "/docs/retired.md)\n"
        "[current](reference/retired.md)\n[unrelated old debt](other-missing.md)"
        "\n[raw history](https://raw.githubusercontent.com/salvamalfa/aeromexico-tracker/"
        + "a" * 40
        + "/docs/retired.md)"
    )
    baseline = retire_fixture(tmp_path, "README.md", consumer)
    (tmp_path / "reference").mkdir()
    (tmp_path / "reference/retired.md").write_text("Different current guide")
    commit(tmp_path)
    disposition = summary(
        {"path": "docs/retired.md", "disposition": "archive", "reason": "Immutable history link"},
        {"path": "reference/retired.md", "disposition": "keep", "reason": "Different guide"},
    )
    assert not validate_dispositions(tmp_path, changed_documents(tmp_path, baseline), disposition)


def test_pr_diff_excludes_upstream_changes_from_github_merge_checkout(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "README.md").write_text("Synthetic base")
    baseline = commit(tmp_path)
    git(tmp_path, "checkout", "-qb", "upstream")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/upstream.md").write_text("Another task's document")
    upstream = commit(tmp_path)
    git(tmp_path, "checkout", "-qb", "candidate", baseline)
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs/ours.md").write_text("This task's document")
    head = commit(tmp_path)
    git(tmp_path, "merge", "--no-ff", "--no-edit", upstream)
    assert changed_documents(tmp_path, baseline) == ["docs/ours.md", "docs/upstream.md"]
    assert changed_documents(tmp_path, baseline, head) == ["docs/ours.md"]
    assert changed_documents(tmp_path, upstream, head) == ["docs/ours.md"]


def test_dynamic_source_url_does_not_abort_retirement_scan_or_hide_paths(tmp_path):
    baseline = retire_fixture(
        tmp_path,
        "tests/test_server.py",
        'url = f"http://127.0.0.1:{server.server_address[1]}/review.html"\n'
        'Path("docs/retired.md").read_text()\n',
    )
    paths = changed_documents(tmp_path, baseline)
    result = validate_dispositions(
        tmp_path,
        paths,
        summary({"path": "docs/retired.md", "disposition": "archive", "reason": "Replaced guide"}),
    )
    assert any("Inbound reference" in error and "tests/test_server.py" in error for error in result)
    (tmp_path / "tests/test_server.py").write_text(
        'url = f"http://127.0.0.1:{server.server_address[1]}/review.html"\n'
    )
    assert (
        validate_dispositions(
            tmp_path,
            paths,
            summary({"path": "docs/retired.md", "disposition": "archive", "reason": "Replaced guide"}),
        )
        == []
    )


def test_malformed_markdown_url_is_reported_as_a_validation_error(tmp_path):
    (tmp_path / "README.md").write_text("[bad](http://[broken/file.md)")
    result = validate_dispositions(
        tmp_path,
        ["README.md"],
        summary({"path": "README.md", "disposition": "update", "reason": "Updated guide"}),
    )
    assert any("Malformed Markdown target" in error for error in result)


def test_full_inventory_includes_code_data_and_uncommitted_files(tmp_path):
    from scripts.check_document_lifecycle import changed_files

    git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("cache/\n")
    (tmp_path / "old.py").write_text("original")
    baseline = commit(tmp_path)
    (tmp_path / "old.py").unlink()
    (tmp_path / "src").mkdir()
    (tmp_path / "src/new.py").write_text("source")
    git(tmp_path, "add", "src/new.py")
    (tmp_path / "evidence.parquet").write_bytes(b"synthetic evidence")
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache/ignored.json").write_text("{}")
    assert changed_files(tmp_path, baseline) == []
    paths = changed_files(tmp_path, baseline, worktree=True)
    assert paths == ["evidence.parquet", "old.py", "src/new.py"]
    assert validate_dispositions(tmp_path, paths, "No inventory")
    body = summary(
        {"path": "old.py", "disposition": "retire", "reason": "Replaced implementation in Git"},
        {"path": "src/new.py", "disposition": "keep", "reason": "Active replacement"},
    )
    assert any("evidence.parquet" in error for error in validate_dispositions(tmp_path, paths, body))
    body = body.replace(
        "]}", ', {"path":"evidence.parquet","disposition":"keep","reason":"Required evidence"}]}'
    )
    assert not validate_dispositions(tmp_path, paths, body)
    commit(tmp_path)
    assert changed_files(tmp_path, baseline) == paths
    with pytest.raises(ValueError, match="requires"):
        changed_files(tmp_path, baseline, baseline, worktree=True)


def test_artifact_groups_are_bounded_counted_and_do_not_replace_source_entries(tmp_path):
    paths = ["site/data/v1/a.json", "site/data/v1/b.json"]
    for name in paths:
        file = tmp_path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("{}")
    row = {"prefix": "site/data/v1/", "count": 2, "disposition": "keep", "reason": "Signed public data"}
    assert not validate_dispositions(tmp_path, paths, summary(row))
    assert validate_dispositions(tmp_path, paths, summary({**row, "count": 1}))
    assert validate_dispositions(tmp_path, paths, summary(row, {**row, "prefix": "site/"}))
    assert validate_dispositions(tmp_path, paths, summary({**row, "prefix": "site/data/v1"}))
    assert validate_dispositions(tmp_path, paths, summary({**row, "prefix": "src/"}))
    assert validate_dispositions(tmp_path, paths, summary({**row, "prefix": "site/../"}))
    file = tmp_path / "site/data/v1/README.md"
    file.write_text("Canonical guide")
    assert validate_dispositions(tmp_path, paths + ["site/data/v1/README.md"], summary({**row, "count": 3}))
    assert validate_dispositions(tmp_path, paths, summary(row) + summary(row))
    assert validate_dispositions(tmp_path, paths, summary({**row, "reason": None}))


def test_private_repository_identity_catches_mutable_links_and_retired_consumers(tmp_path):
    from scripts.check_document_lifecycle import repository_name

    baseline = retire_fixture(
        tmp_path,
        "README.md",
        "[old](https://github.com/salvamalfa/aeromexico-tracker-data/blob/master/docs/retired.md)",
    )
    git(tmp_path, "remote", "add", "origin", "git@github.com:salvamalfa/aeromexico-tracker-data.git")
    assert repository_name(tmp_path) == "salvamalfa/aeromexico-tracker-data"
    body = summary(
        {"path": "docs/retired.md", "disposition": "archive", "reason": "Stored in fixed Git commit"},
        {"path": "README.md", "disposition": "update", "reason": "Canonical index"},
    )
    errors = validate_dispositions(tmp_path, ["docs/retired.md", "README.md"], body)
    assert any("Broken/outside" in error for error in errors)
    assert any("Inbound" in error for error in errors)
    (tmp_path / "README.md").write_text(
        f"[history](https://github.com/salvamalfa/aeromexico-tracker-data/blob/{baseline}/docs/retired.md)"
    )
    assert not validate_dispositions(tmp_path, ["docs/retired.md", "README.md"], body)
    assert validate_dispositions(
        tmp_path,
        ["docs/retired.md"],
        summary({"path": "docs/retired.md", "disposition": "delete_candidate", "reason": "Needs review"}),
    )


@pytest.mark.parametrize(
    "name", ["source.py", "source.ts", "source.js", "workflow.yml", "guide.md", "analysis.ipynb"]
)
def test_evidence_groups_cannot_swallow_source_or_canonical_guides(tmp_path, name):
    path = "review/batch/" + name
    file = tmp_path / path
    file.parent.mkdir(parents=True)
    file.write_text("Synthetic source")
    assert validate_dispositions(
        tmp_path,
        [path],
        summary({"prefix": "review/batch/", "count": 1, "disposition": "keep", "reason": "Evidence"}),
    )


def test_worktree_retirement_checks_new_untracked_code_consumers(tmp_path):
    from scripts.check_document_lifecycle import changed_files

    git(tmp_path, "init", "-q")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/retired.md").write_text("Original")
    baseline = commit(tmp_path)
    (tmp_path / "docs/retired.md").unlink()
    (tmp_path / "src").mkdir()
    (tmp_path / "src/new.py").write_text('Path("docs/retired.md").read_text()')
    paths = changed_files(tmp_path, baseline, worktree=True)
    errors = validate_dispositions(
        tmp_path,
        paths,
        summary(
            {"path": "docs/retired.md", "disposition": "archive", "reason": "Fixed original retained"},
            {"path": "src/new.py", "disposition": "keep", "reason": "New consumer"},
        ),
    )
    assert any("Inbound" in error and "src/new.py" in error for error in errors)


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/salvamalfa/aeromexico-tracker-data.git",
        "git@github.com:salvamalfa/aeromexico-tracker-data.git",
        "ssh://git@github.com/salvamalfa/aeromexico-tracker-data.git",
        "ssh://git@ssh.github.com:443/salvamalfa/aeromexico-tracker-data.git",
    ],
)
def test_private_repository_identity_supports_clone_url_formats(tmp_path, monkeypatch, remote):
    from scripts.check_document_lifecycle import repository_name

    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    git(tmp_path, "init", "-q")
    git(tmp_path, "remote", "add", "origin", remote)
    assert repository_name(tmp_path) == "salvamalfa/aeromexico-tracker-data"


@pytest.mark.parametrize(
    "retired,consumer",
    [
        ("map-old.json", '<a href="map%2Dold.json">map</a>'),
        ("a_(b).md", r"[old](a_\(b\).md)"),
    ],
)
def test_retirement_skips_unrelated_data_and_checks_encoded_consumer(
    tmp_path, monkeypatch, retired, consumer
):
    from pathlib import Path

    from scripts.check_document_lifecycle import inbound_references

    git(tmp_path, "init", "-q")
    (tmp_path / "site").mkdir()
    (tmp_path / "site" / retired).write_text("{}")
    (tmp_path / "site/maps.json").write_text(json.dumps({"rows": ["unrelated/value"] * 10000}))
    (tmp_path / "site/index.html").write_text(consumer)
    commit(tmp_path)
    (tmp_path / "site" / retired).unlink()
    original = Path.resolve
    resolutions = []

    def resolve(path, *args, **kwargs):
        resolutions.append(str(path))
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    errors = inbound_references(tmp_path, ["site/" + retired])
    assert any("site/index.html" in error for error in errors)
    assert len(resolutions) < 50  # Work scales with candidate paths, not unrelated rows.
