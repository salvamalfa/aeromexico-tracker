"""Verify narrowly projected monthly source updates over a frozen released site."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from src.config import PATHS

from . import editorial as transport
from . import manifest as manifests
from .issuer_scope import sha, verify_historical_baseline

ANCHOR = "config/publish/source-data-release.json"
PROOF = "source-data-publication.json"


def encoded(value):
    """Strict JSON on this new surface; never emit nonstandard NaN/Infinity."""
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def adapter(product):
    if product == "am_traffic_ir":
        from . import am_monthly_projection as module
    elif product in {"aicm_traffic", "aifa_traffic", "asur_traffic", "gap_traffic"}:
        from . import airport_demand_projection as module
    else:
        raise ValueError("Source has no reviewed selective publication adapter")
    return module


def pins(outputs):
    return [{"path": p, "sha256": sha(b), "bytes": len(b)} for p, b in sorted(outputs.items())]


def scope(spec):
    return {
        k: spec[k]
        for k in (
            "product",
            "period_id",
            "source_binding",
            "baseline_commit",
            "data_files",
            "frontend_files",
            "producer_code_version",
            "contract_changes",
        )
    }


def anchor(repo=PATHS.root):
    raw = (repo / ANCHOR).read_bytes()
    if raw != transport._git(repo, "show", f"HEAD:{ANCHOR}"):
        raise ValueError("Source release anchor must be committed")
    spec = json.loads(raw)
    fields = {
        "schema_version",
        "product",
        "period_id",
        "baseline_commit",
        "baseline_manifest_sha256",
        "producer_code_version",
        "source_binding",
        "projection",
        "data_files",
        "frontend_files",
        "contract_changes",
        "authorization_sha256",
    }
    if set(spec) != fields or spec["schema_version"] != "source_data_release_v1":
        raise ValueError("Unsupported selective source release")
    module = adapter(spec["product"])
    if not re.fullmatch(r"\d{4}M(?:0[1-9]|1[0-2])", spec["period_id"]):
        raise ValueError("Select one real monthly source period")
    if not re.fullmatch("[a-f0-9]{40}", spec["baseline_commit"]):
        raise ValueError("Missing exact baseline commit")
    transport._git(repo, "merge-base", "--is-ancestor", spec["baseline_commit"], "HEAD")
    for k in ("baseline_manifest_sha256", "producer_code_version", "authorization_sha256"):
        if not re.fullmatch("[a-f0-9]{64}", spec[k]):
            raise ValueError("Invalid source release digest")
    binding = spec["source_binding"]
    if set(binding) != {"product", "period", "receipt_id", "candidate_as_of", "output_sha256"} or (
        binding["product"],
        binding["period"],
    ) != (spec["product"], spec["period_id"]):
        raise ValueError("Source release binding names another product/period")
    if set(spec["contract_changes"]) != set(module.CONTRACTS):
        raise ValueError("Unexpected source contract change")
    for name, digest in spec["contract_changes"].items():
        if sha((repo / "contracts/web" / name).read_bytes()) != digest:
            raise ValueError("Source contract differs from its committed release pin")
    for field, allowed in (("data_files", set(module.TARGETS)), ("frontend_files", None)):
        seen = []
        for item in spec[field]:
            name = item["path"]
            if set(item) != {"path", "sha256", "bytes"} or not re.fullmatch("[a-f0-9]{64}", item["sha256"]):
                raise ValueError("Invalid source output pin")
            if type(item["bytes"]) is not int or item["bytes"] <= 0:
                raise ValueError("Invalid source output size")
            if (
                allowed is None
                and name != "index.html"
                and not re.fullmatch(r"assets/[A-Za-z0-9_.-]+\.(js|css)", name)
            ):
                raise ValueError("Unexpected source frontend file")
            seen.append(name)
        if seen != sorted(set(seen)) or (allowed is not None and set(seen) != allowed):
            raise ValueError("Incomplete, duplicate or unordered source output pins")
        if allowed is None and "index.html" not in seen:
            raise ValueError("Source frontend is missing its entry point")
    return spec


def preserved_files(site: Path, repo: Path, spec: dict):
    old, _ = transport.baseline(repo, spec)
    current = manifests.load_manifest(site)
    proof = json.loads((site / PROOF).read_bytes())
    if set(proof) != {"schema_version", "anchor_sha256", "remote_witness"} or (
        proof["schema_version"] != "source_data_publication_v1"
        or proof["anchor_sha256"] != sha((repo / ANCHOR).read_bytes())
    ):
        raise ValueError("Source proof differs from the reviewed committed anchor")
    witness = proof["remote_witness"]
    if (
        witness["baseline_commit"] != spec["baseline_commit"]
        or witness["manifest_sha256"] != spec["baseline_manifest_sha256"]
        or witness["files_verified"] != len(old["files"])
        or witness["origin"] != transport.ORIGIN
        or type(witness["deployment_run"]) is not int
    ):
        raise ValueError("Source proof does not name the physically witnessed served baseline")
    transport._git(repo, "merge-base", "--is-ancestor", witness["deployment_commit"], spec["baseline_commit"])
    if transport._git(
        repo, "diff", "--name-only", witness["deployment_commit"], spec["baseline_commit"], "--", "site"
    ):
        raise ValueError("Source witness deployment differs from its baseline site")
    if not old["analysis_manifest"] or current["analysis_manifest"] != old["analysis_manifest"]:
        raise ValueError("Source data update must preserve every released thesis version")
    if current["contracts"] != {**old["contracts"], **spec["contract_changes"]}:
        raise ValueError("Source data update changed an unrelated contract")
    module = adapter(spec["product"])
    before = {p: transport._git(repo, "show", f"{spec['baseline_commit']}:site/{p}") for p in module.TARGETS}
    outputs = module.public_outputs(before, spec["projection"])
    if pins(outputs) != spec["data_files"] or set(outputs) != set(module.TARGETS):
        raise ValueError("Source projection differs from its reviewed exact data pins")
    old_names = {p["path"] for p in old["files"]}
    names = {p["path"] for p in current["files"]}
    frontend = {p["path"] for p in spec["frontend_files"]}
    if names != old_names | frontend | {PROOF}:
        raise ValueError("Source release added or deleted unrelated surfaces")
    actual = {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()}
    if any(p.is_symlink() for p in site.rglob("*")) or actual != names | {manifests.MANIFEST_NAME}:
        raise ValueError("Source site has a symlink or unmanifested file")
    if transport.frontend_entries(site) != spec["frontend_files"]:
        raise ValueError("Source frontend closure differs from its reviewed pins")
    for pin in spec["data_files"] + spec["frontend_files"]:
        raw = (site / pin["path"]).read_bytes()
        if sha(raw) != pin["sha256"] or len(raw) != pin["bytes"]:
            raise ValueError("Source output bytes differ from the approved release")
    if any((site / p).read_bytes() != raw for p, raw in outputs.items()):
        raise ValueError("Source output contains a change outside its deterministic projection")
    preserved = set()
    for pin in old["files"]:
        name = pin["path"]
        if name in set(module.TARGETS) | frontend | {PROOF}:
            continue
        raw = (site / name).read_bytes()
        if sha(raw) != pin["sha256"] or len(raw) != pin["bytes"]:
            raise ValueError(f"Source data update changed historical bytes: {name}")
        preserved.add(name)
    return frozenset(preserved)


def verify_source_data(site, repo=PATHS.root):
    from src.analysis_agent.entity_adapter import code_version

    from .verify import _verify_site

    try:
        spec = anchor(repo)
        if code_version() != spec["producer_code_version"]:
            raise ValueError("Source runtime differs from its reviewed producer")
        verify_historical_baseline(repo, spec, site)
        return _verify_site(site, preserved_approval_files=preserved_files(site, repo, spec))
    except (ValueError, KeyError, OSError, TypeError, subprocess.SubprocessError) as exc:
        return [f"Invalid selective source publication: {exc}"]


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    problems = verify_source_data(parser.parse_args().site)
    print(json.dumps({"valid": not problems, "problems": problems}))
    return int(bool(problems))


if __name__ == "__main__":
    raise SystemExit(main())
