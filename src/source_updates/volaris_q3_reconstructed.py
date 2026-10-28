"""Preparation contracts for the authorized Volaris Q3 editable reconstruction.

These helpers validate identity and dates, not source availability or figures.
No artifact is accepted until the actual Library handoff has been verified.
The original Q2 SEC reader and its four-original contract stay separate.
"""

from datetime import UTC, datetime
from decimal import Decimal

from src.source_updates.carrier_source_contract import amount

PERIOD = "2026Q3"
ALIAS = "volaris_visible_reconstruction"
ACCESSION = "0001292814-26-005010"
DIRECTORY = "/Archives/edgar/data/1520504/000129281426005010"
DOCUMENT = "vlrspr3q26_6k.htm"
EXHIBIT = "ex99-1.htm"
URLS = {
    "exhibit": "https://www.sec.gov" + DIRECTORY + "/" + EXHIBIT,
    "primary": "https://www.sec.gov" + DIRECTORY + "/" + DOCUMENT,
    "index": "https://www.sec.gov" + DIRECTORY + "/index.json",
    "submissions": "https://data.sec.gov/submissions/CIK0001520504.json",
}
FILING = {
    "cik": "0001520504",
    "accession_number": ACCESSION,
    "form": "6-K",
    "report_date": "2026-09-30",
    "filing_date": "2026-10-27",
    "acceptance_at": "2026-10-26T21:31:25Z",
    "primary_document": DOCUMENT,
    "exhibit": EXHIBIT,
}


def zoned_timestamp(value):
    """Require explicit offsets; never invent SEC observation/publication times."""
    if not isinstance(value, str):
        raise ValueError("Volaris reconstruction timestamp must include a timezone")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Volaris reconstruction timestamp must include a timezone")
    return parsed.astimezone(UTC)


def validate_filing_context(context):
    """Check a normalized derivative context against the exact selected filing.

    SEC acceptance and filing date are different facts. Neither proves the
    first IR publication date or a successful HTTP capture of these URLs.
    """
    if not isinstance(context, dict) or set(context) != set(FILING) | {"source_urls"}:
        raise ValueError("Volaris Q3 requires its complete explicit filing context")
    if context["source_urls"] != URLS or any(
        context[key] != expected for key, expected in FILING.items() if key != "acceptance_at"
    ):
        raise ValueError("Volaris reconstructed filing identity or upstream reference changed")
    if zoned_timestamp(context["acceptance_at"]) != zoned_timestamp(FILING["acceptance_at"]):
        raise ValueError("Volaris reconstructed SEC acceptance differs")
    return dict(FILING, source_urls=dict(URLS))


def reporting_context(kind, year, *, quarter=3):
    """Reviewed windows only; Q3 must never be calculated from nine-month totals."""
    if (
        type(year) is not int
        or type(quarter) is not int
        or year not in (2025, 2026)
        or quarter not in (2, 3, 4)
    ):
        raise ValueError("Unreviewed Volaris Q3 comparative context")
    if kind == "quarter" and quarter == 3:
        return "quarter", f"{year}Q3", f"{year}-07-01", f"{year}-09-30"
    if kind == "year_to_date" and quarter == 3:
        return "year_to_date", f"{year}YTD09", f"{year}-01-01", f"{year}-09-30"
    if kind == "instant" and (year, quarter) in {(2025, 4), (2025, 3), (2026, 2), (2026, 3)}:
        end = f"{year}-" + {2: "06-30", 3: "09-30", 4: "12-31"}[quarter]
        return "instant", end, None, end
    raise ValueError("Volaris Q3 quarter/YTD/instant context cannot be substituted")


def native_value(raw, normalized, *, unit, scale):
    """Preserve source tokens and explicit units; dashes remain unknown.

    This verifies a supplied representation, not authenticity or completeness.
    The derived 5% reconciliation policy never applies to transcription.
    """
    scales = {
        "usd": (1_000_000,),
        "seat_miles": (1_000_000,),
        "passenger_miles": (1_000_000,),
        "booked_passengers": (1_000,),
        "us_gallons": (1_000_000,),
        "percent": (Decimal("0.01"),),
        "aircraft": (1,),
        "departures": (1,),
        "shares": (1,),
        "hours": (1,),
        "block_hours_per_aircraft_day": (1,),
        "usd_cents_per_seat_mile": (1,),
        "usd_per_ads": (1,),
        "usd_per_share": (1,),
        "usd_per_booked_passenger": (1,),
        "usd_per_us_gallon": (1,),
        "mxn_per_usd": (1,),
        "times_ltm": (1,),
    }
    if (
        unit not in scales
        or type(scale) not in (int, float, Decimal)
        or Decimal(str(scale)) not in scales[unit]
        or normalized is not None
        and type(normalized) not in (int, float, Decimal)
    ):
        raise ValueError("Volaris reconstructed source unit/scale is unreviewed")
    value = amount(raw)
    if (value is None) != (normalized is None) or (value is not None and Decimal(str(normalized)) != value):
        raise ValueError("Volaris normalized value must reproduce its source token exactly")
    token = raw.strip("()")
    if value is not None and (
        (unit == "percent") != token.endswith("%") or (unit == "times_ltm") != token.endswith("x")
    ):
        raise ValueError("Volaris source token suffix and unit differ")
    if value is not None and unit in {"aircraft", "departures", "shares"} and (value < 0 or value % 1):
        raise ValueError("Volaris reconstructed count must remain a nonnegative integer")
    return value


def preparation():
    """Useful offline preview, explicitly unable to certify missing artifacts."""
    return {
        "product": "volaris_sec",
        "period": PERIOD,
        "representation": ALIAS,
        "filing_context": dict(FILING, source_urls=dict(URLS)),
        "status": "prepared_waiting_verified_Library_derivatives",
        "source_original_bytes_acquired": False,
        "source_original_sha256": None,
        "source_http_status": None,
        "source_observed_at": None,
        "artifact_derivative_sha256": None,
        "native_rows_certified": 0,
        "latest_source_availability_verified": False,
        "ready_for_calendar_incorporation": False,
        "network_requests": 0,
        "activation": "none",
        "publication": "not_authorized",
    }


if __name__ == "__main__":
    import json

    print(json.dumps(preparation(), ensure_ascii=False, indent=2))
