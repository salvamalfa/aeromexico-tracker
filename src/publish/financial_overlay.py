"""Publish the owner-approved financial pair over an immutable site baseline."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from src.config import PATHS
from src.web_export.business_metrics import export_approved_business_metrics

from . import manifest as manifest_mod
from .verify import verify_site


def publish_business_metrics_only(
    record_paths: list[Path],
    out_dir: Path,
) -> dict[str, Any]:
    """Add approved business metrics while retaining all trusted baseline data."""

    from . import gate

    repo_root = PATHS.root
    out_dir = Path(out_dir).resolve()
    try:
        manifest_mod.refuse_if_build_inputs_dirty()
    except RuntimeError as error:
        raise gate.PublicationRefused(f"uncommitted publication inputs: {error}") from error

    records = gate.load_records(record_paths)
    if not records:
        raise gate.PublicationRefused("no --record given; refuse to publish an empty analysis manifest")
    ledger_root = gate.flow.ROOT
    entries = gate.verify_records(records, root=ledger_root)
    authorized = [entry[1] for entry in entries]
    analysis_manifest = [
        {key: entry[key] for key in gate.ANALYSIS_MANIFEST_FIELDS} for entry in authorized
    ]

    trusted_commit = gate._trusted_site_commit(repo_root)
    gate.require_trusted_site_baseline(out_dir, root=repo_root, trusted_commit=trusted_commit)
    problems = verify_site(out_dir)
    if problems:
        raise gate.PublicationRefused(f"existing site is not valid for financial publication: {problems[:5]}")
    current_manifest = manifest_mod.load_manifest(out_dir)
    expected_analysis = sorted(analysis_manifest, key=lambda item: item["period_id"])
    if current_manifest["analysis_manifest"] != expected_analysis:
        raise gate.PublicationRefused("site analysis manifest does not match the exact approved records")

    baseline_data = {
        item["path"]: (item["sha256"], item["bytes"])
        for item in current_manifest["files"]
        if item["path"].startswith("data/v1/")
    }
    if len(baseline_data) != 112:
        raise gate.PublicationRefused(
            "financial-only publication requires the trusted 112-file data baseline"
        )
    metric_paths = {
        "data/v1/business_metrics.json",
        "data/v1/business_metrics.approval.json",
    }
    if metric_paths & set(baseline_data):
        raise gate.PublicationRefused("trusted baseline already contains the business-metrics pair")

    web_data = gate.WEB_DATA_V1
    if web_data.exists():
        shutil.rmtree(web_data)
    web_data.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(out_dir / "data/v1", web_data)
    try:
        written = export_approved_business_metrics(
            repo_root / "config/chat/business-metrics-proposal.json",
            repo_root / "config/chat/metrics-candidates.json",
            repo_root / "config/chat/business-metrics-approval-receipt.json",
            web_data,
        )
    except (OSError, ValueError) as error:
        raise gate.PublicationRefused(f"business metric approval rejected: {error}") from error
    written_paths = {path.relative_to(web_data).as_posix() for path in written}
    expected_metrics = {path.removeprefix("data/v1/") for path in metric_paths}
    if written_paths != expected_metrics:
        raise gate.PublicationRefused(
            "financial exporter did not write exactly the approved payload and receipt"
        )

    dist_dir = gate.build_web(gate.WEB_DIR)
    built_data = {
        item["path"]: (item["sha256"], item["bytes"])
        for item in manifest_mod.file_entries(dist_dir)
        if item["path"].startswith("data/v1/")
    }
    if set(built_data) != set(baseline_data) | metric_paths:
        raise gate.PublicationRefused(
            "frontend build did not preserve the baseline and add only the financial pair"
        )
    if any(built_data[path] != identity for path, identity in baseline_data.items()):
        raise gate.PublicationRefused("frontend build changed a trusted baseline data file")

    contracts = manifest_mod.contract_hashes()
    previous_contracts = current_manifest["contracts"]
    for name, digest in previous_contracts.items():
        if contracts.get(name) != digest:
            raise gate.PublicationRefused(f"published contract changed during financial-only update: {name}")

    def validate_candidate(candidate: Path) -> None:
        candidate_problems = verify_site(candidate)
        if candidate_problems:
            raise ValueError(f"financial candidate failed site verification: {candidate_problems[:5]}")

    try:
        with gate.flow.writer(ledger_root):
            gate.require_trusted_site_baseline(
                out_dir, root=repo_root, trusted_commit=trusted_commit
            )
            current = [
                {key: entry[1][key] for key in gate.ANALYSIS_MANIFEST_FIELDS}
                for entry in gate._verify_under_lock(records, ledger_root)
            ]
            if sorted(current, key=lambda item: item["period_id"]) != expected_analysis:
                raise ValueError("approval changed while financial site was being built; rerun publication")
            manifest = gate.assemble_site(
                dist_dir,
                analysis_manifest,
                out_dir,
                contracts=contracts,
                validate_candidate=validate_candidate,
            )
    except ValueError as error:
        raise gate.PublicationRefused(
            f"financial publication failed final approval or candidate verification: {error}"
        ) from error

    receipt = gate.write_receipt(manifest, authorized, out_dir)
    return {"manifest": manifest, "receipt": receipt}
