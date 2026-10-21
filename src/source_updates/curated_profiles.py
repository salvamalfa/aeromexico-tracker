"""Edition-scoped candidate metrics and entity contracts from retained primary reports.

This reader resolves source units rather than applying the carrier-wide unit flag.
It never edits profiles, active Gold, approval ledgers or operator crosswalks.
Only the two explicitly reviewed editions are supported; another edition fails
closed until its headers, definitions, entity scope and columns are reviewed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from lxml import html
from pypdf import PdfReader

from src.source_updates import primary_review
from src.source_updates.calendar import local_time
from src.source_updates.catalog import ROOT
from src.source_updates.collection import safe_workspace, writer

VERSION = "curated_native_metrics_v1"
EDITIONS = {
    "ry_annual": "2d82d224df2c0379dfcc69c11c1cf8828c55db57599b01fa912b70aa2e6bed5d",
    "viva_q2": "4fca922642ce3fe06743578064239107539b0546c1519a11abecb0eef098bc7f",
}
OUTPUTS = (
    "silver/curated_native_metrics.json",
    "gold/curated_native_metrics.json",
    "curated-profile-receipt.json",
)
KEYS = ("entity_id", "period", "metric")
NATIVE_UNITS = {
    ("ry_annual", "asm"): ("seat_miles", "1000000000"),
    ("ry_annual", "average_sector_length"): ("miles", "1"),
    ("ry_annual", "passengers_booked"): ("booked_passengers", "1000000"),
    ("ry_annual", "load_factor_booked"): ("fraction", "0.01"),
    ("viva_q2", "total_operating_revenue"): ("USD", "1000"),
    ("viva_q2", "asm"): ("seat_miles", "1000000"),
    ("viva_q2", "rpm"): ("revenue_passenger_miles", "1000000"),
    ("viva_q2", "passengers_booked"): ("booked_passengers", "1000"),
    ("viva_q2", "load_factor_scheduled"): ("fraction", "0.01"),
    ("viva_q2", "trasm"): ("USD_cents_per_seat_mile", "1"),
    ("viva_q2", "casm"): ("USD_cents_per_seat_mile", "1"),
}


def encoded(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def number(token: str) -> Decimal:
    if not isinstance(token, str) or not re.fullmatch(r"-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", token):
        raise ValueError("Explicit finite source number required; missing is not zero")
    try:
        result = Decimal(token.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError("Invalid source number") from exc
    if not result.is_finite():
        raise ValueError("Invalid source number")
    return result


def cell(text: str, pattern: str) -> tuple[str, dict]:
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError("Expected exactly one edition-scoped metric row and current-period column")
    match = matches[0]
    return match.group("value"), {
        "normalized_char_start": match.start(),
        "normalized_char_end": match.end(),
        "excerpt": match.group(),
    }


def metric(
    source: dict,
    source_id: str,
    text: str,
    pattern: str,
    *,
    name: str,
    raw_unit: str,
    unit: str,
    scale: str,
    entity: str,
    period: str,
    start: str,
    end: str,
    definition: str,
    page: int | None = None,
) -> dict:
    token, locator = cell(text, pattern)
    number(token)
    if page is not None:
        locator["pdf_page_1based"] = page
    return {
        "entity_id": entity,
        "period": period,
        "period_start": start,
        "period_end": end,
        "metric": name,
        "value_raw": token,
        "unit_raw": raw_unit,
        "unit_normalized": unit,
        "scale_multiplier": scale,
        "definition": definition,
        "value_kind": "reported",
        "entity_scope": "issuer_consolidated_report",
        "operating_carrier_iata": None,
        "operating_carrier_icao": None,
        "source_id": source_id,
        "source_system": source["source_system"],
        "source_file": source["source_file"],
        "source_url": source["source_url"],
        "source_sha256": source["sha256"],
        "captured_at": source["downloaded_at"],
        "locator": locator,
        "publication_date": None,
        "release_lag_days": None,
        "parser_version": VERSION,
    }


def validate(records: list[dict], *, normalized=False) -> None:
    seen = set()
    for row in records:
        key = tuple(row[k] for k in KEYS)
        if key in seen:
            raise ValueError("Duplicate candidate metric grain")
        seen.add(key)
        contract = NATIVE_UNITS.get((row["source_id"], row["metric"]))
        if contract != (row["unit_normalized"], row["scale_multiplier"]):
            raise ValueError("Metric-specific native unit/scale contract mismatch")
        if (
            row["source_id"] not in EDITIONS
            or row["source_sha256"] != EDITIONS[row["source_id"]]
            or row["entity_scope"] != "issuer_consolidated_report"
            or row["operating_carrier_iata"] is not None
            or row["operating_carrier_icao"] is not None
        ):
            raise ValueError("Unverified edition or operator attribution")
        if row["source_id"] == "ry_annual" and (
            row["entity_id"] != "RYANAIR_HOLDINGS_CONSOLIDATED"
            or row["period"] != "FY2026"
            or (row["period_start"], row["period_end"]) != ("2025-04-01", "2026-03-31")
        ):
            raise ValueError("Ryanair annual issuer scope must not be relabeled as calendar quarter")
        if row["source_id"] == "viva_q2" and (
            row["entity_id"] != "GRUPO_VIVA_AEROBUS_CONSOLIDATED"
            or row["period"] != "2026Q2"
            or (row["period_start"], row["period_end"]) != ("2026-04-01", "2026-06-30")
        ):
            raise ValueError("Viva issuer report must not be relabeled as operating subsidiary")
        value = number(row["value_raw"]) * number(row["scale_multiplier"])
        if value < 0:
            raise ValueError("Negative source metric is outside this reader's domain")
        if row["unit_normalized"] == "fraction" and not 0 <= value <= 1:
            raise ValueError("Load factor outside unit interval")
        if normalized and row.get("value_normalized") != str(value):
            raise ValueError("Normalized value does not match native source token and explicit scale")
        if row["publication_date"] is not None or row["release_lag_days"] is not None:
            raise ValueError("Document date is not verified first publication or release lag")
    if {(row["source_id"], row["metric"]) for row in records} != set(NATIVE_UNITS):
        raise ValueError("Candidate is missing a required edition-scoped metric")


def extract(bundle: dict, roots: dict[str, Path], repository: Path) -> tuple[list[dict], dict]:
    verification = primary_review.verify(bundle, roots, repository)
    for key, expected in EDITIONS.items():
        if bundle["sources"][key]["sha256"] != expected:
            raise ValueError("Report edition has not been reviewed by this candidate reader")
    paths = {
        key: primary_review.original(
            roots[bundle["sources"][key].get("root_id", "old_public")], bundle["sources"][key]
        )
        for key in EDITIONS
    }
    ry = primary_review.normalize(" ".join(html.fromstring(paths["ry_annual"].read_bytes()).itertext()))
    pages = PdfReader(paths["viva_q2"])
    if len(pages.pages) != 12:
        raise ValueError("Viva edition pagination changed")
    viva = primary_review.normalize(pages.pages[6].extract_text())
    required = (
        (ry, "Fiscal year ended March 31 2026 2025 2024 2023 2022"),
        (viva, "Grupo Viva Aerobus, S.A. de C.V. and Subsidiaries"),
        (viva, "Three-month period ended June 30, 2026 and 2025"),
        (viva, "Financial Information in Thousands of U.S. Dollars, unless otherwise stated"),
        (viva, "2Q 2026 2Q 2025 % Var"),
    )
    if any(phrase not in text for text, phrase in required):
        raise ValueError("Report entity, column, period or scale header changed")
    rows = []

    def add(source_id, text, pattern, name, raw_unit, unit, scale, definition):
        is_viva = source_id == "viva_q2"
        rows.append(
            metric(
                bundle["sources"][source_id],
                source_id,
                text,
                pattern,
                name=name,
                raw_unit=raw_unit,
                unit=unit,
                scale=scale,
                definition=definition,
                entity="GRUPO_VIVA_AEROBUS_CONSOLIDATED" if is_viva else "RYANAIR_HOLDINGS_CONSOLIDATED",
                period="2026Q2" if is_viva else "FY2026",
                start="2026-04-01" if is_viva else "2025-04-01",
                end="2026-06-30" if is_viva else "2026-03-31",
                page=7 if is_viva else None,
            )
        )

    token = r"(?P<value>[\d,]+(?:\.\d+)?)"
    for pattern, name, raw_unit, unit, scale, definition in [
        (
            r"Available seat miles \(ASM\) " + token + r"bn 166bn 152bn 138bn 91bn",
            "asm",
            "billion seat miles",
            "seat_miles",
            "1000000000",
            "Seats available multiplied by average sector length in miles; no carrier-wide metric inference",
        ),
        (
            r"Average Sector Length \(miles\) " + token + r" 783 780 766 772",
            "average_sector_length",
            "miles",
            "miles",
            "1",
            "Average sector length, not kilometers",
        ),
        (
            r"Passengers Booked \(millions\) " + token + r" 200 184 169 97",
            "passengers_booked",
            "million booked passengers",
            "booked_passengers",
            "1000000",
            "Booked passengers; not evidence of passengers flown",
        ),
        (
            r"Booked Passenger Load Factor " + token + r"%",
            "load_factor_booked",
            "percent booked load factor",
            "fraction",
            "0.01",
            "Booked passenger load factor; not scheduled RPM/ASM or boarded-passenger load factor",
        ),
    ]:
        add("ry_annual", ry, pattern, name, raw_unit, unit, scale, definition)
    for label, name, raw_unit, unit, scale, definition in [
        (
            "Total operating revenue",
            "total_operating_revenue",
            "thousand USD",
            "USD",
            "1000",
            "Consolidated issuer operating revenue; page 7 thousands, not page 1 rounded millions",
        ),
        (
            "ASMs (millions)",
            "asm",
            "million seat miles",
            "seat_miles",
            "1000000",
            "Available seat miles as defined in glossary; not ASK-km",
        ),
        (
            "RPMs (millions)",
            "rpm",
            "million revenue passenger miles",
            "revenue_passenger_miles",
            "1000000",
            "Revenue passenger miles as defined in glossary; not RPK-km",
        ),
        (
            "Booked Passengers (thousands)",
            "passengers_booked",
            "thousand booked passengers",
            "booked_passengers",
            "1000",
            "Customers who purchased tickets regardless of whether they flew; not transported passengers",
        ),
        (
            "Load Factor (scheduled, RPM/ASM)",
            "load_factor_scheduled",
            "percent scheduled load factor",
            "fraction",
            "0.01",
            "Scheduled RPM divided by scheduled ASM; must not reconcile using unspecified total ASM/RPM",
        ),
        (
            "TRASM (US cents)",
            "trasm",
            "US cents per ASM",
            "USD_cents_per_seat_mile",
            "1",
            "Total revenue per available seat mile; no kilometer denominator",
        ),
        (
            "CASM (US cents)",
            "casm",
            "US cents per ASM",
            "USD_cents_per_seat_mile",
            "1",
            "Total operating expenses per ASM",
        ),
    ]:
        add("viva_q2", viva, re.escape(label) + " " + token, name, raw_unit, unit, scale, definition)
    validate(rows)
    for label, total in [
        ("ASMs (millions)", "5,789"),
        ("RPMs (millions)", "4,953"),
        ("Booked Passengers (thousands)", "7,208"),
    ]:
        match = re.search(
            re.escape(label)
            + r" (?P<total>[\d,]+) .*? Domestic (?P<domestic>[\d,]+)"
            + r" .*? International (?P<international>[\d,]+)",
            viva,
        )
        if (
            not match
            or match.group("total") != total
            or number(match.group("domestic")) + number(match.group("international"))
            != number(match.group("total"))
        ):
            raise ValueError("Viva native domestic/international totals do not reconcile")
    return rows, verification


def revision(records: list[dict], baseline: dict | None) -> dict:
    if baseline is None:
        return {"status": "not_compared_no_baseline"}
    primary_review.no_activation(baseline)
    if (
        baseline.get("schema") != VERSION
        or baseline.get("layer") != "candidate_gold"
        or baseline.get("activation") != "none"
        or baseline.get("agent_eligible") is not False
    ):
        raise ValueError("Explicit compatible ineligible candidate baseline required")
    old = baseline["records"]
    validate(old, normalized=True)
    previous = {tuple(row[k] for k in KEYS): row for row in old}
    current = {tuple(row[k] for k in KEYS): row for row in records}
    keys = previous.keys() & current.keys()
    changed = sum(previous[k] != current[k] for k in keys)
    return {
        "status": "compared_explicit_baseline",
        "added": len(current.keys() - previous.keys()),
        "removed": len(previous.keys() - current.keys()),
        "changed": changed,
        "unchanged": len(keys) - changed,
        "baseline_sha256": digest(encoded(baseline)),
        "comparison_kind": "candidate_rows_not_proof_of_new_source_revision",
    }


def build(
    bundle: dict, roots: dict[str, Path], repository: Path, *, as_of: str, baseline: dict | None = None
) -> dict:
    rows, verification = extract(bundle, roots, repository)
    cutoff = local_time(as_of)
    if any(
        local_time(row["captured_at"]) > cutoff or row["period_end"] >= cutoff.date().isoformat()
        for row in rows
    ):
        raise ValueError("Report period/capture must precede the explicit cutoff")
    normalized = [
        {**row, "value_normalized": str(number(row["value_raw"]) * number(row["scale_multiplier"]))}
        for row in rows
    ]
    validate(normalized, normalized=True)
    common = {
        "schema": VERSION,
        "agent_eligible": False,
        "activation": "none",
        "approval_granted": False,
        "source_map_canonical_sha256": digest(encoded(bundle)),
        "parser_sha256": primary_review.sha(Path(__file__)),
        "as_of": as_of,
        "latest_availability_verified": False,
    }
    silver = {**common, "layer": "candidate_silver", "records": rows}
    gold = {**common, "layer": "candidate_gold", "records": normalized}
    receipt = {
        **common,
        "layer": "candidate_receipt",
        "status": "checks_passed",
        "rows": len(rows),
        "documentary_check": verification,
        "network_requests": 0,
        "new_source_capture": False,
        "inputs": EDITIONS,
        "revision": revision(normalized, baseline),
        "outputs_sha256": {
            "silver/curated_native_metrics.json": digest(encoded(silver)),
            "gold/curated_native_metrics.json": digest(encoded(gold)),
        },
        "contracts": {
            "distance_units": "metric_specific_native_units_no_carrier_wide_conversion",
            "viva_issuer": "Grupo Viva Aerobus, S.A. de C.V. and Subsidiaries",
            "viva_subsidiary": (
                "Aeroenlaces Nacionales S.A. de C.V.; relationship only, "
                "not operator attribution of group totals"
            ),
            "viva_reporting_currency_effective": "2022-10-01",
            "viva_functional_currency_effective": "2020-01-01",
            "currency_scope": "USD for selected 2026Q2 report; no historical relabelling",
            "operator_designators": (
                "unverified_primary_registry_required_for_operator_join; nulls do not block issuer metrics"
            ),
            "comparability": (
                "booked_not_flown; annual_not_quarterly; scheduled_and_booked_load_factors_distinct"
            ),
            "publication": "document_dates_do_not_prove_first_publication; publication_and_lag_null",
        },
        "reconciliations": {
            "viva_native_segments": "ASM_RPM_booked_passengers_domestic_plus_international_equals_total",
            "scheduled_load_factor": "not_reconciled_to_total_RPM_ASM_different_scope",
        },
        "remaining_decisions": [
            "Approval and publication of any new metric version remains separate",
            "Operator-level joins require an exact primary designator registry; never infer from issuer name",
        ],
        "production_writes": 0,
        "calendar_activation": False,
    }
    return dict(zip(OUTPUTS, (silver, gold, receipt), strict=True))


def run(
    bundle: dict,
    roots: dict[str, Path],
    repository: Path,
    workspace: Path,
    *,
    as_of: str,
    execute=False,
    check=False,
    baseline=None,
) -> dict:
    workspace = safe_workspace(workspace)
    outputs = build(bundle, roots, repository, as_of=as_of, baseline=baseline)
    expected = {name: encoded(body) for name, body in outputs.items()}
    result = {
        "mode": "check" if check else "execute" if execute else "dry_run",
        "workspace": str(workspace),
        "rows": outputs[OUTPUTS[-1]]["rows"],
        "outputs": list(outputs),
        "activation": "none",
        "network_requests": 0,
    }
    if check:
        actual = {
            p.relative_to(workspace).as_posix() for p in workspace.rglob("*") if p.is_file()
        }
        if actual != set(expected) or any(
            not (workspace / name).is_file() or (workspace / name).read_bytes() != body
            for name, body in expected.items()
        ):
            raise ValueError("Offline replay differs from candidate artifacts")
        return {**result, "status": "verified_identical"}
    if not execute:
        return {**result, "status": "validated_plan", "writes": 0}
    with writer(workspace):
        existing = [p for p in workspace.iterdir() if p.name != ".source-update.lock"]
        if existing:
            actual = {
                p.relative_to(workspace).as_posix()
                for p in workspace.rglob("*")
                if p.is_file() and p != workspace / ".source-update.lock"
            }
            if actual == set(expected) and all(
                (workspace / name).is_file() and (workspace / name).read_bytes() == body
                for name, body in expected.items()
            ):
                return {**result, "status": "idempotent_existing", "writes": 0}
            raise ValueError("Candidate workspace contains different artifacts; use another workspace")
        for name, body in expected.items():
            destination = workspace / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)
    return {**result, "status": "checks_passed", "writes": len(outputs)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--root", action="append", default=[], help="ID=/path/to/originals")
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--as-of", required=True, help="Explicit timezone-aware cutoff")
    parser.add_argument("--baseline", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        roots = {k: Path(v) for k, v in (pair.split("=", 1) for pair in args.root)}
        result = run(
            json.loads(args.bundle.read_text()),
            roots,
            args.repository,
            args.workspace,
            as_of=args.as_of,
            execute=args.execute,
            check=args.check,
            baseline=json.loads(args.baseline.read_text()) if args.baseline else None,
        )
    except (ValueError, KeyError, OSError, TypeError, IndexError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "activation": "none"}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
