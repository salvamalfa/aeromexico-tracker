"""Conservative normalization: retain legacy ambiguity and separate money from points."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

PROVIDERS = {"AMR", "DOTERS", "VOLARIS"}
STATUSES = {
    "ok",
    "partial_redemption",
    "no_availability",
    "access_blocked",
    "login_required",
    "error",
    "legacy_unverified",
}
AMOUNTS = (
    "cash_final_mxn",
    "points",
    "redemption_cash_mxn",
    "redemption_taxes_mxn",
    "redemption_carrier_mxn",
    "cash_carrier_mxn",
    "cash_taxes_mxn",
    "legacy_regular_mxn",
)
TEXT_FIELDS = (
    "outbound_departure_time",
    "outbound_arrival_time",
    "return_departure_time",
    "return_arrival_time",
    "outbound_flight",
    "return_flight",
    "fare",
    "conditions",
    "evidence",
    "capture_id",
    "run_id",
    "notes",
)
AMR_COLUMNS = (
    "query_date",
    "origin",
    "destination",
    "departure_date",
    "return_date",
    "outbound_departure_time",
    "return_departure_time",
    "fare",
    "promotion",
    "points",
    "redemption_taxes_mxn",
    "cash_carrier_mxn",
    "cash_taxes_mxn",
    "points_accrual",
)
DOTERS_COLUMNS = (*AMR_COLUMNS[:7], "legacy_regular_mxn", "points")


def provider_key(value: str) -> str:
    aliases = {
        "amr": "AMR",
        "aeromexico": "AMR",
        "aeroméxico": "AMR",
        "doters": "DOTERS",
        "viva": "DOTERS",
        "volaris": "VOLARIS",
    }
    return aliases.get(value.strip().casefold(), value) if isinstance(value, str) else value


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def text(value: object) -> str | None:
    if value is None or str(value).strip().casefold() in {"", "null", "n/a", "n/d", "no aplica"}:
        return None
    return str(value).strip()


def iso_date(value: object) -> str | None:
    value = text(value)
    if value is None:
        return None
    for pattern in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Invalid calendar date: {value}")


def amount(value: object, *, integer: bool = False) -> int | float | None:
    raw = text(value)
    if raw is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Boolean is not an amount")
    # Locale is explicit: MXN and English comma thousands, never guess decimal commas.
    raw = re.sub(r"\s*(MXN|MX\$|\$)\s*", "", raw, flags=re.I)
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d{1,2})?", raw):
        raise ValueError(f"Ambiguous amount: {value}")
    try:
        parsed = Decimal(raw.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"Invalid amount: {value}") from exc
    if not parsed.is_finite() or parsed < 0 or (integer and parsed != parsed.to_integral_value()):
        raise ValueError(f"Invalid amount: {value}")
    return int(parsed) if integer else float(parsed)


def canonical_row(
    raw: dict, provider: str, *, legacy: bool = False, verification: dict | None = None
) -> dict:
    provider = provider_key(provider)
    if provider not in PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    raw = dict(raw)
    for alias, name in {
        "outbound_time": "outbound_departure_time",
        "return_time": "return_departure_time",
        "evidence_url": "evidence",
        "capture_key": "capture_id",
    }.items():
        if name not in raw:
            raw[name] = raw.get(alias)
    notes = raw.get("notes")
    details = {}
    if isinstance(notes, str) and notes.startswith("{"):
        details = json.loads(notes)
        raw.setdefault(
            "redemption_carrier_mxn", details.get("award_carrier_cash_mxn", details.get("award_carrier_cash"))
        )
        for key in ("outbound_arrival_time", "return_arrival_time"):
            raw.setdefault(key, details.get(key))
    if verification:
        details["airport_verification"] = verification
        raw["notes"] = json.dumps(details, ensure_ascii=False, sort_keys=True)
    if text(raw.get("provider")) and provider_key(raw["provider"]) != provider:
        raise ValueError("Row provider contradicts snapshot")
    captured_at = text(raw.get("captured_at"))
    query_date = iso_date(raw.get("query_date"))
    if captured_at:
        timestamp = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("captured_at requires a timezone")
        observed_date = timestamp.astimezone(ZoneInfo("America/Mexico_City")).date().isoformat()
        if query_date and query_date != observed_date:
            raise ValueError("query_date disagrees with captured_at in Mexico City")
        query_date = observed_date
    if not query_date:
        raise ValueError("query_date or captured_at is required")
    normalized = dict(
        provider=provider,
        query_date=query_date,
        captured_at=captured_at,
        period_id=f"{query_date[:4]}Q{(int(query_date[5:7]) - 1) // 3 + 1}",
    )
    for key in ("origin", "destination"):
        code = (text(raw.get(key)) or "").upper()
        if not re.fullmatch("[A-Z]{3}", code):
            raise ValueError(f"{key} must be an explicit IATA airport")
        normalized[key] = code
    if normalized["origin"] == normalized["destination"]:
        raise ValueError("Origin and destination must differ")
    for key in ("departure_date", "return_date"):
        normalized[key] = iso_date(raw.get(key))
    departure, returning = normalized["departure_date"], normalized["return_date"]
    if not departure or (returning and returning < departure):
        raise ValueError("Invalid itinerary dates")
    # Historical captures are legitimate even when the trip is now in the past.
    date.fromisoformat(departure)
    for key in AMOUNTS:
        normalized[key] = amount(raw.get(key), integer=key == "points")
    if provider == "VOLARIS" and normalized["points"] is not None:
        raise ValueError("Volaris points must be null, including when the source says zero")
    normalized["points_applicability"] = "not_applicable" if provider == "VOLARIS" else "applicable"
    for key in TEXT_FIELDS:
        normalized[key] = text(raw.get(key))
    for key in TEXT_FIELDS[:4]:
        if normalized[key] and legacy:
            for pattern in ("%H:%M", "%I:%M %p"):
                try:
                    normalized[key] = datetime.strptime(normalized[key], pattern).strftime("%H:%M")
                    break
                except ValueError:
                    pass
        if normalized[key] and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", normalized[key]):
            raise ValueError(f"Invalid local flight time: {key}")
    normalized["status"] = "legacy_unverified" if legacy else text(raw.get("status")) or "error"
    normalized["status"] = {"partial": "partial_redemption", "captured": "ok"}.get(
        normalized["status"], normalized["status"]
    )
    if normalized["status"] not in STATUSES:
        raise ValueError("Unknown capture status")
    if legacy:
        # A historic carrier amount may exclude taxes or already contain them. No invented total.
        normalized["cash_final_mxn"] = None
        normalized["redemption_cash_mxn"] = None
    if normalized["status"] in {"ok", "partial_redemption"}:
        if normalized["cash_final_mxn"] is None or not normalized["evidence"]:
            raise ValueError("Verified cash capture requires final MXN and evidence")
        if provider != "VOLARIS" and normalized["status"] == "ok":
            if normalized["points"] is None or normalized["redemption_cash_mxn"] is None:
                raise ValueError("Complete points capture requires points and final redemption payment")
        # A booking URL that explicitly names another airport is conflicting evidence.
        itinerary = parse_qs(urlparse(normalized["evidence"]).query).get("itineraryCode", [""])[0]
        match = re.match(r"([A-Z]{3})_([A-Z]{3})_\d{8}", itinerary)
        if match and (match[1], match[2]) != (normalized["origin"], normalized["destination"]):
            selected = verification or {}
            if not (
                selected.get("basis") == "selected_flight_summary"
                and selected.get("origin") == normalized["origin"]
                and selected.get("destination") == normalized["destination"]
                and selected.get("outbound_flight") == normalized["outbound_flight"]
                and selected.get("return_flight") == normalized["return_flight"]
            ):
                raise ValueError("Search URL airports differ; selected flight summary verification required")
    normalized["observation_id"] = digest(normalized)
    return normalized


def decode_snapshot(snapshot: dict, verifications: dict | None = None) -> tuple[list[dict], list[dict]]:
    provider = provider_key(snapshot.get("provider"))
    if provider not in PROVIDERS:
        raise ValueError("Snapshot requires provider AMR, DOTERS or VOLARIS")
    required = ("spreadsheet_id", "sheet_name", "range", "fetched_at", "values")
    if any(key not in snapshot for key in required):
        raise ValueError("Snapshot missing source identity, range, fetched_at or values")
    if not isinstance(snapshot["values"], list):
        raise ValueError("Snapshot values must be an array")
    values = snapshot["values"]
    if not values:
        return [], []
    legacy = snapshot.get("format") in {"amr_legacy_v1", "doters_legacy_v1"}
    headers = (
        (AMR_COLUMNS if snapshot.get("format") == "amr_legacy_v1" else DOTERS_COLUMNS)
        if legacy
        else tuple(str(x).strip() for x in values[0])
    )
    if not legacy and len(headers) != len(set(headers)):
        raise ValueError("Duplicate headers")
    if not legacy and not {"origin", "destination", "departure_date"} <= set(headers):
        raise ValueError("Use canonical headers or explicit format amr_legacy_v1")
    start_row = int(snapshot.get("start_row", 1))
    rows, rejected = [], []
    data_rows = values if legacy and snapshot.get("has_header") is False else values[1:]
    offset = start_row if data_rows is values else start_row + 1
    for index, cells in enumerate(data_rows, offset):
        if not any(text(cell) is not None for cell in cells[: len(headers)]):
            continue
        source = dict(
            spreadsheet_id=snapshot["spreadsheet_id"],
            sheet_name=snapshot["sheet_name"],
            row=index,
            fetched_at=snapshot["fetched_at"],
        )
        try:
            fields = dict(zip(headers, cells))
            key = fields.get("capture_key", fields.get("capture_id"))
            verification = (verifications or {}).get((provider, key))
            row = canonical_row(fields, provider, legacy=legacy, verification=verification)
            rows.append(dict(**row, sources=[source], raw_source_row=cells))
        except (ValueError, TypeError) as exc:
            rejected.append(dict(source=source, reason=str(exc), raw_source_row=cells))
    return rows, rejected
