"""Add only contracted fare aggregates over a fully verified, immutable published baseline."""

from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

from src.config import PATHS
from src.web_export.fare_averages import CONTRACT, PUBLIC_PATH, validate_averages

from . import manifest as manifests

PROOF = "fare-quotes-publication.json"
POLICY = "config/publish/fare-quotes-policy.json"
DATA = "data/v1/" + PUBLIC_PATH
SCHEMA = "fare_quotes_publication_v1"
FIELDS = {
    "schema_version",
    "baseline_commit",
    "baseline_manifest_sha256",
    "aggregate_sha256",
    "private_input_sha256",
    "policy_sha256",
    "public_contract_sha256",
}


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def public_files(site):
    return {item["path"]: (item["sha256"], item["bytes"]) for item in manifests.file_entries(site)}


def protected(files):
    return {
        name: value
        for name, value in files.items()
        if name not in {"index.html", DATA, PROOF} and not name.startswith("assets/")
    }


def read_proof(site: Path, repo: Path):
    manifest = manifests.load_manifest(site)
    raw = (site / PROOF).read_bytes()
    proof = json.loads(raw)
    if set(proof) != FIELDS or proof["schema_version"] != SCHEMA:
        raise ValueError("Unknown fare publication proof")
    if any(
        not re.fullmatch(r"[a-f0-9]{64}", proof[key])
        for key in FIELDS - {"schema_version", "baseline_commit"}
    ):
        raise ValueError("Invalid fare proof fingerprint")
    commit = proof["baseline_commit"]
    if not re.fullmatch(r"[a-f0-9]{40}", commit) or commit == manifest["code_commit"]:
        raise ValueError("Fare baseline must be an earlier committed publication")
    if subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, manifest["code_commit"]], cwd=repo, capture_output=True
    ).returncode:
        raise ValueError("Fare baseline is outside publication history")
    pin = [row for row in manifest["files"] if row["path"] == PROOF]
    if len(pin) != 1 or pin[0]["sha256"] != sha(raw) or pin[0]["bytes"] != len(raw):
        raise ValueError("Fare proof differs from its manifest pin")
    if (site / PROOF).is_symlink() or any(p.is_symlink() for p in site.rglob("*")):
        raise ValueError("Fare publication cannot contain symlinks")
    if proof["policy_sha256"] != sha((repo / POLICY).read_bytes()):
        raise ValueError("Fare policy differs from the reviewed release")
    if proof["public_contract_sha256"] != sha((repo / "contracts/web" / CONTRACT).read_bytes()):
        raise ValueError("Fare contract differs from reviewed release")
    if proof["aggregate_sha256"] != sha((site / DATA).read_bytes()):
        raise ValueError("Fare aggregate differs from publication proof")
    return proof, manifest


def verify_fare_site(site: Path, repo: Path = PATHS.root, *, depth: int = 0) -> list[str]:
    """Revalidate the preceding strong release, then require every inherited byte unchanged."""
    from scripts.check_pages_publication import verify_site as verify_selected

    from .verify import _verify_site

    try:
        site, repo = Path(site), Path(repo)
        if depth > 20:
            raise ValueError("Excessive fare release ancestry")
        proof, manifest = read_proof(site, repo)
        archive = subprocess.check_output(["git", "archive", proof["baseline_commit"], "site"], cwd=repo)
        with tempfile.TemporaryDirectory(prefix="fare-trusted-site-") as temporary:
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                tar.extractall(temporary, filter="data")
            baseline = Path(temporary) / "site"
            prior = manifests.load_manifest(baseline)
            if sha((baseline / manifests.MANIFEST_NAME).read_bytes()) != proof["baseline_manifest_sha256"]:
                raise ValueError("Fare baseline manifest differs from committed source")
            problems = (
                verify_fare_site(baseline, repo, depth=depth + 1)
                if (baseline / PROOF).exists()
                else verify_selected(baseline, repo)
            )
            if problems:
                raise ValueError(f"Underlying strong publication failed: {problems[:3]}")
            if manifest["analysis_manifest"] != prior["analysis_manifest"]:
                raise ValueError("Fare release changed financial analysis approvals")
            expected_contracts = {**prior["contracts"], CONTRACT: proof["public_contract_sha256"]}
            if manifest["contracts"] != expected_contracts:
                raise ValueError("Fare release changed another public contract")
            if protected(public_files(site)) != protected(public_files(baseline)):
                raise ValueError("Fare release changed, removed or added protected public data")
            validate_averages(json.loads((site / DATA).read_bytes()))
            # Every inherited payload has already passed its original strong verifier.
            inherited = frozenset(
                name for name in public_files(baseline) if name.startswith("data/v1/") and name != DATA
            )
            return _verify_site(site, preserved_approval_files=inherited)
    except (ValueError, KeyError, TypeError, OSError, subprocess.SubprocessError) as error:
        return [f"Invalid fare publication: {error}"]


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    args = parser.parse_args(argv)
    problems = verify_fare_site(args.site)
    for problem in problems:
        print(problem)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
