"""Select published BMV ZIPs and register their bounded offline JSON members."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import zipfile

from src.config import PATHS, SOURCE_URLS
from src.ingest.bmv.download import _validate_archive, parse_catalog_html
from src.common.storage import save_bronze
from src.source_updates.checks import period_end, verify_bronze


def selection(catalog_file: Path, period: str, tickers: tuple[str, ...] = ("AERO", "VOLAR")) -> dict:
    if len(period) == 4 and period.isdigit():
        period_end(period + "Q4")
    else:
        period_end(period)
    if not tickers or not set(tickers) <= {"AERO", "VOLAR"}:
        raise ValueError("Select AERO and/or VOLAR explicitly")
    reports = [
        r
        for r in parse_catalog_html(catalog_file.read_bytes())
        if r.package_period_id == period and r.ticker in tickers
    ]
    if {r.ticker for r in reports} != set(tickers):
        raise ValueError("Requested BMV ticker/period absent from the actual catalogue")
    return {
        "version": 1,
        "items": [
            {
                "id": f"bmv-{r.ticker}-{period}",
                "product": "bmv_xbrl",
                "source_system": "bmv",
                "entity": f"{r.ticker}_xbrl_package",
                "period": period,
                "purpose": "data",
                "url": r.zip_url,
                "extension": "zip",
                "mode": "get",
                "relative_dir": f"bmv/xbrl/{r.ticker}/{period}",
            }
            for r in reports
        ],
    }


def preserved_reports(artifacts):
    catalogues = sorted(
        (
            (name, row)
            for name, row in artifacts.items()
            if row["source_system"] == "bmv" and row["source_url"] == SOURCE_URLS["bmv_xbrl"]
        ),
        key=lambda item: item[1]["downloaded_at"],
    )
    if not catalogues:
        raise FileNotFoundError("Preserved BMV catalogue is required")
    reports = {}
    for name, _ in catalogues:
        for report in parse_catalog_html((PATHS.bronze / name).read_bytes()):
            reports[report.zip_url] = report
    return list(reports.values())


def register_members() -> tuple[str, ...]:
    artifacts = verify_bronze(PATHS.root)
    zip_files = {
        r["source_url"]: (PATHS.bronze / name, r)
        for name, r in artifacts.items()
        if r["source_system"] == "bmv" and name.lower().endswith(".zip")
    }
    reports = [r for r in preserved_reports(artifacts) if r.zip_url in zip_files]
    if not reports or len(reports) > 50:
        raise ValueError("Select 1..50 BMV packages actually present in the catalogue")
    # Preflight all archives before registration. The canonical limits cap each
    # member at 100 MB and each archive at 250 MB; exactly one JSON is accepted.
    for report in reports:
        with zipfile.ZipFile(zip_files[report.zip_url][0]) as archive:
            members = _validate_archive(archive)
            if len(members) != 1 or members[0].flag_bits & 1:
                raise ValueError("BMV requires exactly one unencrypted JSON instance")
    for report in reports:
        path, metadata = zip_files[report.zip_url]
        with zipfile.ZipFile(path) as archive:
            member = _validate_archive(archive)[0]
            content = archive.read(member)
        if not isinstance(json.loads(content), dict):
            raise ValueError("BMV member must be an XBRL JSON object")
        save_bronze(
            content,
            "bmv",
            f"{report.ticker}_xbrl_member",
            report.package_period_id,
            "json",
            f"{report.zip_url}#member={member.filename}",
            "offline_zip_member",
            bronze_root=PATHS.bronze,
            relative_dir=f"bmv/xbrl/{report.ticker}/{report.package_period_id}/extracted",
            downloaded_at=datetime.fromisoformat(metadata["downloaded_at"]),
            content_type="application/json",
            notes="Offline derivation from verified immutable ZIP; no HTTP request to fragment URL.",
        )
    return tuple(report.zip_url for report in reports)


def parse_selected() -> dict:
    from src.parse.bmv.pipeline import run_bmv_parse

    urls = register_members()
    reports = preserved_reports(verify_bronze(PATHS.root))
    return {**run_bmv_parse(zip_urls=urls, reports=reports), "bounded_offline_member_registration": True}
