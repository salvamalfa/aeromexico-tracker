import json

from scripts.check_document_lifecycle import validate_dispositions


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
