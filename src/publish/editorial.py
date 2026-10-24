"""Explicit incremental editorial publication with a remotely witnessed baseline.

Historical semantic approvals are inherited only for identical Git-anchored
bytes. The ordinary verifier and publication modes retain their full replay.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

from src.config import PATHS
from . import manifest as manifests

REPOSITORY = "salvamalfa/aeromexico-tracker"
ORIGIN = "https://salvamalfa.github.io/aeromexico-tracker/"
PROOF = "editorial-publication.json"
ANCHOR = "config/publish/editorial-release.json"
ANALYSIS = "data/v1/analysis/2026Q3.json"


def frontend_entries(dist: Path) -> list[dict]:
    """Pin only the dashboard's generated asset closure, excluding other apps."""
    assets = {p.name: p for p in (dist / "assets").glob("*") if p.is_file()}
    pending = [dist / "index.html"]
    seen = set()
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        seen.add(path)
        text = path.read_text()
        pending.extend(p for name, p in assets.items() if name in text and p not in seen)
    return sorted(
        [
            {
                "path": p.relative_to(dist).as_posix(),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                "bytes": p.stat().st_size,
            }
            for p in seen
        ],
        key=lambda e: e["path"],
    )


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=repo)


def _json(raw: bytes):
    return json.loads(raw)


def anchor(repo: Path) -> dict:
    raw = (repo / ANCHOR).read_bytes()
    # This reviewed anchor must be committed; a local replacement is not authority.
    if raw != _git(repo, "show", f"HEAD:{ANCHOR}"):
        raise ValueError("Editorial anchor is not committed")
    value = _json(raw)
    if (
        set(value)
        != {
            "schema_version",
            "baseline_commit",
            "baseline_manifest_sha256",
            "analysis_entry",
            "analysis_sha256",
            "analysis_bytes",
            "frontend_files",
            "analysis_contract_sha256",
        }
        or value["schema_version"] != "editorial_release_v1"
    ):
        raise ValueError("Invalid editorial anchor")
    for field, size in (
        ("baseline_commit", 40),
        ("baseline_manifest_sha256", 64),
        ("analysis_sha256", 64),
        ("analysis_contract_sha256", 64),
    ):
        if not re.fullmatch(f"[a-f0-9]{{{size}}}", value[field]):
            raise ValueError("Invalid editorial anchor digest")
    if manifests.analysis_identity(value["analysis_entry"]) != ("AEROMEXICO", "2026Q3"):
        raise ValueError("Editorial scope is Aeromexico 3Q26 only")
    names = [item["path"] for item in value["frontend_files"]]
    if len(names) != len(set(names)) or "index.html" not in names:
        raise ValueError("Invalid pinned frontend inventory")
    for item in value["frontend_files"]:
        if (
            set(item) != {"path", "sha256", "bytes"}
            or not (
                item["path"] == "index.html"
                or re.fullmatch(r"assets/[A-Za-z0-9_.-]+\.(js|css)", item["path"])
            )
            or not re.fullmatch("[a-f0-9]{64}", item["sha256"])
            or not isinstance(item["bytes"], int)
            or item["bytes"] <= 0
        ):
            raise ValueError("Invalid pinned frontend file")
    _git(repo, "merge-base", "--is-ancestor", value["baseline_commit"], "HEAD")
    schema_path = repo / "contracts/web" / manifests.EDITORIAL_ANALYSIS_CONTRACT
    if hashlib.sha256(schema_path.read_bytes()).hexdigest() != value["analysis_contract_sha256"]:
        raise ValueError("Editorial analysis contract differs from reviewed anchor")
    return value


def baseline(repo: Path, spec: dict) -> tuple[dict, bytes]:
    raw = _git(repo, "show", f"{spec['baseline_commit']}:site/publication_manifest.json")
    if hashlib.sha256(raw).hexdigest() != spec["baseline_manifest_sha256"]:
        raise ValueError("Baseline manifest differs from reviewed anchor")
    document = _json(raw)
    names = [entry["path"] for entry in document["files"]]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate baseline path")
    for name in names:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or str(path) != name:
            raise ValueError("Unsafe baseline path")
    return document, raw


def _get(path: str) -> bytes:
    request = Request(
        ORIGIN + path, headers={"Cache-Control": "no-cache", "User-Agent": "Aeromexico-editorial-verifier/1"}
    )
    with urlopen(request, timeout=45) as response:
        if response.geturl() != ORIGIN + path:
            raise ValueError("Served baseline redirected")
        return response.read()


def witness_remote(repo: Path, spec: dict) -> dict:
    """Check live master, successful deployment, Git objects and EVERY served file."""
    remote = _git(repo, "ls-remote", "origin", "refs/heads/master").decode().split()[0]
    if remote != spec["baseline_commit"]:
        raise ValueError("Remote master diverged from reviewed baseline")
    document, raw = baseline(repo, spec)
    runs = _json(
        subprocess.check_output(
            [
                "gh",
                "run",
                "list",
                "--repo",
                REPOSITORY,
                "--workflow",
                "pages.yml",
                "--status",
                "success",
                "--limit",
                "30",
                "--json",
                "databaseId,headSha,conclusion,url",
            ],
            cwd=repo,
        )
    )
    deployment = None
    for run in runs:
        commit = run["headSha"]
        if not re.fullmatch("[a-f0-9]{40}", commit):
            continue
        try:
            _git(repo, "merge-base", "--is-ancestor", commit, remote)
            deployed = _git(repo, "show", f"{commit}:site/publication_manifest.json")
            unchanged = not _git(repo, "diff", "--name-only", commit, remote, "--", "site")
        except subprocess.CalledProcessError:
            continue
        if deployed == raw and unchanged:
            deployment = run
            break
    if deployment is None:
        raise ValueError("No successful Pages deployment of exact baseline tree")
    if _get("publication_manifest.json") != raw:
        raise ValueError("Served manifest differs from Git baseline")

    def check(entry):
        name = entry["path"]
        expected = _git(repo, "show", f"{remote}:site/{name}")
        if len(expected) != entry["bytes"] or hashlib.sha256(expected).hexdigest() != entry["sha256"]:
            raise ValueError(f"Git baseline file differs from manifest: {name}")
        if _get(name) != expected:
            raise ValueError(f"Served baseline differs from Git: {name}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(check, document["files"]))
    if (
        _get("publication_manifest.json") != raw
        or _git(repo, "ls-remote", "origin", "refs/heads/master").decode().split()[0] != remote
    ):
        raise ValueError("Remote baseline changed during verification")
    return {
        "baseline_commit": remote,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "files_verified": len(document["files"]),
        "deployment_run": deployment["databaseId"],
        "deployment_commit": deployment["headSha"],
        "origin": ORIGIN,
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }


def preserved_files(site: Path, repo: Path, spec: dict) -> frozenset[str]:
    """Prove scope from Git, never from self-declared receipt hashes."""
    old, _ = baseline(repo, spec)
    current = _json((site / "publication_manifest.json").read_bytes())
    proof = _json((site / PROOF).read_bytes())
    if (
        set(proof)
        != {
            "schema_version",
            "anchor_sha256",
            "baseline_commit",
            "baseline_manifest_sha256",
            "remote_witness",
            "analysis_entry",
        }
        or proof["schema_version"] != "editorial_publication_v1"
    ):
        raise ValueError("Invalid editorial proof")
    if (
        proof["anchor_sha256"] != hashlib.sha256((repo / ANCHOR).read_bytes()).hexdigest()
        or proof["baseline_commit"] != spec["baseline_commit"]
        or proof["baseline_manifest_sha256"] != spec["baseline_manifest_sha256"]
        or proof["analysis_entry"] != spec["analysis_entry"]
    ):
        raise ValueError("Editorial proof differs from reviewed anchor")
    witness = proof["remote_witness"]
    if (
        witness["baseline_commit"] != spec["baseline_commit"]
        or witness["manifest_sha256"] != spec["baseline_manifest_sha256"]
        or witness["files_verified"] != len(old["files"])
        or witness["origin"] != ORIGIN
        or not isinstance(witness["deployment_run"], int)
    ):
        raise ValueError("Incomplete remote witness")
    _git(repo, "merge-base", "--is-ancestor", witness["deployment_commit"], spec["baseline_commit"])
    if _git(repo, "diff", "--name-only", witness["deployment_commit"], spec["baseline_commit"], "--", "site"):
        raise ValueError("Witness deployment has another baseline tree")
    expected_contracts = {
        **old["contracts"],
        manifests.EDITORIAL_ANALYSIS_CONTRACT: spec["analysis_contract_sha256"],
    }
    if current["contracts"] != expected_contracts:
        raise ValueError("Editorial publication changed contracts")
    expected_entries = sorted(
        [*old["analysis_manifest"], spec["analysis_entry"]], key=manifests.analysis_sort_key
    )
    if current["analysis_manifest"] != expected_entries or any(
        manifests.analysis_identity(e) == ("AEROMEXICO", "2026Q3") for e in old["analysis_manifest"]
    ):
        raise ValueError("Editorial publication changed historical approval identities")
    old_names = {e["path"] for e in old["files"]}
    actual_names = {p.relative_to(site).as_posix() for p in site.rglob("*") if p.is_file()}
    if any(p.is_symlink() for p in site.rglob("*")):
        raise ValueError("Editorial publication contains symlinks")
    frontend_names = {item["path"] for item in spec["frontend_files"]}
    if actual_names != old_names | {"publication_manifest.json", PROOF, ANALYSIS} | frontend_names:
        raise ValueError("Editorial publication added out-of-scope files")
    for item in spec["frontend_files"]:
        raw = (site / item["path"]).read_bytes()
        if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("Frontend differs from reviewed build pin")
    for entry in old["files"]:
        name = entry["path"]
        if name == "index.html":
            continue
        expected = _git(repo, "show", f"{spec['baseline_commit']}:site/{name}")
        path = site / name
        if not path.is_file() or path.read_bytes() != expected:
            raise ValueError(f"Editorial publication changed preserved file: {name}")
    raw = (site / ANALYSIS).read_bytes()
    if len(raw) != spec["analysis_bytes"] or hashlib.sha256(raw).hexdigest() != spec["analysis_sha256"]:
        raise ValueError("New editorial payload differs from approved pin")
    return frozenset(old_names - {"index.html"})


def verify_editorial(site: Path, repo: Path = PATHS.root) -> list[str]:
    from .verify import _verify_site

    try:
        allowed = preserved_files(site, repo, anchor(repo))
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        return [f"Invalid editorial preservation proof: {error}"]
    return _verify_site(site, preserved_approval_files=allowed)


def publish_editorial(record_paths: list[Path], out_dir: Path):
    from . import gate

    repo = PATHS.root
    manifests.refuse_if_build_inputs_dirty()
    start_head = _git(repo, "rev-parse", "HEAD")
    spec = anchor(repo)
    if gate._trusted_site_commit(repo) != spec["baseline_commit"]:
        raise gate.PublicationRefused("Editorial baseline is not current origin/master")
    gate.require_trusted_site_baseline(repo / "site", trusted_commit=spec["baseline_commit"])
    records = gate.load_records(record_paths)
    if len(records) != 1 or records[0]["draft"].get("source_profile") != "quarterly_release_v1":
        raise gate.PublicationRefused("Editorial publication requires only the new quarterly record")
    old, _ = baseline(repo, spec)
    first_witness = witness_remote(repo, spec)

    def approved():
        entry = gate._verify_under_lock(records, gate.flow.ROOT)[0]
        payload = gate._analysis_payload(*entry)
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        if (
            gate._analysis_manifest_entry(entry[1]) != spec["analysis_entry"]
            or len(raw) != spec["analysis_bytes"]
            or hashlib.sha256(raw).hexdigest() != spec["analysis_sha256"]
        ):
            raise ValueError("New editorial approval or payload changed")
        return entry, raw

    with gate.flow.writer(gate.flow.ROOT):
        entry, raw = approved()
    web = gate.WEB_DATA_V1
    if web.exists():
        shutil.rmtree(web)
    shutil.copytree(repo / "site/data/v1", web)
    (web / "analysis/2026Q3.json").write_bytes(raw)
    dist = gate.build_web()
    if frontend_entries(dist) != spec["frontend_files"]:
        raise ValueError("Frontend build differs from committed editorial pin")
    old_names = {item["path"] for item in old["files"]}
    retained = old_names | {e["path"] for e in spec["frontend_files"]} | {ANALYSIS}
    # Vite builds access/review applications too. Retain their original HTML
    # and assets; deploy only the newly pinned dashboard asset closure.
    for path in dist.rglob("*"):
        if path.is_file() and path.relative_to(dist).as_posix() not in retained:
            if path.parent != dist / "assets":
                raise ValueError("Build introduced an out-of-scope surface")
            path.unlink()
    # Keep the entire prior tree, including old assets, so preservation means
    # bytes, not a promise about equivalent data. Only index is replaced.
    for item in old["files"]:
        if item["path"] != "index.html":
            target = dist / item["path"]
            if item["path"].startswith("data/v1/") and (
                not target.exists() or target.read_bytes() != (repo / "site" / item["path"]).read_bytes()
            ):
                raise ValueError("Frontend build changed a preserved file")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(repo / "site" / item["path"], target)
    final_witness = witness_remote(repo, spec)
    if final_witness["deployment_commit"] != first_witness["deployment_commit"]:
        raise ValueError("Baseline deployment changed during build")
    proof = {
        "schema_version": "editorial_publication_v1",
        "anchor_sha256": hashlib.sha256((repo / ANCHOR).read_bytes()).hexdigest(),
        "baseline_commit": spec["baseline_commit"],
        "baseline_manifest_sha256": spec["baseline_manifest_sha256"],
        "remote_witness": final_witness,
        "analysis_entry": spec["analysis_entry"],
    }
    (dist / PROOF).write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")

    def final_baseline():
        manifests.refuse_if_build_inputs_dirty()
        if _git(repo, "rev-parse", "HEAD") != start_head or anchor(repo) != spec:
            raise ValueError("Editorial code or anchor changed during build")
        gate.require_trusted_site_baseline(repo / "site", trusted_commit=spec["baseline_commit"])
        if (
            _git(repo, "ls-remote", "origin", "refs/heads/master").decode().split()[0]
            != spec["baseline_commit"]
        ):
            raise ValueError("Remote master changed before swap")

    def validate(candidate):
        problems = verify_editorial(candidate, repo)
        if problems:
            raise ValueError(f"Editorial candidate refused: {problems[:3]}")
        final_baseline()

    with gate.flow.writer(gate.flow.ROOT):
        final_baseline()
        final_entry, final_raw = approved()
        if final_entry != entry or final_raw != raw:
            raise ValueError("Approval changed during build")
        final_baseline()
        manifest = gate.assemble_site(
            dist,
            sorted([*old["analysis_manifest"], spec["analysis_entry"]], key=manifests.analysis_sort_key),
            out_dir,
            contracts={
                **old["contracts"],
                manifests.EDITORIAL_ANALYSIS_CONTRACT: spec["analysis_contract_sha256"],
            },
            validate_candidate=validate,
        )
    receipt = gate.write_receipt(manifest, [entry[1]], out_dir)
    return {"manifest": manifest, "receipt": receipt}


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("site", type=Path)
    args = parser.parse_args(argv)
    problems = verify_editorial(args.site)
    if problems:
        print("\n".join(problems))
        return 1
    print("Editorial site valid: historical bytes inherited, new approved payload pinned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
