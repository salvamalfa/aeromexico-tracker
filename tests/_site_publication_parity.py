"""Test consumers follow exact issuer history instead of freezing the entire site."""

import json
from pathlib import Path

from scripts.check_pages_publication import verifier_for
from src.publish import issuer_scope
from src.publish.editorial import _git
from src.publish.financial_scope import encoded, sha
from src.publish.issuer_projection import require_scope


def verify_current_publication(site, repo, financial_checker):
    module = verifier_for(site)
    if module == "src.publish.issuer_scope":
        problems = issuer_scope.verify_issuer(site, repo)
    elif module == "src.publish.financial_scope":
        problems = financial_checker(site, repo)
    elif module == "src.publish.editorial":
        from src.publish.editorial import verify_editorial

        problems = verify_editorial(site, repo)
    else:
        from src.publish.verify import verify_site

        problems = verify_site(site)
    assert not problems, problems


def preserved_financial_projection(site, repo, financial_spec):
    """Every later delta must be its exact reviewed issuer slot, not a whitelist.

    The caller also invokes the strict current verifier, which checks each
    released baseline with its own pinned producer and immutable file manifest.
    Here each financial delta is checked structurally, including prior issuer
    releases, before comparing the complete original financial source replay.
    """
    current = json.loads((site / issuer_scope.EXECUTIVE).read_bytes())
    manifest = json.loads((site / "publication_manifest.json").read_bytes())
    commit = None
    seen = set()
    while sha(encoded(current)) != financial_spec["executive_sha256"]:
        assert issuer_scope.PROOF in {item["path"] for item in manifest["files"]}, (
            "Unreviewed financial delta without an issuer receipt"
        )
        raw = (
            (repo / issuer_scope.ANCHOR).read_bytes()
            if commit is None
            else _git(repo, "show", f"{commit}:{issuer_scope.ANCHOR}")
        )
        spec = json.loads(raw)
        assert sha(encoded(current)) == spec["executive_sha256"], "Issuer output pin differs"
        assert len(encoded(current)) == spec["executive_bytes"]
        previous = spec["baseline_commit"]
        assert previous not in seen, "Cyclic issuer baseline"
        seen.add(previous)
        before = json.loads(_git(repo, "show", f"{previous}:site/{issuer_scope.EXECUTIVE}"))
        if spec["stage"] == "editorial_only":
            assert current == before, "Editorial stage changed financial data"
        else:
            require_scope(before, current, spec["entity_key"], spec["period_id"])
        manifest_raw = _git(repo, "show", f"{previous}:site/publication_manifest.json")
        assert sha(manifest_raw) == spec["baseline_manifest_sha256"]
        manifest = json.loads(manifest_raw)
        current, commit = before, previous
    assert len(encoded(current)) == financial_spec["executive_bytes"]
    return current


def preserved_readings(site: Path, repo: Path, financial_spec):
    """Protect every original reading, not just the selected current issuer."""
    manifest = json.loads(
        _git(repo, "show", f"{financial_spec['baseline_commit']}:site/publication_manifest.json")
    )
    current = json.loads((site / "publication_manifest.json").read_bytes())
    for entry in manifest["analysis_manifest"]:
        assert entry in current["analysis_manifest"], "Historical approval changed"
    readings = [item for item in manifest["files"] if item["path"].startswith("data/v1/analysis/")]
    for item in readings:
        raw = (site / item["path"]).read_bytes()
        assert sha(raw) == item["sha256"] and len(raw) == item["bytes"], item["path"]
    assert len(readings) == 5
