"""Read-only presentation diagnosis. Never imports, approves or publishes a version."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

from src.analysis_agent import entity_adapter, lifecycle
from src.analysis_agent.analyst import SKILL
from src.analysis_agent.evidence import digest
from src.config import PATHS
from src.publish.manifest import analysis_relative_path, load_manifest
from src.web_export.analysis import _load_record

BASE = "40a63d1905afde97ae8e3f8671c8217aafacc4aa"
APPROVED_CODE = "6d8da2c4c0b96371c26521aedb5828610451d03a"
_CACHE: dict[str, str] = {}


def included(name: str) -> bool:
    p = PurePosixPath(name)
    if name in {"src/dashboard/entities.py", "src/config.py", "uv.lock"}:
        return True
    if any(
        name.startswith(folder + "/") for folder in ("src/analysis_agent", "src/publish", "src/web_export")
    ):
        return p.suffix == ".py"
    if name.startswith("contracts/web/"):
        return True
    if name.startswith("web/src/"):
        return (
            p.suffix in {".ts", ".tsx", ".js", ".jsx", ".json", ".css"}
            and not {"test", "tests", "spec", "specs", "__tests__", "__specs__"}.intersection(
                p.relative_to("web/src").parts
            )
            and not re.search(r"(?:^|[._-])(?:test|spec)(?:[._-]|$)", p.name)
        )
    return name in {
        "web/" + n for n in ("index.html", "package.json", "package-lock.json", "vite.config.ts")
    } or (p.parent == PurePosixPath("web") and p.name.startswith("tsconfig") and p.suffix == ".json")


def git_components(ref: str) -> dict[str, str]:
    result = {}
    for entry in subprocess.check_output(["git", "ls-tree", "-rz", ref]).split(b"\0"):
        if not entry:
            continue
        info, raw_name = entry.split(b"\t", 1)
        name, obj = raw_name.decode(), info.split()[2].decode()
        if included(name):
            if obj not in _CACHE:
                _CACHE[obj] = hashlib.sha256(
                    subprocess.check_output(["git", "cat-file", "blob", obj])
                ).hexdigest()
            result[name] = _CACHE[obj]
    return result


def changes(before, after):
    return [
        {"path": name, "before_sha256": before.get(name), "after_sha256": after.get(name)}
        for name in sorted(before.keys() | after.keys())
        if before.get(name) != after.get(name)
    ]


def report() -> dict:
    root = PATHS.root
    current = {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in ("src", "contracts/web", "web")
        for p in (root / folder).rglob("*")
        if p.is_file() and included(p.relative_to(root).as_posix())
    }
    current["uv.lock"] = hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest()
    if digest(current) != entity_adapter.code_version():
        raise ValueError("Diagnostic component selector differs from the unchanged production guard")
    approved, baseline = git_components(APPROVED_CODE), git_components(BASE)
    manifest = load_manifest(root / "site")
    records = []
    for entry in manifest["analysis_manifest"]:
        args = {"entity_key": entry["entity_key"]} if "entity_key" in entry else {}
        record = _load_record(entry["period_id"], entry["version"], lifecycle.ROOT, **args)
        public = json.loads((root / "site/data/v1" / analysis_relative_path(entry)).read_text())
        gate = {"passed": True}
        try:
            lifecycle.require_current_presentation(record)
        except ValueError as error:
            gate = {"passed": False, "error": str(error)}
        # Diagnostic replay only. consumer_payload/export_period remain gated.
        _, calculations, checks = lifecycle.verified_inputs(record)
        rendered = checks["rendered"]
        expected = {claim["claim_id"]: rendered[claim["claim_id"]] for claim in public["claims"]}
        actual = {claim["claim_id"]: claim["text"] for claim in public["claims"]}
        state = lifecycle.state(record, lifecycle.ROOT)
        records.append(
            {
                "entity": entry.get("entity_key", "AEROMEXICO"),
                "period": entry["period_id"],
                "version": entry["version"],
                "content_hash": record["content_hash"],
                "evidence_fingerprint": record["draft"]["evidence_fingerprint"],
                "record_code_version": record["code_version"],
                "prompt_unchanged": record["prompt_version"] == entity_adapter.sha(SKILL),
                "ledger_state": state["state"],
                "approval_event": state["approval"]["event_hash"],
                "presentation_gate": gate,
                "source_calculation_replay": "passed",
                "calculation_record_sha256": digest(calculations),
                "public_claims": len(actual),
                "public_claims_identical": expected == actual,
                "public_claims_sha256": digest(actual),
                "replayed_claims_sha256": digest(expected),
                "thesis_identical": public["thesis"] == rendered[record["draft"]["thesis_claim_id"]],
                "summary_identical": public["summary"]
                == [rendered[cid] for cid in record["draft"]["summary_claim_ids"]],
                "proposed_technical_version_unapproved_not_written": digest(
                    {
                        "draft": record["draft"],
                        "prompt_version": record["prompt_version"],
                        "code_version": digest(current),
                    }
                )
                if lifecycle.is_entity_record(record)
                else None,
            }
        )
    protected = [
        "data/gold",
        "site",
        "src/analysis_agent",
        ".agents/skills/aeromexico-tracker-analysis",
        "config/chat/evidence/approved-index.json",
    ]
    changed_protected = subprocess.check_output(
        ["git", "diff", "--name-only", BASE, "--", *protected], text=True
    ).splitlines()
    from src.dashboard.flights import build_flight_payload
    from src.dashboard.executive_summary import build_executive_payload
    from src.web_export.flights import export_flights, recombine_flights
    from src.web_export.executive import export_executive

    with tempfile.TemporaryDirectory(prefix="presentation-diagnostic-") as temporary:
        folder = Path(temporary)
        export_flights(build_flight_payload(), folder, skip_input_check=True)
        export_executive(build_executive_payload(), folder, skip_input_check=True)
        fresh_flights, site_flights = recombine_flights(folder), recombine_flights(root / "site/data/v1")
        fresh_executive = json.loads((folder / "executive.json").read_text())
        site_executive = json.loads((root / "site/data/v1/executive.json").read_text())
        payloads = {
            "flights_identical": fresh_flights == site_flights,
            "executive_identical": fresh_executive == site_executive,
            "fresh_flights_sha256": digest(fresh_flights),
            "site_flights_sha256": digest(site_flights),
            "fresh_executive_sha256": digest(fresh_executive),
            "site_executive_sha256": digest(site_executive),
        }
    private_gold = []
    for path in sorted((root / "data/gold").glob("*.parquet")):
        if subprocess.run(
            ["git", "ls-files", "--error-unmatch", str(path.relative_to(root))], capture_output=True
        ).returncode:
            private_gold.append(path.stat().st_size)

    return {
        "schema": "presentation_parity_diagnostic_v1",
        "authorizes_publication": False,
        "approved_code_commit": APPROVED_CODE,
        "base_commit": BASE,
        "candidate_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "fingerprints": {
            "approved_entity_code": digest(approved),
            "master_base": digest(baseline),
            "candidate": digest(current),
        },
        "component_counts": {
            "approved": len(approved),
            "master_base": len(baseline),
            "candidate": len(current),
        },
        "inherited_changes": changes(approved, baseline),
        "candidate_changes": changes(baseline, current),
        "protected_paths_changed_since_base": changed_protected,
        "public_payload_parity_diagnostic": payloads,
        "private_gold_inputs": {
            "count": len(private_gold),
            "total_bytes": sum(private_gold),
            "per_file_metadata_redacted": True,
        },
        "selected_records": records,
        "decision": "Presentation remains blocked. Review/import/audit new technical entity versions and obtain explicit approval before export; retain the existing theses and evidence. This report is not an approval.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = report()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "fingerprints": result["fingerprints"],
                "replayed": len(result["selected_records"]),
                "presentation_verified": False,
            }
        )
    )


if __name__ == "__main__":
    main()
