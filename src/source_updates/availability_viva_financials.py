"""Reviewed Q3 original already acquired; closed-edition proof, not latest discovery."""

from pathlib import Path

import pandas as pd

from src.source_updates.closed_editions import binding_fields, evidence
from src.source_updates.collection import safe_workspace
from src.source_updates.retained import originals

SCOPE = "viva_Q3_official_retained_target_v1"
URL = "https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/ReportesTrimestrales/2026-3T26-en.pdf"
SHA = "a198374a6e74f983e0ea449506b613b996c57c275c45733b91b14fa97e554003"


def preflight(binding, candidate):
    if not binding_fields(binding, {"source_scope"}) or binding.get("source_scope") != SCOPE:
        raise ValueError("Viva Q3 requires its reviewed retained-original scope")
    return safe_workspace(Path(candidate))


def verify(item, result, cutoff):
    root = preflight(item["availability"], item["workspace"])
    if (
        (item["product"], item["adapter"], item["period"]) != ("viva_financials", "viva_financial", "2026Q3")
        or result.get("status") != "checks_passed"
        or result.get("report_period") != "2026Q3"
        or result.get("effective_as_of") != item["candidate_as_of"]
    ):
        raise ValueError("Viva retained proof requires the complete Q3 candidate replay")
    inputs, retention_sha = originals(root, item["product"], item["receipt_id"], cutoff)
    row = inputs["pdf"][1]
    if (
        row["source_url"] != URL
        or row["sha256"] != SHA
        or row.get("http_status") != 200
        or row.get("download_method") != "httpx"
        or row.get("bytes") != 336146
        or result.get("retention_receipt_sha256") != retention_sha
    ):
        raise ValueError("Viva Q3 proof is limited to the verified original, not another edition")
    native = pd.read_parquet(root / "data/silver/viva_financial_native.parquet")
    primary = native.loc[native.edition.eq("2026Q3")]
    if (
        len(primary) != 405
        or set(primary.source_hash) != {SHA}
        or set(primary.source_file) != {row["source_file"]}
        or not primary.report_date.eq("2026-10-28").all()
    ):
        raise ValueError("Viva Q3 native does not bind the reviewed primary original")
    return {
        "validated_closed_edition": evidence(
            item, cutoff, row["downloaded_at"], precision="timestamp", source_url=URL, original_sha=SHA
        ),
        "source_scope": SCOPE,
        "source_representation": "original_official_PDF",
        "source_artifact_url": URL,
        "source_artifact_sha256": SHA,
        "source_availability_observed_at": row["downloaded_at"],
        "source_report_date_as_reported": "2026-10-28",
        "retention_receipt_sha256": retention_sha,
        "availability_basis": "validated_closed_Q3_original_not_latest_index_or_revision_census",
        "latest_source_availability_verified": False,
        "latest_available_period": None,
        "first_publication_date": None,
        "release_lag_days": None,
        "round_as_of": cutoff,
    }
