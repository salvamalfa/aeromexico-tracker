import json

import pytest

from scripts.check_document_lifecycle import markdown_targets, markdown_url, validate_dispositions


@pytest.mark.parametrize(
    "target",
    [
        "docs/a_(b).md",
        "docs/a_(b_(c)).md",
        "<docs/a_(b).md>",
        r"docs/a_\(b\).md",
        'docs/a_(b).md "A title (with parentheses)"',
    ],
)
def test_valid_balanced_parentheses_targets_are_resolved_and_missing_files_still_fail(tmp_path, target):
    url = markdown_url(target)
    path = tmp_path / url.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Synthetic reference")
    (tmp_path / "README.md").write_text(f"[reference]({target})")
    body = (
        "<!-- document-lifecycle:v1\n"
        + json.dumps(
            {"files": [{"path": "README.md", "disposition": "update", "reason": "Synthetic fixture"}]}
        )
        + "\n-->"
    )
    assert markdown_targets(f"[reference]({target})") == [target]
    assert validate_dispositions(tmp_path, ["README.md"], body) == []
    path.unlink()
    assert any("Broken/outside" in error for error in validate_dispositions(tmp_path, ["README.md"], body))
