"""Preserve the current FAA IASA country-results publication in bronze."""

from __future__ import annotations

from src.common.http import SourceHttpClient
from src.ingest.stage4_common import fetch_bronze


FAA_RESULTS_URL = "https://www.faa.gov/sites/faa.gov/files/IASAWSR119r.pdf"


def run() -> dict[str, object]:
    with SourceHttpClient("reference") as client:
        path = fetch_bronze(
            client,
            FAA_RESULTS_URL,
            source_system="faa_iasa",
            entity="country_results",
            period="current",
            ext="pdf",
            relative_dir="reference/faa",
            notes="Current FAA-published IASA country results used to verify Mexico's rating.",
        )
    return {"source_file": path.name}


def main() -> int:
    print(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
