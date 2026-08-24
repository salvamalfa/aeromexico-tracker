"""Download BTS T-100 International Segment (All Carriers) by year."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path

from bs4 import BeautifulSoup
import httpx

from src.common.http import SourceHttpClient
from src.common.storage import find_bronze_by_source_url, save_bronze


FORM_URL = (
    "https://www.transtats.bts.gov/DL_SelectFields.aspx?"
    "gnoyr_VQ=FJE&QO_fu146_anzr=Nv4%20Pn44vr45"
)
FIELDS = (
    "DEPARTURES_SCHEDULED",
    "DEPARTURES_PERFORMED",
    "SEATS",
    "PASSENGERS",
    "FREIGHT",
    "MAIL",
    "DISTANCE",
    "RAMP_TO_RAMP",
    "AIR_TIME",
    "UNIQUE_CARRIER",
    "AIRLINE_ID",
    "UNIQUE_CARRIER_NAME",
    "UNIQUE_CARRIER_ENTITY",
    "CARRIER",
    "CARRIER_NAME",
    "CARRIER_GROUP",
    "ORIGIN",
    "ORIGIN_CITY_NAME",
    "ORIGIN_COUNTRY",
    "ORIGIN_COUNTRY_NAME",
    "DEST",
    "DEST_CITY_NAME",
    "DEST_COUNTRY",
    "DEST_COUNTRY_NAME",
    "AIRCRAFT_TYPE",
    "AIRCRAFT_CONFIG",
    "YEAR",
    "QUARTER",
    "MONTH",
    "CLASS",
)


def logical_source_url(year: int) -> str:
    return f"{FORM_URL}&requested_geography=Mexico&requested_year={year}"


def _post_payload(html: str, *, year: int) -> tuple[str, dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    form = soup.find("form", method=lambda value: value and value.lower() == "post")
    if form is None:
        raise ValueError("BTS field-selection form was not found")
    payload = {
        node["name"]: node.get("value", "")
        for node in form.find_all("input", type="hidden")
        if node.get("name")
    }
    payload.update(
        {
            "cboGeography": "Mexico",
            "cboYear": str(year),
            "cboPeriod": "All",
            "chkDownloadZip": "on",
            "chkshowNull": "on",
            "btnDownload": "Download",
            **{field: "on" for field in FIELDS},
        }
    )
    action = str(httpx.URL(FORM_URL).join(str(form.get("action"))))
    return action, payload


def download_year(client: SourceHttpClient, year: int) -> Path:
    """Download one bounded Mexico year and preserve the returned ZIP unchanged."""

    source_url = logical_source_url(year)
    existing = find_bronze_by_source_url(source_url)
    current_year = datetime.now(UTC).year
    if existing is not None and year < current_year:
        return existing[0]
    form_response = client.request("GET", FORM_URL)
    action, payload = _post_payload(form_response.text, year=year)
    response = client.request("POST", action, data=payload)
    if not response.content.startswith(b"PK"):
        raise ValueError(
            f"BTS did not return a ZIP for {year}; content-type="
            f"{response.headers.get('content-type')}"
        )
    if (
        existing is not None
        and hashlib.sha256(response.content).hexdigest() == str(existing[1]["sha256"])
    ):
        return existing[0]
    return save_bronze(
        response.content,
        "bts_t100",
        "international_segment_all_carriers_mexico",
        str(year),
        "zip",
        source_url,
        "httpx",
        http_status=response.status_code,
        content_type=response.headers.get("content-type", "application/zip"),
        downloaded_at=datetime.now(UTC),
        notes=(
            "BTS 28IS T-100 International Segment All Carriers; geography=Mexico; "
            f"year={year}; all months; selected fields={','.join(FIELDS)}."
        ),
        relative_dir=f"bts/t100/{year}",
    )


def ingest_t100(start_year: int = 2015, end_year: int | None = None) -> dict[str, object]:
    end = end_year or datetime.now(UTC).year
    if start_year < 1990 or end < start_year:
        raise ValueError("Invalid T-100 year range")
    paths: list[Path] = []
    with SourceHttpClient("bts", timeout_seconds=180, max_attempts=5) as client:
        for year in range(start_year, end + 1):
            paths.append(download_year(client, year))
    return {"years": len(paths), "start_year": start_year, "end_year": end}


def main() -> int:
    print(json.dumps(ingest_t100(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
