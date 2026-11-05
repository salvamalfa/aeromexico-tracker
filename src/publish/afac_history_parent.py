"""Original-source replay of an explicitly unserved, already approved parent.

Original inputs are immutable and separate from the corrected Gold workspace.
Only the current authoritative ledger is copied independently for revocations.
No import, approval, ledger projection rebuild, or remote publication is called.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .afac_history_contract import (
    ORIGINAL_PRODUCER,
    hex_digest,
    materialize_site,
    parent_public,
    relative_name,
    require_keys,
    sha,
)


def physical(repo, name, *, directory=False):
    relative_name(name)
    root, path = Path(repo).resolve(), Path(repo) / name
    if not path.resolve().is_relative_to(root) or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Parent input escaped its physical repository workspace")
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError("Missing physical parent replay input")
    return path


def file_ref(repo, value):
    require_keys(value, {"path", "sha256"}, "private reference")
    hex_digest(value["sha256"])
    path = physical(repo, value["path"])
    if sha(path.read_bytes()) != value["sha256"]:
        raise ValueError("Private input differs from its exact retained hash")
    return path


def identity(path):
    return {
        "sha256": sha(path.read_bytes()),
        "bytes": path.stat().st_size,
        "library_identity": {
            key: sha(os.getxattr(path, key))
            for key in getattr(os, "listxattr", lambda _: ())(path)
            if key.startswith("user.library-")
        },
    }


def parent_inventory(repo, inputs):
    require_keys(inputs, {"root", "inventory", "request"}, "original parent inputs")
    root = physical(repo, inputs["root"], directory=True)
    manifest_path = file_ref(repo, inputs["inventory"])
    inventory = json.loads(manifest_path.read_bytes())
    require_keys(inventory, {"schema_version", "files"}, "parent inventory")
    if inventory["schema_version"] != "afac_history_parent_inputs_v1" or not inventory["files"]:
        raise ValueError("Missing original parent input inventory")
    observed = {}
    for entry in inventory["files"]:
        require_keys(entry, {"path", "sha256", "bytes"}, "parent source file")
        name = relative_name(entry["path"])
        if (
            name in observed
            or name.split("/")[0] not in {"data", "analysis_runs", "tmp"}
            or name.startswith("analysis_runs/lifecycle/")
            or name == "analysis_runs/lifecycle"
        ):
            raise ValueError("Original input inventory overwrites code or current ledger")
        path = physical(root, name)
        current = identity(path)
        if (
            type(entry["bytes"]) is not int
            or current["bytes"] != entry["bytes"]
            or current["sha256"] != entry["sha256"]
        ):
            raise ValueError("Original parent snapshot file changed")
        observed[name] = current
    if list(observed) != sorted(observed):
        raise ValueError("Parent inventory must be ordered and unique")
    request = file_ref(root, inputs["request"])
    if inputs["request"]["path"] not in observed:
        raise ValueError("Original quarterly request is outside its retained input closure")
    return root, request, observed


def ledger_inventory(root):
    """The writer lock and regenerable SQLite projection are not authority."""
    result = {}
    root = Path(root)
    if not (root / "head.json").is_file():
        raise ValueError("Current authoritative ledger is missing")
    for name in ("head.json", "events", "audits"):
        path = root / name
        if path.is_symlink():
            raise ValueError("Current ledger cannot contain symlinks")
        files = path.rglob("*") if path.is_dir() else [path]
        for file in sorted(files):
            if file.is_symlink():
                raise ValueError("Current ledger cannot contain symlinks")
            if file.is_file():
                result[file.relative_to(root).as_posix()] = identity(file)
    return result


# The released producer intentionally has no new gate module. Keep its program
# limited to APIs already present in that original checkout.
REPLAY_SCRIPT = r"""
import hashlib,json,sys
from pathlib import Path
from src.analysis_agent.quarterly_story import code_version
from src.analysis_agent.evidence import digest
from src.publish import gate,quarterly_story_update as release,quarterly_story_scope as check
from src.publish import manifest as manifests
from src.publish.quarterly_story_data import encoded
from src.publish.source_data_scope import pins
request_path,parent_site,scope_sha,producer=sys.argv[1:]
if code_version()!=producer: raise ValueError("Original parent producer fingerprint differs")
problems=check.verify_story(Path(parent_site))
if problems: raise ValueError("Original parent public verifier rejected its own tree: "+str(problems[:3]))
spec=check.anchor()
scope=spec['scope']
if digest(scope)!=scope_sha: raise ValueError("Original inspected scope changed")
request,paths,records,packages=release.request_inputs(Path(request_path))
old,_=release.transport.baseline(release.PATHS.root,spec)
retained,superseded=release.historical_approvals(spec,old)
headers=[dict(entity_key=r['draft']['entity_key'],period_id=r['draft']['period_id'],version=r['version'],
 content_hash=r['content_hash'],evidence_fingerprint=r['draft']['evidence_fingerprint'])
 for r in sorted(records,key=lambda r:r['draft']['entity_key'])]
source_packages={e:dict(package_id=p['package_id'],evidence_fingerprint=p['evidence_fingerprint'])
 for e,p in packages.items()}
outputs=release.data_outputs(request['sources'],release.PATHS.root/'site',packages)
if (headers!=scope['records'] or source_packages!=scope['source_packages']
 or retained!=scope['retained_analysis_manifest'] or superseded!=scope['superseded_analysis_manifest']
 or pins(outputs)!=scope['data_files'] or scope['producer_code_version']!=code_version()):
 raise ValueError("Original source/approval reconstruction differs from its authorized scope")
release.authority(request,scope)
entries=gate.verify_records(records)
for record,authorized,package,calculations in entries:
 payload=gate._analysis_payload(record,authorized,package,calculations)
 from src.publish.manifest import analysis_relative_path
 outputs['data/v1/'+analysis_relative_path(payload).as_posix()]=encoded(payload)
actual=json.loads((Path(parent_site)/'publication_manifest.json').read_bytes())
pins={p['path']:p for p in actual['files']}
for name,raw in outputs.items():
 if pins[name]['bytes']!=len(raw) or pins[name]['sha256']!=hashlib.sha256(raw).hexdigest():
  raise ValueError("Original source/approved payload no longer matches its parent pin: "+name)
print(json.dumps({'producer_code_version':code_version(),'scope_sha256':scope_sha,
 'authorized':actual['analysis_manifest'],'analysis_manifest':actual['analysis_manifest'],
 'outputs_verified':len(outputs),'retained_q2_replayed':len(scope['retained_analysis_manifest'])}))
"""


def replay_parent(repo, parent, inputs, ledger_root):
    """Fully recheck original source, current approval and exact bytes; no cache."""
    manifest, raw_manifest, files, _ = parent_public(repo, parent)
    source_root, _, before = parent_inventory(repo, inputs)
    ledger_before = ledger_inventory(ledger_root)
    with tempfile.TemporaryDirectory(prefix="afac-original-parent-") as temporary:
        temporary_root = Path(temporary).resolve()
        checkout = temporary_root / "producer"
        subprocess.run(
            [
                "git",
                "-c",
                "core.autocrlf=false",
                "worktree",
                "add",
                "--detach",
                str(checkout),
                parent["code_commit"],
            ],
            cwd=repo,
            check=True,
            capture_output=True,
        )
        try:
            for name, pin in before.items():
                target = checkout / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_root / name, target)
                if identity(target) != pin:
                    raise ValueError("Original parent materialization changed bytes or library provenance")
            for name, pin in ledger_before.items():
                target = checkout / "analysis_runs/lifecycle" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path(ledger_root) / name, target)
                if identity(target) != pin:
                    raise ValueError("Current ledger changed while materializing original replay")
            site = materialize_site(temporary_root / "parent-site", raw_manifest, files)
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-c",
                    REPLAY_SCRIPT,
                    str(checkout / inputs["request"]["path"]),
                    str(site),
                    parent["scope_sha256"],
                    ORIGINAL_PRODUCER,
                ],
                cwd=checkout,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=3600,
                env={**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            )
            if result.returncode:
                folder = Path(repo) / "tmp/approval-replay-diagnostics"
                folder.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", suffix=".stderr.txt", dir=folder, delete=False
                ) as output:
                    output.write(result.stderr)
                raise ValueError("Original parent refused replay; inspect private replay diagnostics")
            value = json.loads(result.stdout)
        finally:
            if not checkout.resolve().is_relative_to(temporary_root):
                raise ValueError("Refusing worktree cleanup outside its temporary replay workspace")
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(checkout)],
                cwd=repo,
                check=True,
                capture_output=True,
            )
    if (
        parent_inventory(repo, inputs)[2] != before
        or ledger_inventory(ledger_root) != ledger_before
        or value["producer_code_version"] != ORIGINAL_PRODUCER
        or value["scope_sha256"] != parent["scope_sha256"]
        or value["analysis_manifest"] != manifest["analysis_manifest"]
        or value["outputs_verified"] != 16
        or value["retained_q2_replayed"] != 4
    ):
        raise ValueError("Original parent inputs, approval or complete replay result changed")
    return value
