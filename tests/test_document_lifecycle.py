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
