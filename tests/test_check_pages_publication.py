"""Declared receipt routing never downgrades and executes the pinned checkout."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_pages_publication import VERIFIERS, verifier_for

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/check_pages_publication.py"


def manifest(site, receipts):
    site.mkdir(exist_ok=True)
    (site / "publication_manifest.json").write_text(
        json.dumps({"files": [{"path": name} for name in receipts]}), encoding="utf-8"
    )
    for name in receipts:
        (site / name).write_text("{}", encoding="utf-8")


@pytest.mark.parametrize(
    "receipts, expected",
    [
        ([], "src.publish.verify"),
        (["editorial-publication.json"], "src.publish.editorial"),
        (["editorial-publication.json", "financial-publication.json"], "src.publish.financial_scope"),
        (["issuer-publication.json"], "src.publish.issuer_scope"),
        ([name for name, _ in VERIFIERS], "src.publish.movements_scope"),
    ],
)
def test_declared_receipt_priority(tmp_path, receipts, expected):
    manifest(tmp_path, receipts)
    assert verifier_for(tmp_path) == expected


@pytest.mark.parametrize("receipt, module", VERIFIERS)
def test_missing_declared_receipt_fails_before_any_verifier(tmp_path, receipt, module):
    manifest(tmp_path, [receipt])
    (tmp_path / receipt).unlink()
    with pytest.raises(ValueError, match="declared publication receipt is missing"):
        verifier_for(tmp_path)


@pytest.mark.parametrize("receipt, module", [*VERIFIERS, (None, "src.publish.verify")])
@pytest.mark.parametrize("exit_code", [0, 17])
def test_real_subprocess_uses_cwd_code_and_preserves_failure(tmp_path, receipt, module, exit_code):
    # Master supplies the helper; a separate pinned checkout supplies modules.
    preview = tmp_path / "_preview"
    package = preview / "src/publish"
    package.mkdir(parents=True)
    (preview / "src/__init__.py").touch()
    (package / "__init__.py").touch()
    for _, name in [*VERIFIERS, (None, "src.publish.verify")]:
        filename = package / (name.rsplit(".", 1)[1] + ".py")
        filename.write_text(
            "from pathlib import Path\n"
            f"Path('executed.txt').open('a').write({name!r} + '\\n')\n"
            f"raise SystemExit({exit_code if name == module else 91})\n",
            encoding="utf-8",
        )
    manifest(preview / "site", [receipt] if receipt else [])
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    result = subprocess.run([sys.executable, str(HELPER), "site/"], cwd=preview, env=env)
    assert result.returncode == exit_code
    assert (preview / "executed.txt").read_text().splitlines() == [module]


def test_workflow_uses_master_helper_with_preview_cwd():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/pages.yml").read_text())
    production = next(
        s for s in workflow["jobs"]["verify"]["steps"] if "check_pages_publication" in s.get("run", "")
    )
    preview = next(
        s for s in workflow["jobs"]["preview"]["steps"] if "check_pages_publication" in s.get("run", "")
    )
    assert "python scripts/check_pages_publication.py site/" in production["run"]
    assert preview["working-directory"] == "_preview"
    assert "python ../scripts/check_pages_publication.py site/" in preview["run"]
