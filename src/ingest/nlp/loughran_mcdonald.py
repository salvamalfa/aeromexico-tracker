"""Download the official Loughran-McDonald master dictionary to bronze."""

from __future__ import annotations

from datetime import UTC, datetime
import json

import httpx

from src.common.storage import find_bronze_by_source_url, save_bronze


FILE_ID = "1iq2RUf8qGFEAk1g8wQntP3habOnR3fXF"
SOURCE_URL = f"https://drive.google.com/uc?export=download&id={FILE_ID}"
LANDING_PAGE = "https://sraf.nd.edu/loughranmcdonald-master-dictionary/"


def download(*, force: bool = False) -> dict[str, str]:
    existing = find_bronze_by_source_url(SOURCE_URL)
    if existing and not force:
        return {"path": str(existing[0]), "status": "cached", "source_url": SOURCE_URL}

    response = httpx.get(SOURCE_URL, follow_redirects=True, timeout=90.0)
    response.raise_for_status()
    content = response.content
    if not content.startswith(b"Word,Seq_num,"):
        raise ValueError("The official dictionary download did not return the expected CSV")
    path = save_bronze(
        content,
        source_system="loughran_mcdonald",
        entity="master_dictionary",
        period="1993_2025",
        ext="csv",
        source_url=SOURCE_URL,
        download_method="httpx",
        notes=(
            "Official March 2026 release linked by the University of Notre Dame; "
            f"landing page: {LANDING_PAGE}"
        ),
        content_type=response.headers.get("content-type", "text/csv"),
        downloaded_at=datetime.now(UTC),
    )
    return {"path": str(path), "status": "downloaded", "source_url": SOURCE_URL}


def main() -> int:
    print(json.dumps(download(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
