"""Closed Viva/Volaris monthly bookings, separate from AFAC flown passengers.

The two points are the report month and its comparison in the SAME edition,
not a reconstruction of historical source availability. The common gate checks
the complete dashboard contract and preserves every unrelated payload.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal

from src.pipeline.offline import block_network
from src.publish.airport_demand_projection import _facts, _input_files
from src.source_updates import readiness
from src.source_updates.catalog import ROOT
from src.source_updates.checks import period_end
from src.source_updates.closed_editions import accepted
from src.web_export.writer import dumps_deterministic

PRODUCTS = frozenset({"viva_traffic", "volaris_traffic_ir"})
TARGETS = ("data/v1/flights/quarters.json",)
CONTRACTS = ("flights.schema.json",)
SCOPE = "booked_flight_segments_not_observed_flown_passengers_itinerary_and_charter"
ENTITIES = {"viva_traffic": "VIVA_AEROBUS", "volaris_traffic_ir": "VOLARIS"}
TABLES = {
    "viva_traffic": "fact_viva_monthly_source_metrics",
    "volaris_traffic_ir": "fact_volaris_ir_monthly_traffic",
}
SERIES_FIELDS = {
    "entity",
    "source_url",
    "source_sha256",
    "captured_at",
    "documentary_date",
    "scope",
    "reporting_status",
    "entity_attribution",
    "records",
}
RECORD_FIELDS = {
    "period_id",
    "date",
    "domestic",
    "international",
    "reported_total",
    "total_segment_sum",
    "reconciliation_delta",
}


def _validate_series(series, product, period):
    if product not in ENTITIES or not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("Peer report requires its own explicitly monthly native period")
    if set(series) != SERIES_FIELDS or series["entity"] != ENTITIES[product] or series["scope"] != SCOPE:
        raise ValueError("Peer bookings series has a changed entity, scope or contract")
    if not re.fullmatch("[a-f0-9]{64}", series["source_sha256"]) or not series["source_url"].startswith(
        "https://"
    ):
        raise ValueError("Peer bookings series needs its physical primary source URL/hash")
    captured = datetime.fromisoformat(series["captured_at"].replace("Z", "+00:00"))
    if captured.tzinfo is None:
        raise ValueError("Peer source capture requires its original timezone")
    documentary = date.fromisoformat(series["documentary_date"])
    current = period_end(period)
    if not current < documentary <= captured.date():
        raise ValueError("Peer document date/capture cannot be relabelled as the observation month")
    expected = {period, f"{int(period[:4]) - 1}{period[4:]}"}
    records = series["records"]
    if len(records) != 2 or {row["period_id"] for row in records} != expected:
        raise ValueError("Keep exactly the reported month and its same-edition annual comparison")
    for row in records:
        if set(row) != RECORD_FIELDS or row["date"] != row["period_id"].replace("M", "-") + "-01":
            raise ValueError("Peer monthly points cannot become quarters, YTD or invented dated observations")
        values = [row[k] for k in ("domestic", "international", "reported_total", "total_segment_sum")]
        if any(type(v) not in {int, float} or not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("Peer bookings need explicit finite nonnegative reported counts")
        delta = row["reconciliation_delta"]
        if type(delta) not in {int, float} or not math.isfinite(delta):
            raise ValueError("Peer bookings need an explicit finite reconciliation difference")
        if row["total_segment_sum"] != row["domestic"] + row["international"]:
            raise ValueError("Peer segment sum must retain the two actual rounded source cells")
        if (
            row["reconciliation_delta"] != row["total_segment_sum"] - row["reported_total"]
            or abs(row["reconciliation_delta"]) > 1500
        ):
            raise ValueError("Peer total reconciliation exceeds three rounded-thousand source cells")
    if not series["reporting_status"] or not series["entity_attribution"]:
        raise ValueError("Keep the preliminary status and literal issuer/brand attribution")


def project_series(item, checked):
    product, period = item["product"], item["period"]
    if product not in PRODUCTS or not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("Select one reviewed monthly peer traffic product")
    from pathlib import Path

    candidate = Path(item["workspace"])
    frame = _facts(candidate, TABLES[product], checked)
    receipt = candidate / "receipts" / f"certified-{product}-{period}.json"
    if (
        receipt.is_symlink()
        or not receipt.is_file()
        or hashlib.sha256(receipt.read_bytes()).hexdigest() != checked["accepted_receipt_sha256"]
    ):
        raise ValueError("Peer document metadata must come from the exact replayed source receipt")
    details = json.loads(receipt.read_bytes())
    months = {period, f"{int(period[:4]) - 1}{period[4:]}"}
    rows = frame[
        frame.metric_key.eq("passengers_booked")
        & frame.period_type.eq("month")
        & frame.period_id.isin(months)
    ].copy()
    if (
        len(rows) != 6
        or set(rows.segment) != {"domestic", "international", "total"}
        or rows.duplicated(["period_id", "segment"]).any()
    ):
        raise ValueError("Peer report needs six unique booked-passenger monthly/comparative source cells")
    if (
        not rows.unit.eq("thousand booked passengers").all()
        or not rows.carrier_key.eq(ENTITIES[product]).all()
    ):
        raise ValueError("Peer passenger unit/entity differs; never substitute AFAC flown passengers")
    if not rows.is_preliminary.eq(True).all():
        raise ValueError("Peer preliminary source flag changed; preserve the actual reviewed edition")
    if product == "viva_traffic":
        if not rows.definition.eq("booked_not_necessarily_flown_itinerary_and_charter").all():
            raise ValueError("Viva passenger definition changed")
        if not rows.reporting_status.eq("preliminary").all():
            raise ValueError("Viva reporting status changed")
        documentary = details["document_date"]
        status = "preliminary"
    else:
        if (
            not rows.passenger_definition.eq("booked_flight_segments_not_observed_flown_passengers").all()
            or not rows.flight_scope.eq("itinerary_and_charter; load_factor_RPM_div_ASM").all()
            or not rows.is_unaudited.eq(True).all()
            or not rows.scale_multiplier.eq(1000).all()
            or not rows.normalized_unit.eq("booked passengers").all()
            or not rows.value_normalized.eq(rows.value * 1000).all()
        ):
            raise ValueError("Volaris bookings, unit normalization or reporting scope changed")
        documentary = details["source_report_date_as_reported"]
        status = "preliminary_unaudited"
    for field in ("source_hash", "ingested_at", "entity_as_reported"):
        if rows[field].nunique() != 1:
            raise ValueError("A monthly peer edition must preserve its unique original/capture/entity")
    if rows.value.isna().any() or any(
        not math.isfinite(float(v)) or float(v) != int(v) or v < 0 for v in rows.value
    ):
        raise ValueError("Peer bookings require native integer thousands, not inferred precision")
    records = []
    for native_period, group in rows.groupby("period_id", sort=True):
        values = {row.segment: int(Decimal(str(row.value)) * 1000) for row in group.itertuples()}
        total = values["domestic"] + values["international"]
        records.append(
            dict(
                period_id=str(native_period),
                date=str(native_period).replace("M", "-") + "-01",
                domestic=values["domestic"],
                international=values["international"],
                reported_total=values["total"],
                total_segment_sum=total,
                reconciliation_delta=total - values["total"],
            )
        )
    artifacts = _facts(candidate, "dim_source_artifact", checked)
    first = rows.iloc[0]
    source = artifacts[artifacts.artifact_sha256.eq(first.source_hash)]
    if len(source) != 1:
        raise ValueError("Peer report must retain its one verified primary artifact")
    series = dict(
        entity=ENTITIES[product],
        source_url=str(source.source_url.iloc[0]),
        source_sha256=str(first.source_hash),
        captured_at=first.ingested_at.isoformat()
        if hasattr(first.ingested_at, "isoformat")
        else str(first.ingested_at),
        documentary_date=documentary,
        scope=SCOPE,
        reporting_status=status,
        entity_attribution=str(first.entity_as_reported),
        records=records,
    )
    _validate_series(series, product, period)
    return series


def replay(profile, baseline):
    if (
        set(profile) != {"schema_version", "item", "as_of"}
        or profile["schema_version"] != "peer_monthly_passengers_source_v1"
    ):
        raise ValueError("Unsupported peer monthly source profile")
    item = profile["item"]
    if item.get("product") not in PRODUCTS:
        raise ValueError("Peer monthly projection cannot consume another source")
    recipe = {"version": 1, "as_of": profile["as_of"], "required_items": [item["id"]], "items": [item]}
    with block_network():
        task = readiness.preflight(recipe, ROOT / "tmp/source-updates/peer-monthly-source-check")[0]
        checked = readiness.check_task(task, item["candidate_as_of"], profile["as_of"])
        if not accepted(task, checked):
            raise ValueError("Peer monthly source requires its complete availability and physical replay")
        series = project_series(task, checked)
        inputs = _input_files(task)
    binding = {key: item[key] for key in ("product", "period", "receipt_id", "candidate_as_of")}
    binding["output_sha256"] = checked["output_sha256"]
    return {
        "source_binding": binding,
        "projection": {"product": item["product"], "period": item["period"], "series": series},
        "input_files": inputs,
    }


def public_outputs(before, projection):
    if (
        set(before) != set(TARGETS)
        or set(projection) != {"product", "period", "series"}
        or projection["product"] not in PRODUCTS
    ):
        raise ValueError("Peer monthly projection must name its one existing flight-series payload")
    product, period, series = projection["product"], projection["period"], projection["series"]
    _validate_series(series, product, period)
    payload = json.loads(before[TARGETS[0]])
    if payload.get("schema_version") != "flight_dashboard_payload_v1":
        raise ValueError("Peer source needs the existing complete flight dashboard payload")
    updated = copy.deepcopy(payload)
    peers = updated.setdefault("corporate_peer_monthly_passengers", {})
    previous = peers.get(series["entity"])
    if previous and not {row["period_id"] for row in previous["records"]} <= {
        row["period_id"] for row in series["records"]
    }:
        raise ValueError(
            "Retain older peer editions with point-level provenance before extending their history"
        )
    peers[series["entity"]] = copy.deepcopy(series)
    return {TARGETS[0]: (dumps_deterministic(updated) + "\n").encode()}
