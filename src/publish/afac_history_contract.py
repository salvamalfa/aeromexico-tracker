"""Closed public boundary for a native AFAC correction over an unserved parent.

The parent is evidence, never a replacement for the actually served baseline.
Historical source/approval replay belongs to afac_history_parent, not this file.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import tarfile
from pathlib import Path, PurePosixPath

from . import editorial as transport
from . import manifest as manifests

ANCHOR = "config/publish/afac-history-release.json"
PROOF = "afac-history-publication.json"
PARENT_ANCHOR = "config/publish/quarterly-story-release.json"
PARENT_PROOF = "quarterly-story-publication.json"
PARENT_KIND = "verified_unpublished_quarterly_story_v1"
SCHEMA = "afac_history_release_v2"
PROOF_SCHEMA = "afac_history_publication_v2"
PRODUCT = "afac_carriers_history"
PERIOD = "2026M09"
TARGETS = ("data/v1/flights/quarters.json", "data/v1/market.json")
ORIGINAL_PRODUCER = "602ea2a44fec7881311af05eb5610de20ddb07219b220c50ff75f618d11960d6"
ORIGINAL_IMPLEMENTATION = "089f48a656e301d2380c8d1a23aab5bb6ada728b"
PARENT_FIELDS = {
    "kind",
    "site_commit",
    "manifest_sha256",
    "code_commit",
    "source_implementation_commit",
    "producer_code_version",
    "scope_sha256",
    "proof",
}


def encoded(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode()


def canonical_digest(value):
    """The original authority scope uses canonical JSON without a final LF."""
    return sha(encoded(value).removesuffix(b"\n"))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f"Invalid {label} fields")


def hex_digest(value, length=64):
    if not isinstance(value, str) or not re.fullmatch(rf"[a-f0-9]{{{length}}}", value):
        raise ValueError("Invalid exact Git or SHA-256 identity")
    return value


def relative_name(value):
    if (
        not isinstance(value, str)
        or not value
        or "\\" in value
        or PurePosixPath(value).is_absolute()
        or ".." in PurePosixPath(value).parts
        or PurePosixPath(value).as_posix() != value
    ):
        raise ValueError("Unsafe noncanonical relative input path")
    return value


def file_pin(pin):
    require_keys(pin, {"path", "sha256", "bytes"}, "file pin")
    relative_name(pin["path"])
    hex_digest(pin["sha256"])
    if type(pin["bytes"]) is not int or pin["bytes"] <= 0:
        raise ValueError("Invalid pinned file length")
    return pin


def pins(outputs):
    return [{"path": name, "sha256": sha(raw), "bytes": len(raw)} for name, raw in sorted(outputs.items())]


def site_tree(repo, commit):
    """Read one complete immutable Git tree, with no checkout or remote claim."""
    hex_digest(commit, 40)
    raw = transport._git(repo, "archive", "--format=tar", commit, "site")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for item in archive:
            if item.isdir():
                continue
            if not item.isfile() or not item.name.startswith("site/"):
                raise ValueError("Git publication tree has a nonphysical file")
            name = relative_name(item.name.removeprefix("site/"))
            if name in files:
                raise ValueError("Duplicate file in Git publication tree")
            files[name] = archive.extractfile(item).read()
    manifest_raw = files.pop(manifests.MANIFEST_NAME)
    manifest = json.loads(manifest_raw)
    declared = manifest["files"]
    for pin in declared:
        file_pin(pin)
    if declared != pins(files):
        raise ValueError("Git publication inventory differs from its exact manifest pins")
    return manifest, manifest_raw, files


def materialize_site(destination, raw_manifest, files):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for name, raw in {**files, manifests.MANIFEST_NAME: raw_manifest}.items():
        target = destination / relative_name(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return destination


def parent_public(repo, parent):
    """Bind the only supported unpublished parent to its original producer."""
    require_keys(parent, PARENT_FIELDS, "unpublished parent")
    if (
        parent["kind"] != PARENT_KIND
        or parent["producer_code_version"] != ORIGINAL_PRODUCER
        or parent["source_implementation_commit"] != ORIGINAL_IMPLEMENTATION
    ):
        raise ValueError("Parent is not the original unserved quarterly-story producer")
    for name in ("site_commit", "code_commit", "source_implementation_commit"):
        hex_digest(parent[name], 40)
    for name in ("manifest_sha256", "scope_sha256"):
        hex_digest(parent[name])
    file_pin(parent["proof"])
    if parent["proof"]["path"] != PARENT_PROOF:
        raise ValueError("Unpublished parent has another proof kind")
    for ancestor, descendant in (
        (parent["source_implementation_commit"], parent["code_commit"]),
        (parent["code_commit"], parent["site_commit"]),
        (parent["site_commit"], manifests.current_commit(repo)),
    ):
        transport._git(repo, "merge-base", "--is-ancestor", ancestor, descendant)
    manifest, raw_manifest, files = site_tree(repo, parent["site_commit"])
    anchor_raw = transport._git(repo, "show", f"{parent['code_commit']}:{PARENT_ANCHOR}")
    spec = json.loads(anchor_raw)
    if (
        sha(raw_manifest) != parent["manifest_sha256"]
        or manifest["code_commit"] != parent["code_commit"]
        or spec["producer_code_version"] != parent["producer_code_version"]
        or spec["scope"]["producer_code_version"] != parent["producer_code_version"]
        or canonical_digest(spec["scope"]) != parent["scope_sha256"]
        or pins({PARENT_PROOF: files[PARENT_PROOF]}) != [parent["proof"]]
        or PROOF in files
    ):
        raise ValueError("Unpublished parent differs from its original Git/producer/scope pins")
    proof = json.loads(files[PARENT_PROOF])
    if proof["anchor_sha256"] != sha(anchor_raw):
        raise ValueError("Unpublished parent proof has another committed anchor")
    from .quarterly_story_scope import ENTITIES, analysis_slots

    for period in ("2026Q2", "2026Q3"):
        analysis_slots(
            [e for e in manifest["analysis_manifest"] if e["period_id"] == period], ENTITIES, period
        )
    if len(manifest["analysis_manifest"]) != 8:
        raise ValueError("Unpublished parent requires exactly eight approved analysis identities")
    return manifest, raw_manifest, files, spec


def output_boundary(before, outputs):
    """The single allowed nested replacement never authorizes other quarters data."""
    if set(outputs) != set(TARGETS) or any(type(raw) is not bytes or not raw for raw in outputs.values()):
        raise ValueError("Historical correction has exactly two nonempty public outputs")
    old, new = (json.loads(value[TARGETS[0]]) for value in (before, outputs))
    if "monthly_passengers" not in new:
        raise ValueError("Historical correction lost the AFAC monthly passenger series")
    if {k: v for k, v in old.items() if k != "monthly_passengers"} != {
        k: v for k, v in new.items() if k != "monthly_passengers"
    }:
        raise ValueError("Historical correction changed a protected non-AFAC quarters block")
    for raw in outputs.values():
        json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Nonfinite {value}")))


def proof_parent(repo, site, manifest, proof):
    """Selector-visible DAG edge, without trusting a proof to waive another one."""
    require_keys(
        proof, {"schema_version", "anchor_sha256", "remote_witness", "candidate_parent"}, "history proof"
    )
    if proof["schema_version"] != PROOF_SCHEMA:
        raise ValueError("Unknown history composition proof version")
    hex_digest(proof["anchor_sha256"])
    parent = proof["candidate_parent"]
    old, _, files, spec = parent_public(repo, parent)
    entries = {row["path"]: row for row in manifest["files"]}
    if (
        (site / PARENT_PROOF).is_symlink()
        or entries.get(PARENT_PROOF) != parent["proof"]
        or (site / PARENT_PROOF).read_bytes() != files[PARENT_PROOF]
    ):
        raise ValueError("Composition parent proof is absent, altered or unlisted")
    if proof["remote_witness"]["baseline_commit"] != spec["baseline_commit"]:
        raise ValueError("Composition witnesses another base; parent is not a served baseline")
    return PARENT_PROOF, old
