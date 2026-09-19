"""Ingest Aeromexico's official quarterly earnings releases."""

from __future__ import annotations

from pathlib import Path
import re

from src.common.http import SourceHttpClient
from src.common.storage import find_bronze_by_source_url, save_bronze


QUARTERLY_REPORT_URLS: dict[str, str] = {
    "2021Q1": "https://ir.aeromexico.com/static-files/fd62cd60-3ddb-4ba1-81f1-a794697ce359",
    "2021Q2": "https://ir.aeromexico.com/static-files/c251dcd9-6e56-4f0a-9137-0ba66638c773",
    "2021Q3": "https://ir.aeromexico.com/static-files/557a5eaf-dddc-48f3-84d7-9327f8d2679d",
    "2021Q4": "https://ir.aeromexico.com/static-files/9e3e703a-d631-4881-929b-a25a3a3a724c",
    "2022Q1": "https://ir.aeromexico.com/static-files/a1b7e53b-1064-427b-a57c-c85b70206459",
    "2022Q2": "https://ir.aeromexico.com/static-files/4f41fd6a-95d4-4e7f-b4de-b9022c3f7319",
    "2022Q3": "https://ir.aeromexico.com/static-files/a4ca1693-da18-41a9-a0f5-d1c48021805d",
    "2022Q4": "https://ir.aeromexico.com/static-files/9db3b265-dcc6-4122-a7c2-58300c89ce27",
    "2023Q1": "https://ir.aeromexico.com/system/files-encrypted/nasdaq_kms/assets/2024/06/03/18-46-40/Aeromexico%201Q23%20ESP_v5.pdf",
    "2023Q2": "https://ir.aeromexico.com/static-files/7710ae5c-f440-47c1-adb1-024069788c29",
    "2023Q3": "https://ir.aeromexico.com/static-files/4eb960d2-81a8-4b9b-a1b2-d0bfd6d5f183",
    "2023Q4": "https://ir.aeromexico.com/static-files/fe6e72a1-6902-4397-9013-d0368c4d791d",
    "2024Q1": "https://ir.aeromexico.com/static-files/59a0af24-e468-4317-a1a5-24c62cc9dcd0",
    "2024Q2": "https://ir.aeromexico.com/static-files/3a1fae89-d68e-44ca-8245-8b251441fcac",
    "2024Q3": "https://ir.aeromexico.com/static-files/24756e75-735f-4631-8197-ff1dc52e3fa7",
    "2024Q4": "https://ir.aeromexico.com/static-files/afa66157-672a-43ca-8b4f-4227369a2af5",
    "2025Q1": "https://ir.aeromexico.com/static-files/38a5f311-fdcb-48a3-a105-a810bbea38e6",
    "2025Q2": "https://ir.aeromexico.com/static-files/fc1e3602-7fbb-4933-8078-ae2ae5f91c41",
    "2025Q3": "https://ir.aeromexico.com/static-files/516d5667-792f-4746-acab-2f3690d6e06a",
    "2025Q4": "https://ir.aeromexico.com/static-files/37af8ded-ddb8-438a-9088-79c011901830",
    "2026Q1": "https://ir.aeromexico.com/static-files/7ad972df-0474-4c39-b505-e9db9e86ecbd",
    "2026Q2": "https://ir.aeromexico.com/static-files/d780da89-7da6-4360-adae-7ad65f49333e",
}


def _period_from_name(path: Path) -> str:
    match = re.search(r"([1-4])T(\d{2})", path.name, re.IGNORECASE)
    if match is None:
        raise ValueError(f"Cannot infer quarter from {path.name!r}")
    return f"20{match.group(2)}Q{match.group(1)}"


def import_local_reports(directory: str | Path) -> dict[str, object]:
    """Preserve a local archive of official reports in immutable Bronze."""

    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(root)
    saved: list[str] = []
    periods: list[str] = []
    for path in sorted(root.glob("*.pdf")):
        period_id = _period_from_name(path)
        source_url = QUARTERLY_REPORT_URLS.get(period_id)
        if source_url is None:
            raise ValueError(f"No official source URL registered for {period_id}")
        method = "computer_use" if period_id.startswith("2026") else "manual"
        target = save_bronze(
            path.read_bytes(),
            "aeromexico_ir",
            "quarterly_results",
            period_id,
            "pdf",
            source_url,
            method,
            notes="Official Spanish quarterly earnings release from Aeromexico Investor Relations.",
            content_type="application/pdf",
        )
        saved.append(target.as_posix())
        periods.append(period_id)
    return {"report_count": len(saved), "periods": periods, "files": saved}


def download_missing_reports() -> dict[str, object]:
    """Download reports not already represented in the Bronze manifest."""

    saved: list[str] = []
    existing: list[str] = []
    with SourceHttpClient("aeromexico_ir", timeout_seconds=90, max_attempts=2) as client:
        for period_id, source_url in QUARTERLY_REPORT_URLS.items():
            found = find_bronze_by_source_url(source_url)
            if found is not None:
                existing.append(period_id)
                continue
            response = client.get(source_url)
            target = save_bronze(
                response.content,
                "aeromexico_ir",
                "quarterly_results",
                period_id,
                "pdf",
                source_url,
                "httpx",
                notes="Official Spanish quarterly earnings release from Aeromexico Investor Relations.",
                http_status=response.status_code,
                content_type=response.headers.get("content-type", "application/pdf"),
            )
            saved.append(target.as_posix())
    return {"downloaded": saved, "already_available": existing}


def run() -> dict[str, object]:
    return download_missing_reports()

