"""Replace only active route data, retaining exact approved analysis bytes.

The normal gate requires a new analysis audit whenever any web/export code
changes. This narrow migration instead revalidates the existing approvals with
that trusted baseline's implementation, protects the analysis renderer, and
copies every non-flight data file byte for byte. It cannot publish a new thesis,
period, financial metric or refreshed source edition.
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
from src.dashboard.flights import build_flight_payload
from src.web_export.flights import export_flights
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
            protected = protected or not allowed
        if protected:
            raise ValueError(f"Official-route-only migration changed a protected analysis input: {name}")
    # Gold source editions must match the published baseline; this operation
    # is a withdrawal, not a source refresh or new period activation.
    changed_gold = subprocess.check_output(
        ["git", "diff", "--name-only", commit, "--", "data/gold"], cwd=repo, text=True
    ).strip()
    if changed_gold:
        raise ValueError("Official-route-only migration cannot change tracked Gold source editions")


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
    with tempfile.TemporaryDirectory(prefix="official-routes-approved-baseline-") as tmp:
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
        raise ValueError("Official-route-only migration changed shared domain runtime code")


def require_retained_official_metrics(baseline: Path, candidate: Path) -> None:
    """Compare every retained official route with the trusted public snapshot."""
    from src.dashboard.official_route_policy import official_network

    old_root = baseline / "data/v1/flights"
    new_root = candidate / "data/v1/flights"
    before = json.loads((old_root / "quarters.json").read_text())
    after = json.loads((new_root / "quarters.json").read_text())
    old_metadata = {key: value for key, value in before.get("metadata", {}).items() if key != "scope"}
    new_metadata = {key: value for key, value in after.get("metadata", {}).items() if key != "scope"}
    if old_metadata != new_metadata:
        raise ValueError("Route withdrawal changed preserved flight metadata")
    for key in ("quarters", "monthly_passengers", "route_network"):
        if before[key] != after[key]:
            raise ValueError(f"Route withdrawal changed retained flight aggregate/geometry: {key}")
    old_paths = {p.relative_to(old_root) for p in old_root.rglob("*.json") if "international" in p.parts}
    new_paths = {p.relative_to(new_root) for p in new_root.rglob("*.json") if "international" in p.parts}
    if old_paths != new_paths:
        raise ValueError("Route withdrawal changed official international periods")
    for relative in old_paths:
        old = official_network(json.loads((old_root / relative).read_text()))
        new = json.loads((new_root / relative).read_text())
        old_routes = {r["market_key"]: r for r in old["routes"]}
        new_routes = {r["market_key"]: r for r in new["routes"]}
        if old_routes.keys() != new_routes.keys():
            raise ValueError(f"Route withdrawal changed retained official markets: {relative}")
        for market, route in new_routes.items():
            original = old_routes[market]
            for key in (
                "passengers",
                "seats",
                "departures",
                "load_factor",
                "source_label",
                "operation_status",
                "origin",
                "destination",
            ):
                if original.get(key) != route.get(key):
                    raise ValueError(f"Route withdrawal changed retained {key}: {relative}/{market}")
            for key in ("passengers", "seats", "departures", "load_factor"):
                if original.get("previous", {}).get(key) != route.get("previous", {}).get(key):
                    raise ValueError(f"Route withdrawal changed an official comparison: {relative}/{market}")


def publish_official_routes_only(record_paths: list[Path], out_dir: Path):
    """Prepare a signed candidate; deployment remains a separate approved step."""
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
    preserved = data_identities(baseline)
    web_data = gate.WEB_DATA_V1
    if web_data.exists():
        shutil.rmtree(web_data)
    shutil.copytree(baseline / "data/v1", web_data)
    from src.transform.stage6_warehouse import build_warehouse

    build_warehouse(max_stage=9)
    export_flights(build_flight_payload(), web_data)
    dist = gate.build_web(gate.WEB_DIR)
    require_type_only_domain_change(PATHS.root, commit)
    require_retained_official_metrics(baseline, dist)
    if data_identities(dist) != preserved:
        raise gate.PublicationRefused("Route migration changed non-flight data or approved analysis bytes")
    contracts = manifest_mod.contract_hashes()
    if contracts != expected["contracts"]:
        raise gate.PublicationRefused("Route migration changed a published data contract")

    def validate_candidate(candidate):
        if data_identities(candidate) != preserved:
            raise ValueError("Candidate changed a trusted non-flight data file")
        require_retained_official_metrics(baseline, candidate)
        problems = verify_site(candidate)
        if problems:
            raise ValueError(f"Official-route candidate failed verification: {problems[:3]}")

    with gate.flow.writer(root):
        gate.require_trusted_site_baseline(baseline, trusted_commit=commit)
        require_preserved_analysis_implementation(PATHS.root, commit)
        current = verify_baseline_approvals(record_paths, commit, root)
        if [gate._analysis_manifest_entry(item) for item in current] != analysis_manifest:
            raise gate.PublicationRefused("Existing approval changed during the build")
        result = gate.assemble_site(
            dist, analysis_manifest, out_dir, contracts=contracts, validate_candidate=validate_candidate
        )
    # Uses the existing receipt mechanism; no approval/request/audit event is
    # manufactured and all analysis identities remain the original ones.
    receipt = gate.write_receipt(result, authorized, out_dir)
    return {"manifest": result, "receipt": receipt}
