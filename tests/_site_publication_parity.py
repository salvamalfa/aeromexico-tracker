"""Test consumers follow exact issuer history instead of freezing the entire site."""

import json
import tempfile
from pathlib import Path

from scripts.check_pages_publication import VERIFIERS, verifier_for
from src.publish import issuer_scope, movements_scope, source_data_scope
from src.publish.editorial import _git
from src.publish.financial_scope import encoded, sha
from src.publish.issuer_projection import require_scope


def verify_current_publication(site, repo, financial_checker):
    module = verifier_for(site, repo)
    if module == "src.publish.source_data_scope":
        problems = source_data_scope.verify_source_data(site, repo)
    elif module == "src.publish.movements_scope":
        problems = movements_scope.verify_movements(site, repo)
    elif module == "src.publish.issuer_scope":
        problems = issuer_scope.verify_issuer(site, repo)
    elif module == "src.publish.financial_scope":
        problems = financial_checker(site, repo)
    elif module == "src.publish.editorial":
        from src.publish.editorial import verify_editorial

        problems = verify_editorial(site, repo)
    elif module == "src.publish.verify":
        from src.publish.verify import verify_site

        problems = verify_site(site)
    else:
        raise AssertionError("Unsupported strict publication verifier: " + module)
    assert not problems, problems


def _active_module(site, repo, manifest, commit):
    if commit is None:
        return verifier_for(site, repo)
    # Only selector inputs are materialized here; the strict current verifier
    # already replays the complete released baseline chain.
    with tempfile.TemporaryDirectory(prefix="parity-proof-") as temporary:
        archive = Path(temporary)
        (archive / "publication_manifest.json").write_bytes(encoded(manifest))
        names = {item["path"] for item in manifest["files"]}
        for proof, _ in VERIFIERS:
            if proof in names:
                (archive / proof).write_bytes(_git(repo, "show", f"{commit}:site/{proof}"))
        return verifier_for(archive, repo)


def _preserved_nonfinancial_financials(site, repo, manifest, commit, spec, label):
    previous = spec["baseline_commit"]
    raw = _git(repo, "show", f"{previous}:site/publication_manifest.json")
    assert sha(raw) == spec["baseline_manifest_sha256"]
    before = json.loads(raw)
    assert len(before["analysis_manifest"]) == 7
    assert manifest["analysis_manifest"] == before["analysis_manifest"], (
        f"{label} changed approvals"
    )
    readings = [item for item in before["files"] if item["path"].startswith("data/v1/analysis/")]
    assert len(readings) == 7, f"{label} baseline is missing a financial thesis"
    for item in readings:
        actual = (
            (site / item["path"]).read_bytes()
            if commit is None
            else _git(repo, "show", f"{commit}:site/{item['path']}")
        )
        assert sha(actual) == item["sha256"] and len(actual) == item["bytes"], item["path"]
    return before


def preserved_financial_projection(site, repo, financial_spec):
    """Every later delta must be its exact reviewed issuer slot, not a whitelist.

    The caller also invokes the strict current verifier, which checks each
    released baseline with its own pinned producer and immutable file manifest.
    Here each financial delta is checked structurally, including prior issuer
    releases, before comparing the complete original financial source replay.
    """
    current_raw = (site / issuer_scope.EXECUTIVE).read_bytes()
    current = json.loads(current_raw)
    manifest = json.loads((site / "publication_manifest.json").read_bytes())
    commit = None
    seen = set()
    nonfinancial = {
        "src.publish.movements_scope": (movements_scope, "Movement correction"),
        "src.publish.source_data_scope": (source_data_scope, "Source data update"),
    }
    while sha(encoded(current)) != financial_spec["executive_sha256"] or {
        movements_scope.PROOF,
        source_data_scope.PROOF,
    } & {
        item["path"] for item in manifest["files"]
    }:
        module = _active_module(site, repo, manifest, commit)
        if module in nonfinancial:
            scope, label = nonfinancial[module]
            assert scope.PROOF in {item["path"] for item in manifest["files"]}, (
                f"Unreviewed {label.lower()} without its own receipt"
            )
            spec = json.loads(
                (repo / scope.ANCHOR).read_bytes()
                if commit is None
                else _git(repo, "show", f"{commit}:{scope.ANCHOR}")
            )
            previous = spec["baseline_commit"]
            assert previous not in seen, "Cyclic publication baseline"
            seen.add(previous)
            before_raw = _git(repo, "show", f"{previous}:site/{issuer_scope.EXECUTIVE}")
            assert current_raw == before_raw, f"{label} changed financial bytes"
            manifest = _preserved_nonfinancial_financials(
                site, repo, manifest, commit, spec, label
            )
            current_raw, current, commit = before_raw, json.loads(before_raw), previous
            continue
        assert module == "src.publish.issuer_scope", "Unreviewed financial publication profile"
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
        before_raw = _git(repo, "show", f"{previous}:site/{issuer_scope.EXECUTIVE}")
        before = json.loads(before_raw)
        if spec["stage"] == "editorial_only":
            assert current == before, "Editorial stage changed financial data"
        else:
            require_scope(before, current, spec["entity_key"], spec["period_id"])
        manifest_raw = _git(repo, "show", f"{previous}:site/publication_manifest.json")
        assert sha(manifest_raw) == spec["baseline_manifest_sha256"]
        manifest = json.loads(manifest_raw)
        current_raw, current, commit = before_raw, before, previous
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
