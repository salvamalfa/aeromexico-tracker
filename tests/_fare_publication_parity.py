"""Authenticate the fare overlay before following its exact published parent."""

import io
import json
import tarfile
import tempfile
from contextlib import ExitStack, contextmanager
from pathlib import Path

from scripts.check_pages_publication import verifier_for
from src.publish import fare_scope, manifest
from src.publish.editorial import _git


@contextmanager
def fare_baseline(site, repo):
    """Yield (site, Git edition) after the complete original strong replay.

    No historical baseline is rechecked with today's SOURCE runtime: the fare
    verifier already executes each exact parent's own selector and producer.
    """
    site = Path(site)
    if verifier_for(site, repo) != "src.publish.fare_scope":
        yield site, None
        return
    raw = (site / manifest.MANIFEST_NAME).read_bytes()
    inventory = manifest.file_entries(site)
    problems = fare_scope.verify_fare_site(site, repo)
    assert not problems, problems
    assert (site / manifest.MANIFEST_NAME).read_bytes() == raw
    assert manifest.file_entries(site) == inventory, "Fare site changed during verification"
    commit, seen = None, set()
    with ExitStack() as stack:
        while verifier_for(site, repo) == "src.publish.fare_scope":
            current = manifest.load_manifest(site)
            proof_raw = (site / fare_scope.PROOF).read_bytes()
            proof = json.loads(proof_raw)
            assert set(proof) == fare_scope.FIELDS and proof["schema_version"] == fare_scope.SCHEMA
            pin = next(p for p in current["files"] if p["path"] == fare_scope.PROOF)
            assert pin["sha256"] == fare_scope.sha(proof_raw) and pin["bytes"] == len(proof_raw)
            commit = proof["baseline_commit"]
            assert commit not in seen, "Cyclic fare baseline"
            seen.add(commit)
            _git(repo, "merge-base", "--is-ancestor", commit, current["code_commit"])
            original = _git(repo, "show", f"{commit}:site/{manifest.MANIFEST_NAME}")
            assert fare_scope.sha(original) == proof["baseline_manifest_sha256"]
            folder = stack.enter_context(tempfile.TemporaryDirectory(prefix="parity-before-fares-"))
            with tarfile.open(fileobj=io.BytesIO(_git(repo, "archive", commit, "site"))) as tar:
                tar.extractall(folder, filter="data")
            site = Path(folder) / "site"
            assert (site / manifest.MANIFEST_NAME).read_bytes() == original
            assert manifest.file_entries(site) == sorted(json.loads(original)["files"], key=lambda p: p["path"])
        yield site, commit
