"""Offline verification of an incremental, reviewed issuer-quarter release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from src.config import PATHS

from . import editorial as transport
from . import manifest as manifests
from .issuer_projection import ENTITIES, require_scope

ANCHOR = "config/publish/issuer-release.json"
PROOF = "issuer-publication.json"
EXECUTIVE = "data/v1/executive.json"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _diagnostic_text(value):
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


def anchor(repo=PATHS.root):
    raw = (repo / ANCHOR).read_bytes()
    if raw != transport._git(repo, "show", f"HEAD:{ANCHOR}"):
        raise ValueError("Issuer release anchor must be committed")
    spec = json.loads(raw)
    fields = {
        "schema_version",
        "baseline_commit",
        "baseline_manifest_sha256",
        "entity_key",
        "period_id",
        "analysis_entry",
        "analysis_sha256",
        "analysis_bytes",
        "executive_sha256",
        "executive_bytes",
        "producer_code_version",
        "stage",
        "package_id",
        "evidence_fingerprint",
        "source_binding",
        "authorization_sha256",
        "previous_entry",
        "previous_file",
    }
    if set(spec) != fields or spec["schema_version"] != "issuer_release_v1":
        raise ValueError("Invalid issuer release anchor")
    if spec["entity_key"] not in ENTITIES or spec["period_id"] != "2026Q3":
        raise ValueError("Issuer release has an unsupported entity/quarter")
    if spec["stage"] not in {"data_only", "editorial_only", "combined"}:
        raise ValueError("Invalid issuer stage")
    if spec["stage"] == "data_only":
        if (
            spec["analysis_entry"] is not None
            or spec["analysis_sha256"] is not None
            or spec["analysis_bytes"] != 0
        ):
            raise ValueError("Data-only release cannot introduce a thesis")
        if not re.fullmatch("[a-f0-9]{64}", spec["authorization_sha256"] or ""):
            raise ValueError("Data-only release requires exact data exposure authority")
        if spec["previous_entry"] is not None or spec["previous_file"] is not None:
            raise ValueError("Data-only publication cannot replace a thesis approval")
    elif manifests.analysis_identity(spec["analysis_entry"]) != (spec["entity_key"], spec["period_id"]):
        raise ValueError("Issuer release and approved thesis identities disagree")
    if (spec["previous_entry"] is None) != (spec["previous_file"] is None):
        raise ValueError("A revision requires both prior approval and file pins")
    for key in (
        "baseline_manifest_sha256",
        "executive_sha256",
        "producer_code_version",
        "evidence_fingerprint",
    ):
        if not isinstance(spec[key], str) or not re.fullmatch("[a-f0-9]{64}", spec[key]):
            raise ValueError("Invalid issuer digest")
    if not re.fullmatch("[a-f0-9]{40}", spec["baseline_commit"]):
        raise ValueError("Invalid issuer baseline commit")
    if spec["stage"] != "data_only" and not re.fullmatch("[a-f0-9]{64}", spec["analysis_sha256"] or ""):
        raise ValueError("Invalid issuer analysis digest")
    sizes = ("executive_bytes",) if spec["stage"] == "data_only" else ("analysis_bytes", "executive_bytes")
    for key in sizes:
        if type(spec[key]) is not int or spec[key] <= 0:
            raise ValueError("Invalid issuer payload size")
    transport._git(repo, "merge-base", "--is-ancestor", spec["baseline_commit"], "HEAD")
    return spec


def verify_historical_baseline(repo, spec, site, *, environment=None, require_site_match=False):
    """Run the original selector/verifier, never ignore a runtime rejection.

    Overlays/control use require_site_match=True to authenticate their input
    tree too. Legacy issuer callers can pass their changed candidate as site;
    the parent's exact Git snapshot is still the only historical verifier input.
    """
    old, raw = transport.baseline(repo, spec)
    if require_site_match:
        actual = manifests.file_entries(Path(site))
        if (
            (Path(site) / manifests.MANIFEST_NAME).read_bytes() != raw
            or actual != sorted(old["files"], key=lambda item: item["path"])
            or any(path.is_symlink() for path in Path(site).rglob("*"))
        ):
            raise ValueError("Historical input site differs from its exact committed manifest")
    for item in old["files"]:
        expected = transport._git(repo, "show", f"{spec['baseline_commit']}:site/{item['path']}")
        if sha(expected) != item["sha256"] or len(expected) != item["bytes"]:
            raise ValueError("Trusted baseline differs from its Git manifest")
    commit = old["code_commit"]
    if not re.fullmatch("[a-f0-9]{40}", commit):
        raise ValueError("Invalid historical verifier commit")
    transport._git(repo, "merge-base", "--is-ancestor", commit, spec["baseline_commit"])
    with tempfile.TemporaryDirectory(prefix="issuer-baseline-") as temporary:
        checkout = Path(temporary) / "checkout"
        subprocess.run(
            ["git", "worktree", "add", "--detach", str(checkout), commit],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        try:
            original = checkout / "site"
            if sha((original / manifests.MANIFEST_NAME).read_bytes()) != sha(raw):
                # The code commit precedes its generated output commit. Use the
                # exact trusted Git site tree as the verifier's input instead.
                original = Path(temporary) / "baseline"
                original.mkdir()
                (original / manifests.MANIFEST_NAME).write_bytes(raw)
                for item in old["files"]:
                    target = original / item["path"]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(
                        transport._git(repo, "show", f"{spec['baseline_commit']}:site/{item['path']}")
                    )
            selector = checkout / "scripts/check_pages_publication.py"
            if selector.is_file():
                # Both selection and verification belong to the producer.
                # A current selector can apply a new composition rule to an
                # old release whose reviewed runtime intentionally differs.
                module = "released scripts/check_pages_publication.py"
                command = [sys.executable, "-B", str(selector), str(original)]
            else:
                from scripts.check_pages_publication import verifier_for

                module = verifier_for(original, checkout)
                if module != "src.publish.verify":
                    raise ValueError("Historical strong publication selector is missing")
                command = [sys.executable, "-B", "-m", module, str(original)]
            try:
                child_environment = dict(os.environ if environment is None else environment)
                child_environment["PYTHONDONTWRITEBYTECODE"] = "1"
                outcome = subprocess.run(
                    command,
                    cwd=checkout,
                    capture_output=True,
                    text=True,
                    env=child_environment,
                    # This caller waits for the complete released verifier
                    # chain. Its own historical children can each allow 600s;
                    # the parent also needs time for setup and other checks.
                    timeout=1800,
                )
            except subprocess.TimeoutExpired as error:
                outcome = error
                outcome.returncode = "timeout"
            if outcome.returncode:
                diagnostics = {
                    "module": module,
                    "code_commit": commit,
                    "returncode": outcome.returncode,
                    "stdout": _diagnostic_text(getattr(outcome, "stdout", "")),
                    "stderr": _diagnostic_text(getattr(outcome, "stderr", "")),
                    "approval_pins": {
                        name: (
                            value if re.fullmatch("[a-f0-9]{64}", value) else "<unset-or-malformed>"
                        )
                        for name in (
                            "CHAT_EVIDENCE_APPROVED_INDEX_SHA256",
                            "CHAT_BUSINESS_METRICS_APPROVAL_RECEIPT_SHA256",
                        )
                        for value in ((os.environ if environment is None else environment).get(name, ""),)
                    },
                }
                folder = repo / "tmp/approval-replay-diagnostics"
                folder.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", suffix=".json", dir=folder, delete=False
                ) as report:
                    json.dump(diagnostics, report, ensure_ascii=False)
                raise ValueError(
                    (
                        "The trusted baseline's own released verifier timed out without a verdict: "
                        if outcome.returncode == "timeout"
                        else "The trusted baseline's own released verifier rejected its site: "
                    )
                    + f"module={module}, code_commit={commit}, returncode={outcome.returncode}; "
                    f"private diagnostics={Path(report.name).relative_to(repo).as_posix()}"
                )
        finally:
            subprocess.run(
                ["git", "worktree", "remove", str(checkout)],
                cwd=repo,
                check=True,
                capture_output=True,
            )
    return old


def preserved_files(site: Path, repo: Path, spec: dict):
    """Only exact historical bytes inherit approval; the new files remain strict."""
    old, _ = transport.baseline(repo, spec)
    current = manifests.load_manifest(site)
    proof = json.loads((site / PROOF).read_bytes())
    if (
        set(proof) != {"schema_version", "anchor_sha256", "remote_witness"}
        or proof["schema_version"] != "issuer_publication_v1"
    ):
        raise ValueError("Invalid issuer publication proof")
    if proof["anchor_sha256"] != sha((repo / ANCHOR).read_bytes()):
        raise ValueError("Issuer proof differs from reviewed anchor")
    witness = proof["remote_witness"]
    if (
        witness["baseline_commit"] != spec["baseline_commit"]
        or witness["manifest_sha256"] != spec["baseline_manifest_sha256"]
        or witness["files_verified"] != len(old["files"])
        or witness["origin"] != transport.ORIGIN
        or type(witness["deployment_run"]) is not int
    ):
        raise ValueError("Issuer remote witness does not identify the exact deployed baseline")
    transport._git(repo, "merge-base", "--is-ancestor", witness["deployment_commit"], spec["baseline_commit"])
    if transport._git(
        repo, "diff", "--name-only", witness["deployment_commit"], spec["baseline_commit"], "--", "site"
    ):
        raise ValueError("Issuer witness has a different site tree")
    name = (
        "data/v1/" + manifests.analysis_relative_path(spec["analysis_entry"]).as_posix()
        if spec["analysis_entry"] is not None
        else None
    )
    additions = [spec["analysis_entry"]] if name else []
    previous = spec["previous_entry"]
    retained_entries = [e for e in old["analysis_manifest"] if e != previous]
    if previous is not None:
        from .approval_cohorts import _cohorts, replacement_cohort

        raw = transport._git(repo, "show", f"{spec['baseline_commit']}:config/publish/approval-cohorts.json")
        new_file = {"path": name, "sha256": spec["analysis_sha256"], "bytes": spec["analysis_bytes"]}
        replacement_cohort(
            {
                "entry": spec["analysis_entry"],
                "file": new_file,
                "replaces": {"entry": previous, "file": spec["previous_file"]},
            },
            _cohorts(raw),
            old,
        )
    expected_entries = sorted([*retained_entries, *additions], key=manifests.analysis_sort_key)
    if current["analysis_manifest"] != expected_entries or current["contracts"] != old["contracts"]:
        raise ValueError("Issuer release changed another approval or a contract")
    old_names = {r["path"] for r in old["files"]}
    new_names = {r["path"] for r in current["files"]}
    if (name is not None and name in old_names and previous is None) or new_names != old_names | (
        {name} if name else set()
    ) | {PROOF}:
        raise ValueError("Issuer release added/removed an unrelated surface")
    allowed = {EXECUTIVE, name, PROOF}
    preserved = set()
    if any(p.is_symlink() for p in site.rglob("*")):
        raise ValueError("Issuer site must not contain symlinks")
    for item in old["files"]:
        if item["path"] in allowed:
            continue
        raw = (site / item["path"]).read_bytes()
        if sha(raw) != item["sha256"] or len(raw) != item["bytes"]:
            raise ValueError(f"Issuer release changed historical bytes: {item['path']}")
        preserved.add(item["path"])
    outputs = [(EXECUTIVE, "executive")] + ([(name, "analysis")] if name else [])
    for path, prefix in outputs:
        raw = (site / path).read_bytes()
        if sha(raw) != spec[prefix + "_sha256"] or len(raw) != spec[prefix + "_bytes"]:
            raise ValueError("Issuer output differs from independently reviewed pins")
    before = json.loads(transport._git(repo, "show", f"{spec['baseline_commit']}:site/{EXECUTIVE}"))
    after = json.loads((site / EXECUTIVE).read_bytes())
    if spec["stage"] == "editorial_only":
        if after != before:
            raise ValueError("Editorial stage cannot alter any financial data")
    else:
        require_scope(before, after, spec["entity_key"], spec["period_id"])
    return frozenset(preserved)


def verify_issuer(site: Path, repo: Path = PATHS.root):
    from src.analysis_agent.entity_adapter import code_version

    from .verify import _verify_site

    try:
        spec = anchor(repo)
        if code_version() != spec["producer_code_version"]:
            raise ValueError("Issuer runtime differs from reviewed producer")
        verify_historical_baseline(repo, spec, site)
        preserved = preserved_files(site, repo, spec)
        return _verify_site(site, preserved_approval_files=preserved)
    except (ValueError, KeyError, OSError, TypeError, subprocess.SubprocessError) as error:
        return [f"Invalid issuer publication: {error}"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    args = parser.parse_args(argv)
    problems = verify_issuer(args.site)
    print(json.dumps({"valid": not problems, "problems": problems}))
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
