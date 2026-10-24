"""Full new-source replay and separate, exact financial-exposure authorization."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from src.config import PATHS
from . import editorial as transport
from .financial_scope import ANALYSIS, EXECUTIVE, SCOPE, encoded, sha
from .frozen_data import verify_baseline_approvals


def authorization(spec: dict, repo: Path = PATHS.root) -> dict:
    path = repo / "analysis_runs/financial_updates/authorizations" / (spec["authorization_sha256"] + ".json")
    if path.is_symlink():
        raise ValueError("Financial authorization cannot be a symlink")
    raw = path.read_bytes()
    if sha(raw) != spec["authorization_sha256"]:
        raise ValueError("Financial authorization changed")
    value = json.loads(raw)
    bound = {
        k: spec[k]
        for k in (
            "scope",
            "baseline_commit",
            "baseline_manifest_sha256",
            "analysis_entry",
            "analysis_sha256",
            "package_id",
            "calculation_fingerprint",
            "producer_commit",
            "producer_code_version",
            "executive_sha256",
            "executive_bytes",
        )
    }
    if (
        value.get("schema_version") != "financial_authorization_v1"
        or value.get("state") != "approved"
        or value.get("binding") != bound
    ):
        raise ValueError("Financial exposure is unapproved, revoked or bound to another output")
    if value.get("scope") != SCOPE or value.get("constraints") != {
        "new_cards": False,
        "other_entities": False,
        "theses": False,
        "flights": False,
        "news": False,
        "monthly": False,
        "calendar_or_ingestion": False,
    }:
        raise ValueError("Financial authorization has another scope")
    consent = value.get("owner_consent", {})
    if not all(
        isinstance(consent.get(k), str) and consent[k] for k in ("source_reference", "instruction", "at")
    ):
        raise ValueError("Financial exposure has no recorded explicit owner consent")
    report_sha = value.get("independent_review_sha256", "")
    if len(report_sha) != 64 or any(c not in "0123456789abcdef" for c in report_sha):
        raise ValueError("Financial source review digest is invalid")
    report_raw = (repo / "analysis_runs/financial_updates/reviews" / (report_sha + ".json")).read_bytes()
    if sha(report_raw) != report_sha:
        raise ValueError("Financial independent review changed")
    report = json.loads(report_raw)
    if (
        report.get("source_release_passed") is not True
        or report.get("unresolved_findings") != []
        or report.get("producer_commit") != spec["producer_commit"]
        or report.get("producer_code_version") != spec["producer_code_version"]
        or report.get("executive_sha256") != spec["executive_sha256"]
        or report.get("baseline_commit") != spec["baseline_commit"]
    ):
        raise ValueError("Financial independent review does not cover this producer and output")
    return value


def projection_at_commit(spec: dict, package_path: Path, repo: Path = PATHS.root) -> dict:
    """Replay with the reviewed producer, including its dependencies, not later UI code."""
    archive = transport._git(
        repo, "archive", spec["producer_commit"], "src", "contracts", "config", "web", "uv.lock", ".agents"
    )
    baseline = transport._git(repo, "show", f"{spec['baseline_commit']}:site/{EXECUTIVE}")
    with tempfile.TemporaryDirectory(prefix="financial-approved-producer-") as folder:
        base = Path(folder)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(base, filter="data")
        (base / "data").symlink_to(repo / "data", target_is_directory=True)
        code = """import json,sys
from pathlib import Path
from src.publish.financial_projection import executive_projection
from src.analysis_agent.entity_adapter import code_version
print(json.dumps({'code_version':code_version(),'projection':executive_projection(json.loads(sys.stdin.read()),json.loads(Path(sys.argv[1]).read_bytes()))},ensure_ascii=False))
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", code, str(package_path.resolve())],
            cwd=base,
            input=baseline.decode(),
            text=True,
            capture_output=True,
        )
        if result.returncode:
            raise ValueError("Reviewed financial producer rejected the source replay")
        value = json.loads(result.stdout)
    if value["code_version"] != spec["producer_code_version"]:
        raise ValueError("Financial producer identity differs from its review")
    return value["projection"]


def approved_projection(
    record_paths: list[Path], spec: dict, ledger_root: Path, repo: Path = PATHS.root
) -> dict:
    from .records import _analysis_manifest_entry, load_records

    if len(record_paths) != 1:
        raise ValueError("Financial release requires exactly its existing approved source record")
    authorization(spec, repo)
    records = load_records(record_paths)
    record = records[0]
    if (
        record["version"] != spec["analysis_entry"]["version"]
        or record["draft"]["package_id"] != spec["package_id"]
        or record["draft"]["calculation_fingerprint"] != spec["calculation_fingerprint"]
    ):
        raise ValueError("Financial source record differs from its reviewed identity")
    replay = verify_baseline_approvals(
        record_paths, spec["source_implementation_commit"], ledger_root, include_public_payloads=True
    )
    if (
        len(replay["authorized"]) != 1
        or _analysis_manifest_entry(replay["authorized"][0]) != spec["analysis_entry"]
    ):
        raise ValueError("Financial source approval changed or was revoked")
    raw = encoded(replay["payloads"][0])
    baseline_raw = transport._git(repo, "show", f"{spec['baseline_commit']}:site/{ANALYSIS}")
    if raw != baseline_raw or sha(raw) != spec["analysis_sha256"] or len(raw) != spec["analysis_bytes"]:
        raise ValueError("Financial source replay changed the already-published reading")
    package_path = repo / "analysis_runs/evidence" / (spec["package_id"] + ".json")
    projection = projection_at_commit(spec, package_path, repo)
    raw = encoded(projection)
    if sha(raw) != spec["executive_sha256"] or len(raw) != spec["executive_bytes"]:
        raise ValueError("Financial source replay differs from the separately approved projection")
    authorization(spec, repo)
    return projection


def source_snapshot(record_paths: list[Path], spec: dict, ledger_root: Path, repo: Path = PATHS.root) -> dict:
    """Fast final guard after slow candidate checks; no authority is inferred here."""
    record = json.loads(record_paths[0].read_bytes())
    package_path = repo / "analysis_runs/evidence" / (spec["package_id"] + ".json")
    package = json.loads(package_path.read_bytes())
    files = [
        record_paths[0],
        package_path,
        repo / "analysis_runs/quantitative" / (record["draft"]["calculation_fingerprint"] + ".json"),
    ]
    files.extend(
        p for p in ledger_root.rglob("*.json") if "publications" not in p.relative_to(ledger_root).parts
    )
    files.extend((repo / "analysis_runs/financial_updates").rglob("*.json"))
    for source in package["sources"]:
        path = repo / "data/bronze" / source["source_file"]
        files.append(path)
        meta = Path(str(path) + ".meta.json")
        if meta.exists():
            files.append(meta)
    return {str(p.resolve()): sha(p.read_bytes()) for p in files}


def verify_preserved_financial(record_paths, site: Path, ledger_root: Path, *, replay=True):
    """A later ordinary UI build still replays this financial exposure's authority."""
    from .financial_scope import ANCHOR, anchor

    repo = PATHS.root
    if not (site / EXECUTIVE).is_file():
        if (site / "financial-publication.json").exists():
            raise ValueError("Financial exposure has no executive data")
        return None
    raw = (site / EXECUTIVE).read_bytes()
    doc = json.loads(raw)
    aero = doc.get("entities", {}).get("AEROMEXICO", {})
    signals = [
        any(r.get("period_id") == "2026Q3" for r in doc.get("records", [])),
        "2026Q3" in doc.get("views", {}),
        any(r.get("period_id") == "2026Q3" for r in aero.get("records", [])),
        "2026Q3" in aero.get("views", {}),
    ]
    if not any(signals):
        if (site / "financial-publication.json").exists():
            raise ValueError("Financial proof has no financial quarter")
        return None
    if not all(signals):
        raise ValueError("Partial financial quarter cannot bypass its authorization")
    if not (repo / ANCHOR).is_file():
        raise ValueError("Published financial quarter requires its committed financial anchor")
    spec = anchor(repo)
    authorization(spec, repo)
    paths = [
        p for p in record_paths if json.loads(p.read_bytes())["version"] == spec["analysis_entry"]["version"]
    ]
    if sha(raw) != spec["executive_sha256"] or len(raw) != spec["executive_bytes"]:
        raise ValueError("Existing financial data differs from its reviewed source projection")
    if replay and encoded(approved_projection(paths, spec, ledger_root)) != raw:
        raise ValueError("Financial source projection changed")
    return source_snapshot(paths, spec, ledger_root)


def validate_ui_financial_candidate(record_paths, baseline, candidate, ledger_root, snapshot, expected_data):
    """Last financial authority/data check after the ordinary slow verifier."""
    from .frozen_data import data_identities

    if snapshot is None:
        return
    if verify_preserved_financial(record_paths, baseline, ledger_root, replay=False) != snapshot:
        raise ValueError("Financial approval or source changed during candidate validation")
    if data_identities(candidate, flights=True) != expected_data:
        raise ValueError("UI candidate changed financial or unrelated data during validation")


def replay_published_projection(site: Path, repo: Path = PATHS.root) -> dict:
    """Strict source parity remains valid after a normal frontend-only transition."""
    from src.analysis_agent import lifecycle as flow
    from .financial_scope import anchor

    spec = anchor(repo)
    path = repo / "analysis_runs/drafts/2026Q3" / (spec["analysis_entry"]["version"] + ".json")
    with flow.writer(flow.ROOT):
        expected = approved_projection([path], spec, flow.ROOT, repo)
    if encoded(expected) != (site / EXECUTIVE).read_bytes():
        raise ValueError("Published financial data differs from its complete approved source replay")
    return expected
