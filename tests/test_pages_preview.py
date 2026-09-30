"""The pinned Pages preview (.github/pages-preview.json) stays well-formed.

pages.yml validates the same rules before deploying; this catches a bad
edit in CI, before the PR that changes the pin is merged.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / ".github" / "pages-preview.json"


def test_preview_pin_is_well_formed() -> None:
    if not CONFIG.is_file():
        pytest.skip("no Pages preview pinned")
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", data["path"])
    assert data["path"] not in {"assets", "data"}
    assert not (ROOT / "site" / data["path"]).exists(), "the preview path collides with master's site/"
    assert re.fullmatch(r"[0-9a-f]{40}", data["ref"]), "pin a full commit SHA, not a branch"


def test_pages_workflow_serves_the_preview() -> None:
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
    assert ".github/pages-preview.json" in workflow
    assert "path: _pages" in workflow


def test_only_deploy_holds_pages_credentials() -> None:
    import yaml

    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8"))
    assert workflow["permissions"] == {"contents": "read"}
    jobs = workflow["jobs"]
    for name, job in jobs.items():
        granted = job.get("permissions", {})
        if name == "deploy":
            assert granted.get("pages") == "write" and granted.get("id-token") == "write"
        else:
            assert "pages" not in granted and "id-token" not in granted, name
    # The pinned commit must have passed test and web itself.
    steps = " ".join(str(step) for step in jobs["preview"]["steps"])
    assert "check-runs" in steps and '"test", "web"' in steps
