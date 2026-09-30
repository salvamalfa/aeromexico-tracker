"""src.publish.verify against tests/fixtures/site/ — CI-runnable, no
private data (see tests/fixtures/site/_generate.py to regenerate).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.publish.verify import _data_schema_for, verify_site
from src.web_export.schemas import NETWORK_FILE_SCHEMA

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "site"


def test_valid_site_has_no_problems() -> None:
    assert verify_site(FIXTURES / "valid") == []


@pytest.mark.parametrize(
    "name,expected_substring",
    [
        ("altered_byte", "SHA-256 on disk"),
        ("extra_file", "unlisted file present on disk"),
        ("missing_file", "which is missing on disk"),
        ("disallowed_carrier", "disallowed carrier_key"),
        ("undeclared_field", "Additional properties are not allowed"),
        ("malformed_approval", "approval_event' is missing or not a non-empty string"),
    ],
)
def test_negative_fixture_is_rejected(name: str, expected_substring: str) -> None:
    problems = verify_site(FIXTURES / name)
    assert problems, f"{name} was accepted; expected it to be rejected"
    assert any(expected_substring in p for p in problems), problems


def test_missing_manifest_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html></html>")
    problems = verify_site(tmp_path)
    assert problems and "is missing" in problems[0]


def test_cli_exits_nonzero_on_a_failing_site(capsys: pytest.CaptureFixture[str]) -> None:
    from src.publish.verify import main

    code = main([str(FIXTURES / "altered_byte")])
    assert code == 1
    captured = capsys.readouterr()
    assert "failed" in captured.err


def test_cli_exits_zero_on_the_valid_fixture(capsys: pytest.CaptureFixture[str]) -> None:
    from src.publish.verify import main

    code = main([str(FIXTURES / "valid")])
    assert code == 0


@pytest.mark.parametrize(
    "rel_path",
    [
        "data/v1/flights/entities/VOLARIS/international/2026Q2.json",
        "data/v1/flights/entities/INDUSTRY/domestic/2026M06.json",
        "data/v1/flights/entities/VIVA_AEROBUS/domestic/2026M04.json",
    ],
)
def test_entity_network_files_are_declared(rel_path: str) -> None:
    assert _data_schema_for(rel_path) is NETWORK_FILE_SCHEMA


@pytest.mark.parametrize(
    "rel_path",
    [
        "data/v1/flights/entities/DELTA/international/2026Q2.json",
        "data/v1/flights/entities/VOLARIS/monthly/2026M06.json",
        "data/v1/flights/entities/VOLARIS/2026Q2.json",
        "data/v1/flights/entities/VOLARIS/domestic/extra/2026M06.json",
    ],
)
def test_unknown_entity_paths_stay_undeclared(rel_path: str) -> None:
    assert _data_schema_for(rel_path) is None
