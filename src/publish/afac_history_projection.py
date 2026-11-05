"""Native AFAC history correction with a fixed, two-payload projection.

Original source replay is private. Public verification consumes only the exact
reconciled projection bound by the independent data-exposure authority.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import duckdb
from jsonschema import Draft202012Validator

from src.config import PATHS
from src.dashboard.market import build_market_payload
from src.parse.afac.market_scope import TOTAL_FORMULA, TOTAL_KEY, market_cells
from src.parse.afac.monthly_stats import _load_crosswalk, parse_annual_passenger_workbook
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.schemas import split_flight_schemas
from src.web_export.writer import dumps_deterministic

from .afac_native_monthly import project_monthly_series
from .source_data_update import file_ref

PRODUCT = "afac_carriers_history"
PERIOD = "2026M09"
TARGETS = ("data/v1/flights/quarters.json", "data/v1/market.json")
GRANULAR_PATHS = {
    TARGETS[0]: (
        "/monthly_passengers/records",
        "/monthly_passengers/period_end",
        "/monthly_passengers/observed_months",
        "/monthly_passengers/calendar_months",
        "/monthly_passengers/as_of",
        "/monthly_passengers/eligibility_reason",
    ),
    TARGETS[1]: ("",),
}
YEARS = tuple(range(2019, 2027))
GROUPS = {"AEROMEXICO", "VIVA_AEROBUS", "VOLARIS"}
PROFILE = "afac_history_source_profile_v1"
PROJECTION = "afac_history_native_projection_v1"


def encoded(value):
    return (dumps_deterministic(value) + "\n").encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _time(value):
    if not isinstance(value, str):
        raise ValueError("Source/candidate time must be a zoned ISO string")
    at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if at.tzinfo is None or at > datetime.now(UTC):
        raise ValueError("AFAC source/candidate time must retain a real zone and cannot be future-dated")
    return at


def read_sources(profile, repo=PATHS.root):
    if (
        not isinstance(profile, dict)
        or set(profile) != {"schema_version", "candidate_as_of", "crosswalk", "sources"}
        or profile["schema_version"] != PROFILE
        or not isinstance(profile["sources"], list)
        or any(not isinstance(row, dict) for row in profile["sources"])
        or [row.get("year") for row in profile["sources"]] != list(YEARS)
    ):
        raise ValueError("AFAC history requires exactly the eight declared annual originals")
    as_of = _time(profile["candidate_as_of"])
    crosswalk = file_ref(profile["crosswalk"], repo)
    if crosswalk != repo / "data/reference/carrier_crosswalk.csv":
        raise ValueError("Use the exact committed carrier crosswalk for the native annual parser")
    loaded, files = [], {str(crosswalk)}
    for row in profile["sources"]:
        if set(row) != {"year", "through", "workbook", "metadata", "capture_manifest"}:
            raise ValueError("Unknown or incomplete annual source fields")
        year, through = row["year"], row["through"]
        if type(year) is not int or type(through) is not int or through != (9 if year == 2026 else 12):
            raise ValueError("Retain seven complete historical years and the exact September 2026 cut")
        workbook, sidecar, capture = (
            file_ref(row[key], repo) for key in ("workbook", "metadata", "capture_manifest")
        )
        if sidecar != workbook.with_suffix(workbook.suffix + ".meta.json"):
            raise ValueError("Capture sidecar must belong to the exact original workbook")
        metadata = json.loads(sidecar.read_bytes())
        captured = _time(metadata["downloaded_at"])
        logical = metadata.get("logical_key", "").split("|")
        url_year = bool(re.search(rf"(?<!\d){year}(?!\d)", metadata.get("source_url", "")))
        # This retained official original uses its documented two-digit name.
        if year == 2019 and metadata.get("source_url", "").endswith("/resumen-historico-dic-19.xlsx"):
            url_year = True
        if (
            metadata.get("source_system") != "afac"
            or metadata.get("sha256") != row["workbook"]["sha256"]
            or metadata.get("bytes") != workbook.stat().st_size
            or metadata.get("http_status") != 200
            or metadata.get("download_method") not in {"computer_use", "httpx"}
            or not metadata.get("source_url", "").startswith(
                "https://www.gob.mx/cms/uploads/attachment/file/"
            )
            or not url_year
            or len(logical) != 4
            or logical[0] != "afac"
            or logical[2] != (str(year) if year != 2026 else PERIOD)
            or not metadata["source_url"].lower().endswith(".xlsx")
            or captured < datetime(year, 1, 1, tzinfo=UTC)
            or captured > as_of
        ):
            raise ValueError("Original AFAC identity, official URL, bytes or chronology differs")
        if not any(json.loads(line) == metadata for line in capture.read_text(encoding="utf-8").splitlines()):
            raise ValueError("Original capture is absent from its retained physical manifest")
        facts, checks = parse_annual_passenger_workbook(workbook, year)
        cells, receipt = market_cells(facts, checks, year, through, _load_crosswalk())
        loaded.append((row, metadata, cells, receipt))
        files.update(map(str, (workbook, sidecar, capture)))
    return loaded, sorted(files)


def _projection(loaded, as_of):
    cells, editions = [], []
    for source, metadata, native, receipt in loaded:
        year = source["year"]
        editions.append(
            {
                "year": year,
                "through": source["through"],
                "source_sha256": source["workbook"]["sha256"],
                "source_file": metadata["source_file"],
                "captured_at": metadata["downloaded_at"],
                "native_total_checks": receipt["checks"],
                "total_formula": receipt["total_formula"],
                "unmapped_in_denominator": receipt["unmapped_in_denominator"],
            }
        )
        cells.extend(
            {"carrier_key": carrier, "period_id": period, "segment": segment, "value": value}
            for (carrier, period, segment), value in sorted(native.items())
        )
    return {
        "schema_version": PROJECTION,
        "candidate_as_of": as_of,
        "source_editions": editions,
        "cells": cells,
    }


def _validate_projection(projection):
    if (
        not isinstance(projection, dict)
        or set(projection) != {"schema_version", "candidate_as_of", "source_editions", "cells"}
        or projection["schema_version"] != PROJECTION
        or not isinstance(projection["source_editions"], list)
        or not isinstance(projection["cells"], list)
        or any(not isinstance(row, dict) for row in projection["source_editions"])
        or [row.get("year") for row in projection["source_editions"]] != list(YEARS)
    ):
        raise ValueError("Unknown or incomplete native history projection")
    as_of = _time(projection["candidate_as_of"])
    editions = {}
    for edition in projection["source_editions"]:
        if set(edition) != {
            "year",
            "through",
            "source_sha256",
            "source_file",
            "captured_at",
            "native_total_checks",
            "total_formula",
            "unmapped_in_denominator",
        }:
            raise ValueError("Unknown annual projection provenance")
        year = edition["year"]
        through = 9 if year == 2026 else 12
        if (
            type(year) is not int
            or type(edition["through"]) is not int
            or type(edition["native_total_checks"]) is not int
            or edition["through"] != through
            or edition["native_total_checks"] != through * 4
            or edition["total_formula"] != TOTAL_FORMULA
            or not isinstance(edition["source_sha256"], str)
            or not re.fullmatch("[a-f0-9]{64}", edition["source_sha256"])
            or _time(edition["captured_at"]) > as_of
            or not isinstance(edition["source_file"], str)
            or not edition["source_file"].startswith("afac/")
            or not edition["source_file"].endswith(".xlsx")
            or ".." in Path(edition["source_file"]).parts
            or "\\" in edition["source_file"]
            or not isinstance(edition["unmapped_in_denominator"], list)
            or any(not isinstance(name, str) or not name for name in edition["unmapped_in_denominator"])
        ):
            raise ValueError("Annual projection lacks its exact reconciled source scope")
        editions[year] = edition
    values = {}
    for row in projection["cells"]:
        if not isinstance(row, dict) or set(row) != {"carrier_key", "period_id", "segment", "value"}:
            raise ValueError("Native cell contains an undeclared field")
        key = (row["carrier_key"], row["period_id"], row["segment"])
        if (
            not all(isinstance(item, str) for item in key)
            or key in values
            or not re.fullmatch(r"(?:2019|202[0-6])M(?:0[1-9]|1[0-2])", key[1])
            or key[2] not in {"domestic", "international", "total"}
            or not re.fullmatch(r"[A-Za-z0-9_]+", key[0])
            or "FOREIGN" in key[0].upper()
            or type(row["value"]) not in {int, float}
            or not math.isfinite(row["value"])
            or row["value"] < 0
            or not float(row["value"]).is_integer()
            or int(key[1][-2:]) > editions[int(key[1][:4])]["through"]
        ):
            raise ValueError("Native cell identity, scope or passenger count is invalid")
        values[key] = float(row["value"])
    for year, edition in editions.items():
        for month in range(1, edition["through"] + 1):
            period = f"{year}M{month:02d}"
            for segment in ("domestic", "international", "total"):
                group = {
                    carrier: value for (carrier, p, s), value in values.items() if (p, s) == (period, segment)
                }
                if (
                    not GROUPS | {TOTAL_KEY} <= set(group)
                    or sum(v for k, v in group.items() if k != TOTAL_KEY) != group[TOTAL_KEY]
                ):
                    raise ValueError(
                        "Every Mexican TOTAL must equal all native operators, including unmapped charter"
                    )
            if values[(TOTAL_KEY, period, "total")] != sum(
                values[(TOTAL_KEY, period, s)] for s in ("domestic", "international")
            ):
                raise ValueError("Mexican passenger market segments do not reconcile")
    return values, editions


def _generated(projection):
    values, editions = _validate_projection(projection)
    with tempfile.TemporaryDirectory(prefix="afac-history-native-") as temporary:
        database = Path(temporary) / "native.duckdb"
        with duckdb.connect(str(database)) as connection:
            connection.execute(
                "CREATE TABLE v_carrier_default(carrier_key VARCHAR,period_id VARCHAR,"
                "segment VARCHAR,value DOUBLE,"
                "metric_key VARCHAR,period_type VARCHAR,derivation_formula VARCHAR,unit_normalized VARCHAR,"
                "source_system VARCHAR,source_file VARCHAR,source_hash VARCHAR,ingested_at TIMESTAMPTZ)"
            )
            connection.executemany(
                "INSERT INTO v_carrier_default VALUES "
                "(?,?,?,?,'passengers_afac','month',?,'count','afac',?,?,?)",
                [
                    (
                        carrier,
                        period,
                        segment,
                        value,
                        TOTAL_FORMULA,
                        editions[int(period[:4])]["source_file"],
                        editions[int(period[:4])]["source_sha256"],
                        editions[int(period[:4])]["captured_at"],
                    )
                    for (carrier, period, segment), value in sorted(values.items())
                ],
            )
            connection.execute(
                "CREATE TABLE dim_source_artifact(source_system VARCHAR,downloaded_at TIMESTAMPTZ)"
            )
            connection.executemany(
                "INSERT INTO dim_source_artifact VALUES ('afac',?)",
                [(edition["captured_at"],) for edition in editions.values()],
            )
        return build_market_payload(str(database)), values, editions


def public_outputs(before, projection):
    if set(before) != set(TARGETS):
        raise ValueError("AFAC history has exactly two output targets")
    quarters, old_market = (json.loads(before[name]) for name in TARGETS)
    market, values, editions = _generated(projection)
    old_months = {row["period_id"]: row for row in old_market["months"]}
    new_months = {row["period_id"]: row for row in market["months"]}
    if set(new_months) != set(old_months) or any(
        new_months[p] != old_months[p] for p in old_months if p.startswith("2026")
    ):
        raise ValueError("Current 2026 market observations changed or an unrelated observation period moved")
    if {k: v for k, v in old_market["metadata"].items() if k != "method_note"} != {
        k: v for k, v in market["metadata"].items() if k != "method_note"
    }:
        raise ValueError("History correction changed unrelated current market metadata")
    old_series = quarters["monthly_passengers"]
    old = {row["period_id"]: row for row in old_series["records"]}
    if len(old) != len(old_series["records"]) or max(old) != "2026M08" or PERIOD in old:
        raise ValueError("History correction must retain its exact parent AFAC monthly boundary")
    for period, row in old.items():
        if period.startswith("2026"):
            expected = {
                segment: values[("AEROMEXICO", period, segment)]
                for segment in ("domestic", "international", "total")
            }
            if (
                any(
                    row[field] != expected[segment]
                    for field, segment in (
                        ("domestic", "domestic"),
                        ("international", "international"),
                        ("reported_total", "total"),
                        ("total_segment_sum", "total"),
                    )
                )
                or row["reconciliation_delta"] != 0
            ):
                raise ValueError("Retained 2026 AFAC passenger values differ from their original source")
    sources = {
        year: {
            "sha256": edition["source_sha256"],
            "downloaded_at": edition["captured_at"],
            "through": edition["through"],
        }
        for year, edition in editions.items()
    }
    result = project_monthly_series(quarters, values, sources)
    after = {row["period_id"]: row for row in result["monthly_passengers"]["records"]}
    if set(after) != set(old) | {PERIOD} or any(
        row != after[period] for period, row in old.items() if period < "2019M01" or period.startswith("2026")
    ):
        raise ValueError("History correction changed a retained AFAC observation or an unrelated period")
    if {k: v for k, v in result.items() if k != "monthly_passengers"} != {
        k: v for k, v in quarters.items() if k != "monthly_passengers"
    }:
        raise ValueError("History correction changed a non-AFAC flight surface")
    for name, payload in ((TARGETS[0], result), (TARGETS[1], market)):
        schema = json.loads(
            (
                PATHS.root
                / "contracts/web"
                / ("flights.schema.json" if name == TARGETS[0] else "market.schema.json")
            ).read_bytes()
        )
        if name == TARGETS[0]:
            schema = split_flight_schemas(schema)[0]
        Draft202012Validator(schema).validate(payload)
        check_privacy(payload, load_privacy_rules())
    return {TARGETS[0]: encoded(result), TARGETS[1]: encoded(market)}


def replay(profile, candidate_parent):
    loaded, files = read_sources(profile)
    projection = _projection(loaded, profile["candidate_as_of"])
    before = {name: (Path(candidate_parent) / name).read_bytes() for name in TARGETS}
    outputs = public_outputs(before, projection)
    native_sha = sha(encoded(projection))
    receipt = sha(
        encoded(
            {
                "profile": profile,
                "parent": {name: sha(raw) for name, raw in before.items()},
                "native": native_sha,
            }
        )
    )
    return {
        "source_binding": {
            "product": PRODUCT,
            "period": PERIOD,
            "receipt_id": receipt,
            "candidate_as_of": profile["candidate_as_of"],
            "output_sha256": {"afac_history_native_cells": native_sha},
        },
        "projection": projection,
        "input_files": files,
        "outputs": outputs,
    }
