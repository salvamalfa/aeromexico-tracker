"""Verify configured SEC identities against the official company ticker catalog."""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from typing import Any

from src.common.http import SourceHttpClient
from src.common.logging import configure_logging
from src.common.storage import save_bronze
from src.config import CARRIERS


COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def verify_ciks(payload: dict[str, Any]) -> list[dict[str, str | bool]]:
    """Compare every configured ticker+CIK pair to one SEC catalog payload."""

    by_ticker = {
        str(item["ticker"]).upper(): item
        for item in payload.values()
        if isinstance(item, dict) and item.get("ticker")
    }
    results: list[dict[str, str | bool]] = []
    for carrier_key, identity in CARRIERS.items():
        configured_cik = identity.get("cik")
        ticker = identity.get("ticker")
        if configured_cik is None:
            continue
        if ticker is None:
            results.append(
                {
                    "carrier_key": carrier_key,
                    "ticker": "",
                    "configured_cik": configured_cik,
                    "sec_cik": "",
                    "sec_title": "",
                    "matches": False,
                }
            )
            continue
        item = by_ticker.get(ticker.upper())
        sec_cik = str(item["cik_str"]).zfill(10) if item else ""
        results.append(
            {
                "carrier_key": carrier_key,
                "ticker": ticker,
                "configured_cik": configured_cik,
                "sec_cik": sec_cik,
                "sec_title": str(item.get("title", "")) if item else "",
                "matches": sec_cik == configured_cik,
            }
        )
    return results


def main() -> int:
    configure_logging()
    with SourceHttpClient("sec") as client:
        response = client.request("GET", COMPANY_TICKERS_URL)
    downloaded_at = datetime.now(UTC)
    saved_path = save_bronze(
        response.content,
        "sec",
        "company_tickers",
        "current",
        "json",
        COMPANY_TICKERS_URL,
        "httpx",
        http_status=response.status_code,
        content_type=response.headers.get("content-type", "application/json"),
        downloaded_at=downloaded_at,
        notes="Official SEC ticker catalog used to validate configured CIKs.",
    )
    payload = response.json()
    results = verify_ciks(payload)
    print(
        json.dumps(
            {
                "source_file": str(saved_path),
                "downloaded_at": downloaded_at.isoformat(),
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if not results or not all(bool(result["matches"]) for result in results):
        logging.getLogger("aeromexico_tracker").error("One or more configured CIKs failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
