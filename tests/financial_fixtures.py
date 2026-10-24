"""Disposable public fixtures; no issuer capture, private ledger or production write."""

import copy
import hashlib
import json
import subprocess
from src.publish import financial_scope as f


def git(repo, *args):
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def put(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def inventory(site):
    return [
        {"path": p.relative_to(site).as_posix(), "bytes": p.stat().st_size, "sha256": f.sha(p.read_bytes())}
        for p in sorted(site.rglob("*"))
        if p.is_file() and p.name != "publication_manifest.json"
    ]


def resign(site):
    path = site / "publication_manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["files"] = inventory(site)
    path.write_bytes(f.encoded(manifest))


def financial_release(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "commit", "--allow-empty", "-qm", "source implementation")
    source_commit = git(repo, "rev-parse", "HEAD")
    entry = {
        k: hashlib.sha256(k.encode()).hexdigest()
        for k in ("version", "content_hash", "evidence_fingerprint", "audit_hash", "approval_event")
    }
    entry["period_id"] = "2026Q3"
    financial = {
        "metadata": {
            "default_period": "2026Q2",
            "last_period": "2026Q2",
            "quarter_count": 1,
            "coverage_label": "old",
            "data_as_of": "old",
            "source_view": "old",
            "method_note": "old",
            "load_rask_interpretation": "old",
        },
        "records": [{"period_id": "2026Q2", "passengers": 10}],
        "views": {"2026Q2": {"old": True}},
        "entities": {},
    }
    for entity in ("AEROMEXICO", "INDUSTRY", "VOLARIS", "VIVA_AEROBUS"):
        financial["entities"][entity] = {
            "records": [{"period_id": "2026Q2", "passengers": 10}],
            "views": {"2026Q2": {"old": True}},
            "quarter_count": 1,
            "last_period": "2026Q2",
            "note": "old",
        }
    raw_analysis = b'{"approved":"existing reading"}'
    files = {
        "index.html": b"old frontend",
        "assets/old.js": b"old asset",
        f.EXECUTIVE: f.encoded(financial),
        f.ANALYSIS: raw_analysis,
        "data/v1/analysis/2026Q2.json": b"old Aero reading",
        "data/v1/analysis/VOLARIS/2026Q2.json": b"old Volaris reading",
        "data/v1/analysis/VIVA_AEROBUS/2026Q2.json": b"old Viva reading",
        "data/v1/analysis/INDUSTRY/2026Q2.json": b"old Industry reading",
        "data/v1/flights/quarters.json": b"old flights",
        "data/v1/news.json": b"old news",
        "data/v1/business_metrics.json": b"old financial totals",
        "data/v1/business_metrics.approval.json": b"old financial approval",
        "editorial-publication.json": b"old editorial receipt",
    }
    for path, raw in files.items():
        put(repo / "site" / path, raw)
    old = {
        "files": inventory(repo / "site"),
        "contracts": {"privacy.yaml": "a" * 64},
        "analysis_manifest": [entry],
    }
    baseline_raw = f.encoded(old)
    put(repo / "site/publication_manifest.json", baseline_raw)
    cohort = {
        "implementation_commit": source_commit,
        "analysis_manifest": [entry],
        "files": [{"path": f.ANALYSIS, "bytes": len(raw_analysis), "sha256": f.sha(raw_analysis)}],
    }
    put(repo / "config/publish/approval-cohorts.json", f.encoded({"cohorts": [cohort]}))
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "published baseline")
    baseline_commit = git(repo, "rev-parse", "HEAD")
    projection = copy.deepcopy(financial)
    projection["records"].append({"period_id": "2026Q3", "passengers": 20})
    projection["views"]["2026Q3"] = {"new": True}
    block = projection["entities"]["AEROMEXICO"]
    block["records"].append({"period_id": "2026Q3", "passengers": 20})
    block["views"]["2026Q3"] = {"new": True}
    block.update(last_period="2026Q3", quarter_count=2)
    projection["metadata"].update(last_period="2026Q3", quarter_count=2)
    git(repo, "commit", "--allow-empty", "-qm", "reviewed producer")
    producer = git(repo, "rev-parse", "HEAD")
    output = f.encoded(projection)
    spec = {
        "schema_version": "financial_release_v1",
        "scope": f.SCOPE,
        "baseline_commit": baseline_commit,
        "baseline_manifest_sha256": f.sha(baseline_raw),
        "analysis_entry": entry,
        "analysis_sha256": f.sha(raw_analysis),
        "analysis_bytes": len(raw_analysis),
        "source_implementation_commit": source_commit,
        "package_id": "2026Q3_" + "a" * 64,
        "calculation_fingerprint": "b" * 64,
        "producer_commit": producer,
        "producer_code_version": "c" * 64,
        "executive_sha256": f.sha(output),
        "executive_bytes": len(output),
        "authorization_sha256": "d" * 64,
        "frontend_files": [{"path": "index.html", "sha256": f.sha(b"new frontend"), "bytes": 12}],
    }
    put(repo / f.ANCHOR, f.encoded(spec))
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "scope pin")
    site = tmp_path / "candidate"
    for name, raw in files.items():
        put(site / name, raw)
    put(site / "index.html", b"new frontend")
    put(site / f.EXECUTIVE, output)
    witness = {
        "baseline_commit": baseline_commit,
        "manifest_sha256": f.sha(baseline_raw),
        "files_verified": len(old["files"]),
        "deployment_run": 1,
        "deployment_commit": baseline_commit,
        "origin": f.transport.ORIGIN,
        "verified_at": "2026-10-24T00:00:00+00:00",
    }
    proof = {
        "schema_version": "financial_publication_v1",
        "anchor_sha256": f.sha((repo / f.ANCHOR).read_bytes()),
        "remote_witness": witness,
        "authorization_sha256": spec["authorization_sha256"],
    }
    put(site / f.PROOF, f.encoded(proof))
    put(site / "publication_manifest.json", baseline_raw)
    resign(site)
    return {
        "repo": repo,
        "site": site,
        "spec": spec,
        "old": old,
        "before": financial,
        "projection": projection,
        "proof": proof,
        "witness": witness,
    }


def install_authorization(release):
    r = release
    spec = r["spec"]
    report = {
        "source_release_passed": True,
        "unresolved_findings": [],
        "producer_commit": spec["producer_commit"],
        "producer_code_version": spec["producer_code_version"],
        "executive_sha256": spec["executive_sha256"],
        "baseline_commit": spec["baseline_commit"],
    }
    report_raw = f.encoded(report)
    report_sha = f.sha(report_raw)
    put(r["repo"] / "analysis_runs/financial_updates/reviews" / (report_sha + ".json"), report_raw)
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
    value = {
        "schema_version": "financial_authorization_v1",
        "scope": f.SCOPE,
        "state": "approved",
        "binding": bound,
        "owner_consent": {
            "source_reference": "synthetic fixture",
            "instruction": "Synthetic financial-only consent",
            "at": "fixture",
        },
        "constraints": {
            k: False
            for k in (
                "new_cards",
                "other_entities",
                "theses",
                "flights",
                "news",
                "monthly",
                "calendar_or_ingestion",
            )
        },
        "independent_review_sha256": report_sha,
    }
    raw = f.encoded(value)
    spec["authorization_sha256"] = f.sha(raw)
    path = (
        r["repo"]
        / "analysis_runs/financial_updates/authorizations"
        / (spec["authorization_sha256"] + ".json")
    )
    put(path, raw)
    r["authorization"] = value
    r["authorization_path"] = path
    r["review_path"] = r["repo"] / "analysis_runs/financial_updates/reviews" / (report_sha + ".json")
    return r
