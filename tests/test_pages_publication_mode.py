"""Execute both real Pages verifier steps against subsequent and invalid sites."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.check_pages_publication import verifier_for
from src.publish.verify import verify_site

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.safe_load((ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8"))
STEPS = [
    step["run"]
    for job in ("verify", "preview")
    for step in WORKFLOW["jobs"][job]["steps"]
    if "run" in step and "check_pages_publication.py" in step["run"]
]


def resign(site):
    path = site / "publication_manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["files"] = [
        {
            "path": p.relative_to(site).as_posix(),
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
        for p in sorted(site.rglob("*"))
        if p.is_file() and p.name != path.name
    ]
    path.write_text(json.dumps(manifest), encoding="utf-8")


def run_step(script, cwd):
    # Keep the workflow's actual branch and actual verifier modules. Only the
    # environment installer/launcher is replaced by this test's interpreter.
    script = "\n".join(line for line in script.splitlines() if "uv sync " not in line)
    script = script.replace("uv run python ", f'"{sys.executable}" ')
    helper = ROOT / "scripts/check_pages_publication.py"
    script = script.replace("../scripts/check_pages_publication.py", str(helper))
    script = script.replace(" scripts/check_pages_publication.py", f" {helper}")
    return subprocess.run(
        ["bash", "-e", "-c", script],
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("script", STEPS, ids=["production", "preview"])
def test_later_frontend_release_uses_general_verifier_with_old_anchor(tmp_path, script):
    site = tmp_path / "site"
    shutil.copytree(ROOT / "tests/fixtures/site/valid", site)
    (tmp_path / "config/publish").mkdir(parents=True)
    shutil.copyfile(
        ROOT / "config/publish/editorial-release.json", tmp_path / "config/publish/editorial-release.json"
    )
    # A later UI build preserves data but legitimately changes frontend bytes.
    old_data = {p.relative_to(site): p.read_bytes() for p in (site / "data/v1").rglob("*") if p.is_file()}
    with (site / "index.html").open("a", encoding="utf-8") as stream:
        stream.write("\n<!-- subsequent gated frontend build -->\n")
    resign(site)
    assert len(STEPS) == 2
    result = run_step(script, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert all((site / p).read_bytes() == raw for p, raw in old_data.items())
    # Normal verification still refuses corruption; no editorial exception.
    (site / "data/v1/executive.json").write_text("{}", encoding="utf-8")
    assert run_step(script, tmp_path).returncode != 0


@pytest.mark.parametrize("script", STEPS, ids=["production", "preview"])
def test_editorial_receipt_failure_never_falls_back(tmp_path, script):
    site = tmp_path / "site"
    shutil.copytree(ROOT / "tests/fixtures/site/valid", site)
    # Selection now requires a witnessed commit even for a single proof. Use
    # actual disposable Git history so this test reaches the editorial verifier
    # rather than stopping at a malformed selection witness.
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for key, value in (("user.name", "Pages Fixture"), ("user.email", "fixture@example.invalid")):
        subprocess.run(["git", "config", key, value], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "site"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "published baseline fixture"], cwd=tmp_path, check=True)
    baseline = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=tmp_path, text=True).strip()
    proof = site / "editorial-publication.json"
    proof.write_text(json.dumps({"remote_witness": {"baseline_commit": baseline}}), encoding="utf-8")
    resign(site)
    assert verifier_for(site, tmp_path) == "src.publish.editorial"
    # The generic verifier would accept these structurally valid bytes. The
    # selected editorial verifier must reject the incomplete authority proof.
    assert verify_site(site) == []
    result = run_step(script, tmp_path)
    assert result.returncode != 0
    assert "Invalid editorial preservation proof: Invalid editorial proof" in result.stdout + result.stderr
    assert "publication verification selection failed" not in result.stdout + result.stderr
    # Removing a still-inventoried proof fails at selection, never by choosing
    # the weaker generic verifier.
    proof.unlink()
    result = run_step(script, tmp_path)
    assert result.returncode != 0
    assert "declared publication receipt is missing" in result.stdout + result.stderr
