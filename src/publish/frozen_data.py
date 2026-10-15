"""Rebuild a flight-only map with all trusted published data byte-identical.

Revalidate existing approvals through their exact trusted implementation.
No source refresh, historical recomputation or new thesis is allowed.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from src.config import PATHS
from . import manifest as manifest_mod
from .verify import verify_site


PROTECTED = (
    "src/analysis_agent/",
    "src/dashboard/entities.py",
    "src/config.py",
    "uv.lock",
    "contracts/web/",
    "sql/gold/",
    ".agents/skills/",
    "src/web_export/analysis.py",
    "src/web_export/executive.py",
    "src/web_export/business_metrics.py",
    "src/dashboard/executive_summary.py",
    "src/dashboard/market.py",
)


def require_preserved_analysis_implementation(repo: Path, commit: str) -> None:
    """Reject unrelated analysis/frontend changes, including untracked inputs."""
    names = subprocess.check_output(
        ["git", "diff", "--name-only", commit, "--"], cwd=repo, text=True
    ).splitlines()
    names += subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=repo, text=True
    ).splitlines()
    for name in names:
        protected = any(name == prefix or name.startswith(prefix) for prefix in PROTECTED)
        if name.startswith("web/"):
            allowed = name.startswith("web/src/views/flights/") or name == "web/src/types/domain.ts"
            if name == "web/index.html":
                before = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=repo, text=True)
                after = (repo / name).read_text()
                allowed = after == before.replace('>Más pasajeros</button>', '>Más vuelos</button>')
            protected = protected or not allowed
        if protected:
            raise ValueError(f"Frozen-data presentation changed a protected analysis input: {name}")
    # Gold source editions must match the published baseline; this operation
    # is a withdrawal, not a source refresh or new period activation.
    changed_gold = subprocess.check_output(
        ["git", "diff", "--name-only", commit, "--", "data/gold"], cwd=repo, text=True
    ).strip()
    if changed_gold:
        raise ValueError("Frozen-data presentation cannot change tracked Gold source editions")


def verify_baseline_approvals(
    record_paths: list[Path], commit: str, ledger_root: Path, *, include_public_payloads: bool = False
):
    """Run the trusted implementation's complete handoff checks, without writes.

    Source/evidence/ledger paths point to the current private local inputs. Only
    code is taken from the pinned published commit. No secrets are copied.
    """
    from . import gate

    paths = [str(Path(path).resolve()) for path in record_paths]
    archive = subprocess.check_output(
        ["git", "archive", commit, "src", "contracts", "config", "uv.lock", "web", ".agents"], cwd=PATHS.root
    )
    with tempfile.TemporaryDirectory(prefix="frozen-data-approved-baseline-") as tmp:
        base = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(base, filter="data")
        (base / "analysis_runs").symlink_to(PATHS.root / "analysis_runs", target_is_directory=True)
        (base / "data").symlink_to(PATHS.data, target_is_directory=True)
        script = """import json,sys
from pathlib import Path
from src.analysis_agent import lifecycle
from src.publish.gate import _verify_under_lock, _analysis_payload
records=[json.loads(Path(p).read_bytes()) for p in json.loads(sys.argv[1])]
entries=_verify_under_lock(records,Path(sys.argv[2]))
value=[entry[1] for entry in entries]
if sys.argv[3]=="public":
 value={"authorized":value,"payloads":[_analysis_payload(*entry) for entry in entries]}
print(json.dumps(value,ensure_ascii=False))
"""
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                script,
                json.dumps(paths),
                str(ledger_root),
                "public" if include_public_payloads else "authorized",
            ],
            cwd=base,
            capture_output=True,
            text=True,
        )
        if result.returncode:
            # Do not echo arbitrary subprocess output or private records.
            raise gate.PublicationRefused(
                "Trusted baseline refused an existing analysis approval; inspect private diagnostic evidence"
            )
        return json.loads(result.stdout)


def data_identities(directory: Path, *, flights: bool = False):
    return {
        item["path"]: (item["sha256"], item["bytes"])
        for item in manifest_mod.file_entries(directory)
        if item["path"].startswith("data/v1/")
        and (flights or not item["path"].startswith("data/v1/flights/"))
    }


def require_type_only_domain_change(repo: Path, commit: str) -> None:
    """A type-only exception must not change emitted shared runtime code."""
    relative = "web/src/types/domain.ts"
    before = subprocess.check_output(["git", "show", f"{commit}:{relative}"], cwd=repo, text=True)
    after = (repo / relative).read_text()
    if before == after:
        return
    script = """const ts=require('typescript'),fs=require('fs');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const emit=s=>ts.transpileModule(s,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext,verbatimModuleSyntax:true}}).outputText;
process.exit(emit(input.before)===emit(input.after)?0:2);
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=repo / "web",
        input=json.dumps({"before": before, "after": after}),
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise ValueError("Frozen-data presentation changed shared domain runtime code")


def publish_preserved_data(record_paths: list[Path], out_dir: Path):
    """Prepare the real frontend with the complete immutable public snapshot."""
    from . import gate

    out_dir = Path(out_dir).resolve()
    manifest_mod.refuse_if_build_inputs_dirty()
    records = gate.load_records(record_paths)
    if not records:
        raise gate.PublicationRefused("No approved records supplied")
    commit = gate._trusted_site_commit(PATHS.root)
    baseline = PATHS.root / "site"
    gate.require_trusted_site_baseline(baseline, trusted_commit=commit)
    require_preserved_analysis_implementation(PATHS.root, commit)
    problems = verify_site(baseline)
    if problems:
        raise gate.PublicationRefused(f"Trusted baseline failed verification: {problems[:3]}")
    expected = manifest_mod.load_manifest(baseline)
    root = gate.flow.ROOT
    with gate.flow.writer(root):
        authorized = verify_baseline_approvals(record_paths, commit, root)
    analysis_manifest = [gate._analysis_manifest_entry(item) for item in authorized]
    if sorted(analysis_manifest, key=manifest_mod.analysis_sort_key) != expected["analysis_manifest"]:
        raise gate.PublicationRefused("Existing approvals differ from the exact published thesis identities")
    preserved = data_identities(baseline, flights=True)
    if gate.WEB_DATA_V1.exists():
        shutil.rmtree(gate.WEB_DATA_V1)
    shutil.copytree(baseline / "data/v1", gate.WEB_DATA_V1)
    dist = gate.build_web(gate.WEB_DIR)
    require_type_only_domain_change(PATHS.root, commit)
    if data_identities(dist, flights=True) != preserved:
        raise gate.PublicationRefused("Frozen-data UI build changed published data")
    if manifest_mod.contract_hashes() != expected["contracts"]:
        raise gate.PublicationRefused("Frozen-data UI build changed a published contract")

    def validate_candidate(candidate):
        if data_identities(candidate, flights=True) != preserved:
            raise ValueError("Candidate changed trusted published data")
        problems = verify_site(candidate)
        if problems:
            raise ValueError(f"Frozen-data candidate failed verification: {problems[:3]}")

    with gate.flow.writer(root):
        gate.require_trusted_site_baseline(baseline, trusted_commit=commit)
        require_preserved_analysis_implementation(PATHS.root, commit)
        current = verify_baseline_approvals(record_paths, commit, root)
        if [gate._analysis_manifest_entry(item) for item in current] != analysis_manifest:
            raise gate.PublicationRefused("Existing approval changed during the build")
        result = gate.assemble_site(
            dist, analysis_manifest, out_dir, contracts=expected["contracts"], validate_candidate=validate_candidate
        )
    receipt = gate.write_receipt(result, authorized, out_dir)
    return {"manifest": result, "receipt": receipt}
