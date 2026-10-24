"""Public regressions for selecting financial parity by publication mode."""

import importlib.util
import json
from pathlib import Path

import pytest

from src.publish import editorial


def parity_module():
    spec = importlib.util.spec_from_file_location(
        "editorial_parity_mode", Path(__file__).with_name("test_site_parity.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("valid", [True, False])
def test_editorial_financial_parity_requires_verified_baseline_not_quarterly_reading(
    tmp_path, monkeypatch, valid
):
    module = parity_module()
    module.SITE_DIR = tmp_path / "site"
    module.SITE_DIR.mkdir()
    (module.SITE_DIR / editorial.PROOF).write_text("{}")
    baseline = {"records": [{"period_id": "2026Q2"}], "views": {"2026Q2": {}}}
    monkeypatch.setattr(
        editorial, "verify_editorial", lambda site, repo: [] if valid else ["Historical bytes changed"]
    )
    monkeypatch.setattr(editorial, "anchor", lambda repo: {"baseline_commit": "a" * 40})
    calls = []

    def git_read(args, **kwargs):
        calls.append(args)
        assert args == ["git", "show", "a" * 40 + ":site/data/v1/executive.json"]
        return json.dumps(baseline).encode()

    monkeypatch.setattr(module.subprocess, "check_output", git_read)
    monkeypatch.setattr(
        module,
        "_quarterly_projection",
        lambda *args: pytest.fail("Editorial mode cannot project financial Q3"),
    )
    if valid:
        assert module.published_executive.__wrapped__(baseline) == baseline
        assert len(calls) == 1
        with pytest.raises(AssertionError):
            module.published_executive.__wrapped__({"records": [{"period_id": "2026Q3"}]})
    else:
        with pytest.raises(AssertionError):
            module.published_executive.__wrapped__(baseline)
        assert calls == []
