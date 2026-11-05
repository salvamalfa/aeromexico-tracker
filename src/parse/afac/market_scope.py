"""Mexican-carrier scope reconciled against the native annual TOTAL rows.

Unknown identities retain their native nationality and a stable source key.
They are never assigned to Mexico just because the crosswalk lacks a match.
"""

import hashlib
import json
import math
from collections import defaultdict

from src.parse.afac.monthly_stats import _mapped_carrier, _normalize

TOTAL_FORMULA = "AFAC_MEXICAN_NATIVE_TOTAL_V2:scheduled+charter;foreign_excluded;exact_reconciliation"
RETAINED_TOTAL_FORMULA = "AFAC_MEXICAN_RETAINED_TOTAL_V2:published_baseline;not_recertified"
TOTAL_KEY = "MARKET_TOTAL_MX"


def cells_sha256(cells):
    """Canonical native/Gold cell identity, compact sorted JSON plus one LF."""
    rows = [
        dict(carrier_key=key, period_id=period, segment=segment, value=float(value))
        for (key, period, segment), value in sorted(cells.items())
    ]
    return hashlib.sha256(
        (
            json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
            + "\n"
        ).encode()
    ).hexdigest()


def carrier_identity(row, crosswalk):
    """Map exact identities, preserving distinct unknown Mexican/foreign names."""
    key, iata = _mapped_carrier(crosswalk, row["source_carrier_name"], int(row["year"]), int(row["month"]))
    if key:
        return key, iata
    nationality = "MX" if row["is_domestic_carrier"] is True else "FOREIGN"
    digest = hashlib.sha256(_normalize(row["source_carrier_name"]).encode()).hexdigest()[:16]
    return f"OTHER_AFAC_{nationality}_{digest}", None


def market_cells(facts, checks, year, through, crosswalk):
    """Return reconciled market cells and proof; raw parser data stays unchanged.

    Four unique TOTALs are required per month: scheduled/charter × domestic/
    international, explicitly within the native Mexican-carrier section.
    Recompute totals independently from facts rather than trusting check flags.
    Connect is consolidated only in this market projection.
    """
    if not 1 <= through <= 12:
        raise ValueError("AFAC coverage must contain 1..12 months")
    domestic = [row for row in facts if row["is_domestic_carrier"] is True]
    if not domestic or any(int(row["year"]) != year for row in facts):
        raise ValueError("AFAC native facts have missing or mixed annual coverage")
    if any(not math.isfinite(float(row["value"])) or row["value"] < 0 for row in facts):
        raise ValueError("AFAC native passenger cells must be finite and nonnegative")
    observed = max(int(row["month"]) for row in domestic if row["value"] > 0)
    if observed != through:
        raise ValueError("Requested coverage differs from observed workbook coverage")
    totals = {}
    for row in checks:
        if row["is_domestic_carrier"] is not True or int(row["period_id"][-2:]) > through:
            continue
        month = int(row["period_id"][-2:])
        key = (month, row["service_type"], row["market"])
        expected = float(row["expected"])
        actual = sum(
            float(fact["value"])
            for fact in domestic
            if (int(fact["month"]), fact["service_type"], fact["market"]) == key
        )
        if (
            row["period_id"] != f"{year}M{month:02d}"
            or key in totals
            or not math.isfinite(expected)
            or expected < 0
            or expected != actual
            or float(row["actual"]) != actual
            or float(row["difference"]) != 0
        ):
            raise ValueError("AFAC published Mexican TOTAL does not reconcile exactly")
        totals[key] = expected
    required = {
        (month, service, market)
        for month in range(1, through + 1)
        for service in ("scheduled", "charter")
        for market in ("domestic", "international")
    }
    if set(totals) != required:
        raise ValueError("AFAC native Mexican TOTAL coverage is incomplete")
    values = defaultdict(float)
    unmapped = set()
    for row in domestic:
        month = int(row["month"])
        if month > through:
            continue
        if (month, row["service_type"], row["market"]) not in totals:
            raise ValueError("AFAC fact lies outside the reconciled native scope")
        key, _ = carrier_identity(row, crosswalk)
        if key.startswith("OTHER_AFAC_"):
            unmapped.add(row["source_carrier_name"])
        if key == "AEROMEXICO_CONNECT":
            key = "AEROMEXICO"
        period = f"{year}M{month:02d}"
        values[(key, period, row["market"])] += float(row["value"])
        values[(key, period, "total")] += float(row["value"])
    for month in range(1, through + 1):
        period = f"{year}M{month:02d}"
        for market in ("domestic", "international"):
            total = sum(totals[(month, service, market)] for service in ("scheduled", "charter"))
            values[(TOTAL_KEY, period, market)] = total
        values[(TOTAL_KEY, period, "total")] = sum(
            values[(TOTAL_KEY, period, market)] for market in ("domestic", "international")
        )
    return dict(values), dict(
        year=year,
        through=through,
        checks=len(totals),
        all_reconciled=True,
        total_formula=TOTAL_FORMULA,
        unmapped_in_denominator=sorted(unmapped),
    )
