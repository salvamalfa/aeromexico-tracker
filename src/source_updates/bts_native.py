"""Strict retained T-100 MX/US segments, native units and exact operator identities."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from zipfile import BadZipFile, ZipFile

import numpy as np
import pandas as pd

from src.source_updates.calendar import local_time
from src.source_updates.catalog import ROOT
from src.source_updates.checks import period_end
from src.transform.silver_contracts import validate_silver_table

PRODUCTS = {"bts_segments"}
VERSION = "bts_retained_segments_v1"
DATA_MEMBER = "T_T100I_SEGMENT_ALL_CARRIER.csv"
DOC_MEMBER = "Documentation.csv"
FIELDS = (
    "DEPARTURES_SCHEDULED DEPARTURES_PERFORMED SEATS PASSENGERS FREIGHT MAIL DISTANCE "
    "RAMP_TO_RAMP AIR_TIME UNIQUE_CARRIER AIRLINE_ID UNIQUE_CARRIER_NAME UNIQUE_CARRIER_ENTITY "
    "CARRIER CARRIER_NAME CARRIER_GROUP ORIGIN ORIGIN_CITY_NAME ORIGIN_COUNTRY ORIGIN_COUNTRY_NAME "
    "DEST DEST_CITY_NAME DEST_COUNTRY DEST_COUNTRY_NAME AIRCRAFT_TYPE AIRCRAFT_CONFIG "
    "YEAR QUARTER MONTH CLASS"
).split()
COUNTS = [k.lower() for k in FIELDS[:9]]
INTEGERS = ["airline_id", "carrier_group", "aircraft_type", "aircraft_config", "year", "quarter", "month"]
IDENTITY = [
    "airline_id",
    "unique_carrier",
    "unique_carrier_name",
    "unique_carrier_entity",
    "carrier",
    "carrier_name",
]
GRAIN = [
    "unique_carrier",
    "unique_carrier_entity",
    "origin",
    "dest",
    "aircraft_type",
    "aircraft_config",
    "year",
    "month",
    "class",
]
REVISION_VALUES = [
    *COUNTS,
    "airline_id",
    "unique_carrier_name",
    "carrier",
    "carrier_name",
    "carrier_group",
    "origin_city_name",
    "origin_country",
    "origin_country_name",
    "dest_city_name",
    "dest_country",
    "dest_country_name",
    "quarter",
]
# Reviewed official dictionary bundled INSIDE the retained dataset, not a name-based equivalence.
DOCUMENTATION = {
    "YEAR": "Year",
    "QUARTER": "Quarter",
    "MONTH": "Month",
    "ORIGIN": "Origin Airport",
    "ORIGIN_CITY_NAME": "Origin City",
    "ORIGIN_COUNTRY": "Origin Airport, Country",
    "ORIGIN_COUNTRY_NAME": "Origin Airport, Country Name",
    "DEST": "Destination Airport",
    "DEST_CITY_NAME": "Destination City",
    "DEST_COUNTRY": "Destination Airport, Country",
    "DEST_COUNTRY_NAME": "Destination Airport, Country Name",
    "UNIQUE_CARRIER": "Unique Carrier Code. When the same code has been used by multiple carriers, a "
    "numeric suffix is used for earlier users, for example, PA, PA(1), PA(2). Use "
    "this field for analysis across a range of years.",
    "AIRLINE_ID": "An identification number assigned by US DOT to identify a unique airline "
    "(carrier). A unique airline (carrier) is defined as one holding and reporting "
    "under the same DOT certificate regardless of its Code, Name, or holding "
    "company/corporation.",
    "UNIQUE_CARRIER_NAME": "Unique Carrier Name. When the same name has been used by multiple "
    "carriers, a numeric suffix is used for earlier users, for example, Air "
    "Caribbean, Air Caribbean (1).",
    "UNIQUE_CARRIER_ENTITY": "Unique Entity for a Carrier's Operation Region.",
    "CARRIER": "Code assigned by IATA and commonly used to identify a carrier. As the same code may "
    "have been assigned to different carriers over time, the code is not always unique. "
    "For analysis, use the Unique Carrier Code.",
    "CARRIER_NAME": "Carrier Name",
    "CARRIER_GROUP": "Carrier Group Code.  Used in Legacy Analysis",
    "CLASS": "Service Class",
    "AIRCRAFT_TYPE": "Aircraft Type",
    "AIRCRAFT_CONFIG": "Aircraft Configuration",
    "DEPARTURES_SCHEDULED": "Departures Scheduled",
    "DEPARTURES_PERFORMED": "Departures Performed",
    "SEATS": "Available Seats",
    "PASSENGERS": "Non-Stop Segment Passengers Transported",
    "FREIGHT": "Non-Stop Segment Freight Transported (pounds)",
    "MAIL": "Non-Stop Segment Mail Transported (pounds)",
    "DISTANCE": "Distance between airports (miles)",
    "RAMP_TO_RAMP": "Ramp to Ramp Time (minutes)",
    "AIR_TIME": "Airborne Time (minutes)",
}


def month(period):
    if not isinstance(period, str) or not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("BTS segments require an explicit month")
    return int(period[:4]), int(period[-2:])


def csv_rows(body, header):
    try:
        reader = csv.reader(io.StringIO(body.decode("utf-8-sig")), strict=True)
        if next(reader, None) != header:
            raise ValueError("BTS CSV header/order changed")
        result = []
        for row in reader:
            if len(row) != len(header) or any(not v or v != v.strip() for v in row):
                raise ValueError("BTS CSV contains missing, ragged or padded values")
            if any(any(ord(c) < 32 for c in v) for v in row):
                raise ValueError("BTS CSV contains control characters")
            result.append(dict(zip(header, row, strict=True)))
            if len(result) > 500_000:
                raise ValueError("BTS CSV row bound exceeded")
        if not result:
            raise ValueError("Empty BTS CSV")
        return result
    except (UnicodeError, csv.Error) as exc:
        raise ValueError("Invalid BTS CSV encoding/format") from exc


def archive(content):
    if len(content) > 20_000_000:
        raise ValueError("BTS ZIP compressed size bound exceeded")
    try:
        with ZipFile(io.BytesIO(content)) as z:
            members = z.infolist()
            if len(members) != 2 or {m.filename for m in members} != {DATA_MEMBER, DOC_MEMBER}:
                raise ValueError("BTS ZIP requires exactly the reviewed data and dictionary members")
            if any(m.flag_bits & 1 or m.is_dir() or m.file_size > 100_000_000 for m in members):
                raise ValueError("Encrypted, directory or oversized BTS ZIP member")
            docs, data = z.read(DOC_MEMBER), z.read(DATA_MEMBER)
    except (BadZipFile, RuntimeError, OSError) as exc:
        raise ValueError("Invalid BTS ZIP") from exc
    rows = csv_rows(docs, ["SYS_FIELD_NAME", "FIELD_DESC"])
    if (
        len(rows) != len(DOCUMENTATION)
        or {r["SYS_FIELD_NAME"]: r["FIELD_DESC"] for r in rows} != DOCUMENTATION
    ):
        raise ValueError("Official BTS dictionary definitions/units changed")
    return csv_rows(data, FIELDS), {
        "data_member": DATA_MEMBER,
        "data_member_sha256": hashlib.sha256(data).hexdigest(),
        "dictionary_member": DOC_MEMBER,
        "dictionary_member_sha256": hashlib.sha256(docs).hexdigest(),
        "native_units": {
            "freight": "pounds",
            "mail": "pounds",
            "distance": "miles",
            "air_time": "minutes",
            "ramp_to_ramp": "minutes",
            "passengers": "non_stop_segment_passengers",
            "seats": "available_seats",
        },
        "service_classes_interpreted": False,
    }


def map_identities(frame):
    reference = pd.read_csv(ROOT / "config/carrier_crosswalk.csv", dtype=str, keep_default_na=False)
    if not set(IDENTITY + ["carrier_key", "carrier_identity"]) <= set(reference):
        raise ValueError("BTS exact identity reference missing fields")
    reference = reference[IDENTITY + ["carrier_key", "carrier_identity"]].drop_duplicates()
    if reference.duplicated(IDENTITY).any():
        raise ValueError("Ambiguous BTS exact identity reference")
    if reference[["carrier_key", "carrier_identity"]].eq("").any().any():
        raise ValueError("BTS identity reference contains missing canonical keys")
    result = frame.merge(reference, on=IDENTITY, how="left", validate="many_to_one", sort=False)
    if result.carrier_key.isna().any():
        raise ValueError("Unmapped BTS exact DOT/entity/code/name identity; review reference explicitly")
    if not result.carrier_identity.eq("AIRLINE_ID_" + result.airline_id).all():
        raise ValueError("BTS DOT identifier differs from canonical identity reference")
    return result


def read(product, inputs, period):
    if product not in PRODUCTS or set(inputs) != {"archive"}:
        raise ValueError("BTS product requires its exact archive role")
    year, requested = month(period)
    content, original = inputs["archive"]
    if original["source_system"] != "bts_t100" or hashlib.sha256(content).hexdigest() != original["sha256"]:
        raise ValueError("BTS original source/hash differs")
    rows, details = archive(content)
    frame = pd.DataFrame([{k.lower(): v for k, v in r.items()} for r in rows])
    frame["source_row_json"] = [json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in rows]
    frame["source_row"] = np.arange(2, len(frame) + 2, dtype="int64")
    for field in COUNTS:
        if not frame[field].str.fullmatch(r"(?:0|[1-9]\d*)\.00").all():
            raise ValueError("BTS native count/distance/time is missing, negative or not integral .00")
        values = frame[field].map(lambda v: int(v[:-3]))
        if values.gt(10**12).any():
            raise ValueError("BTS numeric exactness bound exceeded")
        frame[field] = values.astype("int64")
    for field in INTEGERS:
        # The official FJE-linked aircraft lookup uses three-digit codes, e.g.
        # 094. Only this code field admits that source padding; the original
        # token remains in source_row_json. Quantities and other IDs stay strict.
        pattern = r"(?:0|[1-9]\d*|0[0-9]{2})" if field == "aircraft_type" else r"(?:0|[1-9]\d*)"
        if not frame[field].str.fullmatch(pattern).all():
            raise ValueError("BTS native integer identifier/period changed")
        if frame[field].map(int).gt(10**9).any():
            raise ValueError("BTS identifier bound exceeded")
    if not frame.year.eq(str(year)).all() or not frame.month.astype(int).between(1, 12).all():
        raise ValueError("BTS actual native year/month differs from requested year")
    months = set(frame.month.astype(int))
    observed_max = f"{year}M{max(months):02d}"
    if period_end(observed_max) >= local_time(original["downloaded_at"]).date():
        raise ValueError("BTS maximum observation month is not closed before original capture")
    if months != set(range(1, max(months) + 1)) or requested not in months:
        raise ValueError("BTS archive months must be contiguous and include requested month")
    if not frame.quarter.astype(int).eq((frame.month.astype(int) - 1) // 3 + 1).all():
        raise ValueError("BTS native quarter differs from month")
    if not (
        (frame.origin_country.eq("MX") & frame.dest_country.eq("US"))
        | (frame.origin_country.eq("US") & frame.dest_country.eq("MX"))
    ).all():
        raise ValueError("BTS archive contains observations outside MX/US directional segments")
    for field in ["origin", "dest"]:
        if not frame[field].str.fullmatch(r"[A-Z0-9]{3}").all():
            raise ValueError("BTS airport code format changed")
    if (
        not frame["class"].isin(["F", "G", "L", "P"]).all()
        or not frame.aircraft_config.isin(["1", "2", "3"]).all()
    ):
        raise ValueError("BTS reviewed class/configuration code domain changed")
    if frame.distance.le(0).any() or frame.aircraft_type.astype(int).le(0).any():
        raise ValueError("BTS nonpositive distance/aircraft code")
    if frame.duplicated(GRAIN).any():
        raise ValueError("Duplicate BTS native observation grain")
    padded_types = frame.loc[frame.aircraft_type.str.fullmatch(r"0[0-9]{2}"), "aircraft_type"]
    combined_configurations = int(frame.aircraft_config.eq("3").sum())
    frame = map_identities(frame)
    for field in INTEGERS:
        if field != "airline_id":
            frame[field] = frame[field].astype("int64")
    frame["period_id"] = frame.year.astype(str) + "M" + frame.month.map(lambda m: f"{m:02d}")
    frame["route_key"] = frame.origin + "-" + frame.dest
    for output, quantity in [("asm_miles", "seats"), ("rpm_miles", "passengers")]:
        # Multiply Python integers first; int64 overflow must never pass the bound check.
        products = [int(q) * int(d) for q, d in zip(frame[quantity], frame.distance, strict=True)]
        if any(v > 2**53 for v in products):
            raise ValueError("BTS weighted distance exactness bound exceeded")
        frame[output] = pd.Series(products, dtype="int64", index=frame.index)
    frame["load_factor"] = frame.rpm_miles / frame.asm_miles.replace(0, np.nan)
    frame["quality_issue"] = np.where(frame.passengers.gt(frame.seats), "passengers_exceed_seats", "none")
    issues = frame.loc[
        frame.quality_issue.ne("none"),
        ["source_row", "period_id", *GRAIN, "passengers", "seats", "quality_issue"],
    ].to_dict("records")
    if any(r["period_id"] == period for r in issues):
        raise ValueError(
            "BTS requested month contains passengers above available seats; preserve source and investigate"
        )
    frame = frame.assign(
        source_system="bts_t100",
        source_file=original["source_file"],
        source_hash=original["sha256"],
        ingested_at=pd.Timestamp(original["downloaded_at"]).as_unit("ns"),
        parser_version=VERSION,
        agent_eligible=False,
    )
    validate_silver_table("bts_t100_segment", frame)
    if not padded_types.empty:
        details["aircraft_type_token_policy"] = (
            "three-digit code padding retained literally in source_row_json; "
            "existing integer storage is normalized, without aircraft-name inference"
        )
        details["zero_padded_aircraft_type_tokens"] = {
            str(token): int(count) for token, count in padded_types.value_counts().items()
        }
    if combined_configurations:
        # FJE's official lookup defines 3 as combined passenger/freight. Keep
        # that literal configuration; service classes stay uninterpreted and
        # the financial-expense-only code 9 stays outside physical segments.
        details["combined_aircraft_configuration_rows"] = combined_configurations
    details.update(
        native_rows=len(frame),
        projected_period=period,
        observed_max_period=f"{year}M{max(months):02d}",
        observed_periods=sorted(frame.period_id.unique()),
        raw_class_codes=sorted(frame["class"].unique()),
        native_quality_issues=issues,
        complete_month_certified=False,
        selected_month_observations_certified=True,
        operator_coverage_verified=False,
    )
    return frame.sort_values(GRAIN).reset_index(drop=True), details
