"""Editorial data guards without consulting providers or approval ledgers."""

from __future__ import annotations

import json
from copy import deepcopy

import pytest
from jsonschema import ValidationError

from scripts.monthly.build_preview import build
from scripts.monthly.validate import ISSUES, validate_all, validate_issue


def test_pilot_is_public_draft_with_the_three_companies():
    issue, = validate_all()
    assert issue["status"] == "borrador"
    assert issue["id"] == "2026-09"
    assert {row["airline"] for row in issue["traffic"]} == {"Aeroméxico", "Viva", "Volaris"}


@pytest.mark.parametrize("fault", ["future", "source", "citation", "duplicate", "zero_coercion", "private"])
def test_editorial_validation_rejects_broken_provenance(tmp_path, fault):
    issue = deepcopy(validate_issue(ISSUES / "2026-09.json"))
    if fault == "future":
        issue["sources"][0]["published"] = "2026-10-20"
    elif fault == "source":
        issue["traffic"][0]["source"] = "unknown"
    elif fault == "citation":
        issue["sections"][0]["stories"][0]["claims"][0]["sources"] = []
    elif fault == "duplicate":
        issue["traffic"][0] = issue["traffic"][1]
    elif fault == "zero_coercion":
        issue["traffic"][0]["passengers_thousands"] = ""
    else:
        issue["sources"][0]["url"] = "https://internal.invalid/private"
    path = tmp_path / "issue.json"
    path.write_text(json.dumps(issue))
    with pytest.raises((ValueError, ValidationError)):
        validate_issue(path)


def test_preview_builder_cannot_replace_site_or_input():
    from scripts.monthly.validate import ROOT

    for path in [ROOT / "site/monthly.html", ROOT / "web/monthly.html"]:
        with pytest.raises(ValueError, match="vista previa"):
            build(path)
