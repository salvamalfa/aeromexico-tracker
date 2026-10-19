"""Publish only the accepted flight projection over an immutable signed site.

Existing thesis approvals are re-verified using their published implementation;
non-flight payloads, approval identities and all unrelated contracts stay exact.
"""

from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from src.config import PATHS
from src.web_export.flight_projection import project_flights

from . import manifest as manifest_mod
from .frozen_data import data_identities, require_type_only_domain_change, verify_baseline_approvals
from .verify import verify_site


def outside_flights_html(text):
    start = text.index('<section id="panel-flights"')
    depth = 0
    for match in re.finditer(r"</?section\b[^>]*>", text[start:]):
        depth += -1 if match[0].startswith("</") else 1
        if depth == 0:
            return text[:start] + "<FLIGHTS/>" + text[start + match.end() :]
    raise ValueError("Flights panel has no matching closing section")


def require_flight_only_changes(repo: Path, commit: str):
    names = subprocess.check_output(
        ["git", "diff", "--name-only", commit, "--"], cwd=repo, text=True
    ).splitlines()
    names += subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=repo, text=True
    ).splitlines()
    allowed_src = {
        "src/web_export/flight_projection.py",
        "src/web_export/schemas.py",
        "src/web_export/contract_versions.py",
        "src/publish/flight_overlay.py",
        "src/publish/gate.py",
        "src/publish/README.md",
    }
    for name in names:
        allowed = True
        if name.startswith("src/"):
            allowed = name in allowed_src
        elif name.startswith("web/"):
            allowed = name.startswith("web/src/views/flights/") or name in {
                "web/src/types/domain.ts",
                "web/src/types/generated/flights.ts",
            }
            if name == "web/index.html":
                before = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=repo, text=True)
                allowed = outside_flights_html(before) == outside_flights_html((repo / name).read_text())
        elif name.startswith("contracts/"):
            allowed = name == "contracts/web/flights.schema.json" or name == (
                "contracts/web/versions/"
                "15768d277f9cb31d361d2b976602e4b65e7ed20d6419a38699557b0c13aafef6/flights.schema.json"
            )
        elif name.startswith("config/"):
            allowed = name == "config/flights/2026Q2-accepted.json"
        elif name == "Dockerfile.chat":
            before = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=repo, text=True)
            digest = "15768d277f9cb31d361d2b976602e4b65e7ed20d6419a38699557b0c13aafef6"
            copy = f"COPY contracts/web/versions/{digest}/flights.schema.json ./contracts/web/versions/{digest}/\n"
            allowed = (repo / name).read_text().replace(copy, "") == before
        elif name == ".dockerignore":
            before = subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=repo, text=True)
            digest = "15768d277f9cb31d361d2b976602e4b65e7ed20d6419a38699557b0c13aafef6"
            additions = (
                f"!contracts/web/versions/{digest}/\n!contracts/web/versions/{digest}/flights.schema.json\n"
            )
            allowed = (repo / name).read_text().replace(additions, "") == before
        elif (
            name.startswith("data/gold/")
            or name in {"uv.lock", "pyproject.toml", "railway.toml"}
            or name.startswith(".github/")
        ):
            allowed = False
        if not allowed:
            raise ValueError(f"Flight-only publication changed an unrelated input: {name}")
    # Contract compatibility adds only the exact already-published edition;
    # the resolver's validation logic remains byte-identical.
    resolver_path = "src/web_export/contract_versions.py"
    before_resolver = (
        subprocess.check_output(["git", "show", f"{commit}:{resolver_path}"], cwd=repo, text=True)
        if (repo / resolver_path).exists()
        else None
    )
    if before_resolver is not None:
        marker = '            "17fb7e131da94435190bea925fe9733e298754d04e9b9c5e76fbbea8bef119a7",'
        extra = '            "15768d277f9cb31d361d2b976602e4b65e7ed20d6419a38699557b0c13aafef6",'
        expected_resolver = (
            before_resolver
            if extra in before_resolver
            else before_resolver.replace(marker, marker + "\n" + extra)
        )
        if (repo / resolver_path).read_text() != expected_resolver:
            raise ValueError("Flight publication changed contract-resolution checks")
    # A CLI dispatch may be added; existing gate functions cannot be weakened.
    name = "src/publish/gate.py"
    before = ast.parse(subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=repo, text=True))
    after = ast.parse((repo / name).read_text())

    def functions(module):
        return {
            n.name: ast.dump(n)
            for n in module.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name != "main"
        }

    if functions(before) != functions(after):
        raise ValueError("Flight-only publication changed an existing gate function")
    name = "contracts/web/flights.schema.json"
    before = json.loads(subprocess.check_output(["git", "show", f"{commit}:{name}"], cwd=repo, text=True))
    after = json.loads((repo / name).read_text())
    after["properties"].pop("map_coverage", None)
    after["$defs"].pop("map_coverage", None)
    after["$defs"]["flight_component"]["properties"].pop("regularity", None)
    if after != before:
        raise ValueError("Flight projection changed an existing public data contract")


def publish_flights_only(record_paths: list[Path], out_dir: Path):
    from . import gate

    repo = PATHS.root
    out_dir = Path(out_dir).resolve()
    manifest_mod.refuse_if_build_inputs_dirty()
    if not record_paths:
        raise gate.PublicationRefused("No approved analysis records supplied")
    commit = gate._trusted_site_commit(repo)
    baseline = repo / "site"
    gate.require_trusted_site_baseline(baseline, trusted_commit=commit)
    require_flight_only_changes(repo, commit)
    if problems := verify_site(baseline):
        raise gate.PublicationRefused(f"Trusted site failed verification: {problems[:3]}")
    expected = manifest_mod.load_manifest(baseline)
    approved_code = expected["code_commit"]
    subprocess.run(["git", "merge-base", "--is-ancestor", approved_code, commit], cwd=repo, check=True)
    root = gate.flow.ROOT
    with gate.flow.writer(root):
        authorized = verify_baseline_approvals(record_paths, approved_code, root)
    identities = [gate._analysis_manifest_entry(a) for a in authorized]
    if sorted(identities, key=manifest_mod.analysis_sort_key) != expected["analysis_manifest"]:
        raise gate.PublicationRefused("Approved thesis identities differ from the published baseline")
    preserved = data_identities(baseline)
    config = json.loads((repo / "config/flights/2026Q2-accepted.json").read_text())
    web_data = gate.WEB_DATA_V1
    if web_data.is_symlink():
        raise gate.PublicationRefused("Flight build scratch must not be a symlink")
    if web_data.exists():
        shutil.rmtree(web_data)
    # These local staging links save space. project_flights unlinks every
    # changed destination before writing, leaving the trusted baseline intact.
    shutil.copytree(baseline / "data/v1", web_data, copy_function=os.link)
    project_flights(baseline / "data/v1", web_data, config)
    dist = gate.build_web(gate.WEB_DIR)
    require_type_only_domain_change(repo, commit)
    if data_identities(dist) != preserved:
        raise gate.PublicationRefused("Flight build changed non-flight published data")
    contracts = manifest_mod.contract_hashes()
    if any(contracts.get(k) != v for k, v in expected["contracts"].items() if k != "flights.schema.json"):
        raise gate.PublicationRefused("Flight build changed an unrelated contract")

    def validate(candidate):
        if data_identities(candidate) != preserved:
            raise ValueError("Flight candidate changed a protected published payload")
        if problems := verify_site(candidate):
            raise ValueError(f"Flight candidate verification failed: {problems[:3]}")

    with gate.flow.writer(root):
        gate.require_trusted_site_baseline(baseline, trusted_commit=commit)
        require_flight_only_changes(repo, commit)
        current = verify_baseline_approvals(record_paths, approved_code, root)
        if [gate._analysis_manifest_entry(a) for a in current] != identities:
            raise gate.PublicationRefused("An existing thesis approval changed during the flight build")
        result = gate.assemble_site(
            dist, identities, out_dir, contracts=contracts, validate_candidate=validate
        )
    return {"manifest": result, "receipt": gate.write_receipt(result, authorized, out_dir)}
