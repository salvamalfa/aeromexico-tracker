"""Bounded Aerocivil query recipe and offline monthly source certification CLI."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit
from uuid import uuid4

import pandas as pd

from src.ingest.international_routes import CO_URL
from src.pipeline.offline import block_network
from src.source_updates.calendar import local_time
from src.source_updates.catalog import ROOT
from src.source_updates.checks import period_end, row_changes, verify_bronze
from src.source_updates.collection import safe_workspace, validate_url, writer
from src.transform.international_routes import TABLE
from src.transform.international_routes import validate as validate_routes
from src.transform.stage6_contracts import validate_table
from src.transform.stage9_lineage import (
    LineageSpec,
    _make_artifact_id,
    build_bridge_record_lineage,
    build_dim_source_artifact,
    make_record_id,
)
from src.transform.validate_stage9 import validate_lineage_frames

VERSION = "aerocivil_monthly_candidate_v1"
METADATA_URL = "https://www.datos.gov.co/api/views/jh8x-n6h6.json"
RECORD_GRAIN = ["source_system", "source_hash", "source_locator", "parser_version"]
GRAIN = (
    "anio",
    "mes",
    "aeropuerto_operacion",
    "origen",
    "destino",
    "empresa",
    "explotador",
    "tipo_vuelo",
    "trafico",
    "tipo_operacion",
)
OUTPUTS = (
    "silver/international_routes/observations",
    f"gold/{TABLE}",
    "gold/dim_source_artifact",
    "gold/bridge_international_route_lineage",
)
REVISION_GRAIN = [
    "source_system",
    "period_id",
    "origin_icao",
    "dest_icao",
    "operator_icao",
    "commercial_designator_as_reported",
    "source_flight_type_code",
    "source_traffic_code",
]
METADATA_FIELDS = {
    "empresa": "Designador de la aerolínea (Comercial)",
    "explotador": "Poseedor del Certificado de Operador Aéreo (AOC)",
    "tipo_vuelo": "Clasificación por propósito del vuelo",
    "trafico": "Clasificación geográfica del servicio",
    "totaloperaciones": "Conteo volumétrico de movimientos",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metadata_selection() -> dict:
    return {
        "version": 1,
        "items": [
            {
                "id": "aerocivil-dictionary",
                "product": "aerocivil",
                "source_system": "aerocivil",
                "entity": "dataset_metadata",
                "period": "current",
                "purpose": "data",
                "url": METADATA_URL,
                "extension": "json",
                "mode": "get",
                "relative_dir": "international_routes/aerocivil/metadata",
            }
        ],
    }


def availability_selection(year: str) -> dict:
    """Discover a bounded operator-month maximum; no inference about month completeness."""
    if not isinstance(year, str) or not re.fullmatch(r"20\d{2}", year):
        raise ValueError("Availability requires one explicit four-digit year")
    selection = metadata_selection()
    selection["items"][0].update(
        id="aerocivil-availability",
        entity="latest_available_operator_month",
        relative_dir="international_routes/aerocivil/availability",
        url=CO_URL
        + "?"
        + urlencode(
            {
                "$select": "anio,mes",
                "$where": f"anio = '{year}' AND (explotador='AMX' OR explotador='SLI')",
                "$group": "anio,mes",
                "$order": "anio DESC,mes DESC",
                "$limit": "1",
            }
        ),
    )
    return selection


def recipe(period: str) -> dict:
    if not re.fullmatch(r"20\d{2}M(?:0[1-9]|1[0-2])", period):
        raise ValueError("Choose one explicit month; no automatic full-history refresh")
    where = f"anio = '{period[:4]}' AND mes = '{period[-2:]}' AND (explotador='AMX' OR explotador='SLI')"
    params = {
        "count_before": {"$where": where, "$select": "count(*) AS row_count"},
        "rows": {
            "$where": where,
            "$limit": "1000",
            "$order": ",".join(key for key in GRAIN if key != "trafico"),
        },
        "count_after": {"$where": where, "$select": "count(*) AS row_count"},
    }
    return {
        "version": 1,
        "items": [
            {
                "id": "aerocivil-" + role,
                "product": "aerocivil",
                "source_system": "aerocivil",
                "entity": role,
                "period": period,
                "purpose": "data",
                "url": CO_URL + "?" + urlencode(query),
                "extension": "json",
                "mode": "get",
                "relative_dir": f"international_routes/aerocivil/{period}",
            }
            for role, query in params.items()
        ],
        "bounds": {
            "base_requests": 3,
            "maximum_http_requests": 15,
            "maximum_rows": 1000,
            "pagination": "single bounded response; reject counts above1000",
            "paid_requests": 0,
        },
        "activation": "none",
        "publication": "not_authorized",
        "required_metadata_url": METADATA_URL,
    }


def integer(value) -> int:
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise ValueError("Operation/count value must be an explicit nonnegative integer")
    if isinstance(value, str) and not re.fullmatch(r"\d+", value):
        raise ValueError("Unverified operation/count token")
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid operation/count token") from exc
    if not parsed.is_finite() or parsed < 0 or parsed > 2**53 - 1 or parsed != parsed.to_integral_value():
        raise ValueError("Invalid operation/count value; no missing-to-zero conversion")
    return int(parsed)


def review_metadata(definition: dict) -> dict:
    """Check the same dataset's definitions without inventing its missing code legend."""
    columns = definition.get("columns", [])
    if not isinstance(columns, list) or any(not isinstance(column, dict) for column in columns):
        raise ValueError("Official metadata columns must be an explicit list")
    names = [column.get("fieldName") for column in columns]
    if any(not isinstance(name, str) or not name for name in names) or len(set(names)) != len(names):
        raise ValueError("Official metadata has missing or duplicate field definitions")
    descriptions = {column["fieldName"]: column.get("description") for column in columns}
    description = definition.get("description")
    if (
        definition.get("id") != "jh8x-n6h6"
        or any(descriptions.get(name) != meaning for name, meaning in METADATA_FIELDS.items())
        or not isinstance(description, str)
        or not all(
            token in description
            for token in ("EMPRESA y EXPLOTADOR", "callsign", "matrícula", "trimestralmente")
        )
    ):
        raise ValueError("Official dataset identity/definitions changed; source semantic review required")
    return {
        "dataset_id": definition["id"],
        "reviewed_fields": list(METADATA_FIELDS),
        "description_sha256": hashlib.sha256(description.encode()).hexdigest(),
        "field_definitions_sha256": hashlib.sha256(
            json.dumps({name: descriptions[name] for name in METADATA_FIELDS}, sort_keys=True).encode()
        ).hexdigest(),
        "code_legend_status": "no_explicit_literal_mapping_in_reviewed_column_definitions",
        "service_code_mapping_verified": False,
        "entity_attribution": "source_derived_callsign_and_aircraft_registration_not_independently_verified",
        # These timestamps describe the dataset, not first publication of a monthly slice.
        "dataset_rows_updated_at_epoch": definition.get("rowsUpdatedAt"),
        "dataset_publication_date_epoch": definition.get("publicationDate"),
        "monthly_first_publication_verified": False,
    }


def availability(workspace: Path, year: str, as_of: str, collection: str) -> dict:
    """Verify a retained maximum-month response; this is discovery, not numeric certification."""
    workspace = safe_workspace(workspace)
    expected = availability_selection(year)["items"][0]
    if not re.fullmatch(r"[a-f0-9]{32}", collection):
        raise ValueError("Expected a preserved collection receipt ID")
    receipt_path = workspace / "receipts" / f"collection-{collection}.json"
    receipt = json.loads(receipt_path.read_text())
    if receipt.get("status") != "collected_unvalidated" or len(receipt.get("items", [])) != 1:
        raise ValueError("Complete single-query availability receipt required")
    item = receipt["items"][0]
    original = verify_bronze(workspace).get(item.get("source_file"))
    if (
        original is None
        or original["source_system"] != "aerocivil"
        or item.get("id") != expected["id"]
        or item.get("product") != "aerocivil"
        or item.get("status") != "collected_unvalidated"
        or item.get("http_status") != 200
        or original["source_url"] != expected["url"]
        or item.get("source_url") != expected["url"]
        or item.get("sha256") != original["sha256"]
    ):
        raise ValueError("Availability receipt/manifest/query mismatch")
    validate_url(item.get("response_url", ""), ["datos.gov.co"])
    response, request = urlsplit(item["response_url"]), urlsplit(expected["url"])
    if response.path != request.path or sorted(parse_qsl(response.query)) != sorted(parse_qsl(request.query)):
        raise ValueError("Availability response escaped the selected dataset/query")
    if local_time(original["downloaded_at"]) > local_time(as_of):
        raise ValueError("Availability original is after the requested cutoff")
    path = workspace / "data/bronze" / original["source_file"]
    sidecar = json.loads(Path(str(path) + ".meta.json").read_text())
    if any(
        sidecar.get(key) != original[key] for key in ("sha256", "source_url", "downloaded_at", "logical_key")
    ):
        raise ValueError("Availability Bronze sidecar differs from its manifest")
    rows = json.loads(path.read_bytes())
    if not isinstance(rows, list) or len(rows) > 1:
        raise ValueError("Availability query must return zero or one maximum-month row")
    latest = None
    if rows:
        row = rows[0]
        if (
            not isinstance(row, dict)
            or set(row) != {"anio", "mes"}
            or row["anio"] != year
            or not isinstance(row["mes"], str)
            or not re.fullmatch(r"0[1-9]|1[0-2]", row["mes"])
            or (int(year), int(row["mes"])) > (local_time(as_of).year, local_time(as_of).month)
        ):
            raise ValueError("Unverified maximum-month response identity or future month")
        latest = year + "M" + row["mes"]
    return {
        "status": "availability_observed" if latest else "no_month_returned_for_selected_filter",
        "scope": f"AMX_SLI_source_derived_operator_codes_only_{year}",
        "latest_available_period": latest,
        "latest_validated_period": None,
        "latest_published_period": None,
        "complete_month_verified": False,
        "published_at": None,
        "release_lag_days": None,
        "source_file": original["source_file"],
        "source_url": original["source_url"],
        "source_hash": original["sha256"],
        "downloaded_at": original["downloaded_at"],
        "collection_receipt_sha256": sha(receipt_path),
        "network_requests": 0,
        "paid_requests": 0,
        "activation": "none",
        "publication": "not_authorized",
    }


def normalize(rows: list, period: str, original: dict, airports: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if not isinstance(rows, list) or not rows or len(rows) > 1000:
        raise ValueError("Expected1..1000 complete source rows")
    required = {"ident", "iata_code", "iso_country"}
    if not required.issubset(airports.columns) or airports.ident.duplicated().any():
        raise ValueError("Unique OurAirports ICAO reference required")
    reference = airports.set_index("ident")
    seen, results, excluded = set(), [], []
    for index, raw in enumerate(rows, 1):
        if set(raw) - {*GRAIN, "totaloperaciones"} or not (
            (set(GRAIN) - {"empresa"}) | {"totaloperaciones"}
        ).issubset(raw):
            raise ValueError("Aerocivil source schema changed; review all fields")
        key = tuple(raw.get(field) or None for field in GRAIN)
        if (
            any(
                not isinstance(raw.get(field), str) or not raw[field] for field in GRAIN if field != "empresa"
            )
            or key in seen
        ):
            raise ValueError("Missing native identity or duplicate source grain")
        if raw.get("empresa") is not None and not isinstance(raw["empresa"], str):
            raise ValueError("Unverified commercial designator token")
        seen.add(key)
        if raw["anio"] != period[:4] or raw["mes"] != period[-2:] or raw["explotador"] not in {"AMX", "SLI"}:
            raise ValueError("Aerocivil response escaped the selected month/operator query")
        count = integer(raw["totaloperaciones"])
        if raw["tipo_vuelo"] not in {"S", "N"} or raw["trafico"] not in {"I", "N"}:
            raise ValueError("Unknown flight/traffic category; preserve for review")
        if raw["tipo_vuelo"] != "S" or raw["trafico"] != "I":
            excluded.append(
                {
                    "source_locator": f"record:{index}",
                    "reason": "outside_selected_literal_flight_S_traffic_I_codes",
                    "operations": count,
                }
            )
            continue
        origin, dest = raw["origen"], raw["destino"]
        if not re.fullmatch(r"[A-Z0-9]{4}", origin) or not re.fullmatch(r"[A-Z0-9]{4}", dest):
            raise ValueError("Unverified ICAO airport identifier")
        if origin not in reference.index or dest not in reference.index:
            raise ValueError("Required airport absent from retained reference")
        first, second = reference.loc[origin], reference.loc[dest]
        if {first.iso_country, second.iso_country} != {"MX", "CO"}:
            raise ValueError("Aerocivil candidate only supports identified Mexico-Colombia routes")
        local = origin if first.iso_country == "CO" else dest
        if raw["aeropuerto_operacion"] != local or raw["tipo_operacion"] != (
            "SALIDA" if origin == local else "LLEGADA"
        ):
            raise ValueError("Local recording airport/direction mismatch; do not double-count remote events")
        if not all(
            isinstance(code, str) and re.fullmatch(r"[A-Z]{3}", code)
            for code in (first.iata_code, second.iata_code)
        ):
            raise ValueError("Required airport lacks an unambiguous IATA reference")
        if any(airports.iata_code.eq(code).sum() != 1 for code in (first.iata_code, second.iata_code)):
            raise ValueError("Selected IATA reference is ambiguous")
        row = {
            "record_id": make_record_id(
                TABLE,
                {
                    "source_system": "aerocivil",
                    "source_hash": original["sha256"],
                    "source_locator": f"record:{index}",
                    "parser_version": VERSION,
                },
            ),
            "source_system": "aerocivil",
            "observation_scope": "carrier_route",
            "metric_key": "operations",
            "operator_icao": raw["explotador"],
            "marketing_carrier": None,
            "commercial_designator_as_reported": raw.get("empresa") or None,
            "source_flight_type_code": raw["tipo_vuelo"],
            "source_traffic_code": raw["trafico"],
            "period_id": period,
            "origin_iata": first.iata_code,
            "dest_iata": second.iata_code,
            "origin_icao": origin,
            "dest_icao": dest,
            "airport_iata": None,
            "passengers": None,
            "seats": None,
            "departures": None,
            "operations": float(count),
            "load_factor": None,
            "metric_definition": (
                "Recorded airport movements at the Colombian reporting airport under literal "
                "tipo_vuelo=S and trafico=I codes; legend pending. Commercial/AOC labels are "
                "source-derived. Not passenger, seat or departure counts"
            ),
            "source_file": original["source_file"],
            "source_hash": original["sha256"],
            "source_url": original["source_url"],
            "downloaded_at": original["downloaded_at"],
            "published_at": None,
            "source_locator": f"record:{index}",
            "parser_version": VERSION,
            "agent_eligible": False,
            "artifact_id": _make_artifact_id(original["source_file"], original["sha256"]),
        }
        results.append(row)
    if not results:
        raise ValueError(
            "No Mexico-Colombia observations under selected S/I codes; no zero/absence inference"
        )
    frame = pd.DataFrame(results)
    for column in ("passengers", "seats", "departures", "operations", "load_factor"):
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype(float)
    # Use the source's commercial-designator partition solely for the existing
    # native-grain validator; do not assert that it identifies a codeshare marketer.
    validate_routes(frame.assign(marketing_carrier=frame.commercial_designator_as_reported))
    return frame, {
        "raw_rows": len(rows),
        "accepted_rows": len(frame),
        "excluded": excluded,
        "reported_operations_under_selected_codes": sum(int(value) for value in frame.operations),
        "operators_present": sorted(set(frame.operator_icao)),
        "missing_operator_is_not_zero": True,
    }


def frames(workspace: Path, period: str, as_of: str, collection: str) -> tuple[dict, dict]:
    if not re.fullmatch(r"[a-f0-9]{32}", collection):
        raise ValueError("Expected a preserved collection receipt ID")
    path = workspace / "receipts" / f"collection-{collection}.json"
    receipt = json.loads(path.read_text())
    expected = recipe(period)["items"]
    if receipt.get("status") != "collected_unvalidated" or len(receipt["items"]) != 3:
        raise ValueError("Complete count-before/rows/count-after acquisition required")
    records = verify_bronze(workspace)
    if any(row["source_system"] not in {"aerocivil", "ourairports"} for row in records.values()):
        raise ValueError("Use an isolated Aerocivil candidate with its explicit airport reference")
    content, originals = {}, {}
    for requested, item in zip(expected, receipt["items"], strict=True):
        row = records.get(item.get("source_file"))
        if (
            row is None
            or item.get("id") != requested["id"]
            or item.get("product") != "aerocivil"
            or row["source_system"] != "aerocivil"
            or row["source_url"] != requested["url"]
            or item.get("source_url") != requested["url"]
            or item.get("sha256") != row["sha256"]
            or item.get("http_status") != 200
            or item.get("status") != "collected_unvalidated"
        ):
            raise ValueError("Aerocivil receipt/manifest/query or response status mismatch")
        validate_url(item.get("response_url", ""), ["datos.gov.co"])
        response, request = urlsplit(item["response_url"]), urlsplit(requested["url"])
        if response.path != request.path or sorted(parse_qsl(response.query)) != sorted(
            parse_qsl(request.query)
        ):
            raise ValueError("Aerocivil response escaped the selected dataset/query")
        role = requested["entity"]
        content[role] = json.loads((workspace / "data/bronze" / row["source_file"]).read_bytes())
        originals[role] = row
    references = [row for row in records.values() if row["source_system"] == "ourairports"]
    if len(references) != 1:
        raise ValueError("Import one retained OurAirports original with its hash, no new paid/source request")
    reference = references[0]
    dictionaries = [
        row
        for row in records.values()
        if row["source_system"] == "aerocivil" and row["source_url"] == METADATA_URL
    ]
    if len(dictionaries) != 1:
        raise ValueError("Capture one official dataset metadata/dictionary original")
    dictionary = dictionaries[0]
    definition = json.loads((workspace / "data/bronze" / dictionary["source_file"]).read_bytes())
    metadata_review = review_metadata(definition)
    for row in [*originals.values(), reference, dictionary]:
        if local_time(row["downloaded_at"]) > local_time(as_of):
            raise ValueError("Candidate original/import is after the requested cutoff")
        source = workspace / "data/bronze" / row["source_file"]
        meta = json.loads(Path(str(source) + ".meta.json").read_text())
        if any(meta.get(key) != row[key] for key in ("sha256", "source_url", "downloaded_at", "logical_key")):
            raise ValueError("Bronze sidecar differs from its manifest")
    counts = []
    for role in ("count_before", "count_after"):
        value = content[role]
        if not isinstance(value, list) or len(value) != 1 or set(value[0]) != {"row_count"}:
            raise ValueError("Unverified source count response")
        counts.append(integer(value[0]["row_count"]))
    rows = content["rows"]
    if not isinstance(rows, list) or counts != [len(rows), len(rows)] or not 1 <= len(rows) <= 1000:
        raise ValueError("Truncated, oversized or changing source count; no implicit pagination")
    airports = pd.read_csv(
        io.BytesIO((workspace / "data/bronze" / reference["source_file"]).read_bytes()), low_memory=False
    )
    frame, details = normalize(rows, period, originals["rows"], airports)
    artifacts = validate_table(
        "dim_source_artifact",
        build_dim_source_artifact(
            workspace / "data/bronze/_manifest.jsonl",
            catalog_path=ROOT / "config/source_catalog.yaml",
            verify_files=True,
        ),
    )
    used = {originals["rows"]["source_file"], reference["source_file"], dictionary["source_file"]}
    identifiers = tuple(artifacts.loc[artifacts.source_file.isin(used), "artifact_id"])
    if len(identifiers) != 3:
        raise ValueError("Source observation and IATA mapping must both resolve to artifacts")
    bridge = validate_table(
        "bridge_record_lineage",
        build_bridge_record_lineage(
            [
                LineageSpec(
                    record_id=record,
                    table_name=TABLE,
                    lineage_type="derived",
                    artifact_ids=identifiers,
                    lineage_note=(
                        "Movement counts copied from Aerocivil, literal S/I codes; official dictionary "
                        "preserves derived commercial/AOC labels. IATA mapped with retained "
                        "OurAirports. Eligibility false."
                    ),
                )
                for record in frame.record_id
            ],
            artifacts,
        ),
    )
    lineage = validate_lineage_frames(
        tables={TABLE: frame},
        artifacts=artifacts,
        bridge=bridge,
        contracts={"tables": {TABLE: {"grain": RECORD_GRAIN}}},
    )
    return dict(zip(OUTPUTS, (frame, frame.copy(), artifacts, bridge), strict=True)), {
        **details,
        "source_counts": counts,
        "collection_receipt_sha256": sha(path),
        "lineage": lineage,
        "reference_sha256": reference["sha256"],
        "metadata_sha256": dictionary["sha256"],
        "metadata_review": metadata_review,
        "period": period,
        "published_at": None,
        "release_lag_days": None,
        "scope": "one_AMX_SLI_query_month_literal_S_I_codes_Colombian_reporting_airports_not_global_network",
        "service_code_mapping_verified": False,
        "interpretation_acceptance": "pending_official_code_legend_and_entity_attribution_review",
        "commercial_designator_status": "source_derived_from_callsign_not_proven_marketing_carrier",
        "operator_designator_status": "source_derived_from_aircraft_registration_not_directly_captured",
        "provider_update_cadence": "quarterly_as_documented_not_new_automation",
        "pagination": "all source rows fit one response; no pages",
        "snapshot_version_isolation_proven": False,
        "revision_comparison": "not_compared_no_baseline",
        "agent_eligible": False,
        "activation": "none",
        "publication": "not_authorized",
    }


def run(
    workspace: Path, period: str, as_of: str, collection: str, *, execute=False, check=False, baseline=None
) -> dict:
    workspace = safe_workspace(workspace)
    recipe(period)
    if period_end(period) >= local_time(as_of).date():
        raise ValueError("Observation month must be closed before the cutoff")
    accepted = workspace / "receipts" / f"aerocivil-{period}.json"
    allowed = {workspace / "data" / (name + ".parquet") for name in OUTPUTS}
    for layer in ("silver", "gold"):
        if {p for p in (workspace / "data" / layer).rglob("*.parquet")} - allowed:
            raise ValueError("Candidate contains other outputs")
    if not execute and not check:
        return {
            "mode": "dry_run",
            "outputs": list(OUTPUTS),
            "network_requests": 0,
            "paid_requests": 0,
            "activation": "none",
            "publication": "not_authorized",
            "baseline_file": baseline,
            "revision_comparison": "explicit_baseline_requested" if baseline else "not_compared_no_baseline",
        }
    prior = json.loads(accepted.read_text()) if check else None
    if check:
        previous_baseline = prior.get("revisions", {}).get("baseline_file")
        if baseline is not None and baseline != previous_baseline:
            raise ValueError("Accepted baseline selection changed")
        baseline = previous_baseline
    if execute and (accepted.exists() or any(p.exists() for p in allowed)):
        raise ValueError("Candidate outputs are immutable; use a new workspace")
    with block_network():
        outputs, result = frames(workspace, period, as_of, collection)
    result.update(
        status="checks_passed",
        collection_run_id=collection,
        effective_as_of=as_of,
        checked_at=datetime.now(UTC).isoformat(),
        code_head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        code_sha256=sha(Path(__file__)),
    )
    result["revisions"] = {"status": "not_compared_no_baseline"}
    if baseline:
        path = (workspace / baseline).resolve()
        if not path.is_relative_to((workspace / "baselines").resolve()):
            raise ValueError("Baseline must remain within candidate baselines/")
        before = pd.read_parquet(path)
        required = {*REVISION_GRAIN, "operations", "metric_key", "observation_scope"}
        if (
            before.empty
            or not required.issubset(before.columns)
            or not before.source_system.eq("aerocivil").all()
            or not before.period_id.eq(period).all()
            or not before.metric_key.eq("operations").all()
            or not before.observation_scope.eq("carrier_route").all()
            or pd.to_numeric(before.operations, errors="raise").isna().any()
            or not pd.to_numeric(before.operations, errors="raise").between(0, 2**53 - 1).all()
            or not pd.to_numeric(before.operations, errors="raise").mod(1).eq(0).all()
        ):
            raise ValueError("Baseline must be an explicit same-month Aerocivil operations candidate")
        result["revisions"] = {
            "status": "compared_explicit_baseline",
            "baseline_file": baseline,
            "baseline_sha256": sha(path),
            "keys": REVISION_GRAIN,
            "values": ["operations"],
            **row_changes(before, outputs[OUTPUTS[0]], REVISION_GRAIN, ["operations"]),
        }
        result["revision_comparison"] = "compared_explicit_baseline"
    if check:
        if result["revisions"] != prior.get("revisions"):
            raise ValueError("Accepted baseline or revisions changed")
        if (
            prior["collection_receipt_sha256"] != result["collection_receipt_sha256"]
            or prior["collection_run_id"] != collection
        ):
            raise ValueError("Accepted source collection receipt changed")
        for name, frame in outputs.items():
            try:
                pd.testing.assert_frame_equal(
                    pd.read_parquet(workspace / "data" / (name + ".parquet")), frame, check_exact=True
                )
            except AssertionError as exc:
                raise ValueError(f"Candidate output differs from its originals: {name}") from exc
        result["output_sha256"] = {name: sha(workspace / "data" / (name + ".parquet")) for name in outputs}
        if result["output_sha256"] != prior["output_sha256"]:
            raise ValueError("Accepted artifact hash changed")
        return result
    from src.ingest.stage4_common import write_parquet_atomic

    with writer(workspace):
        if accepted.exists() or any(p.exists() for p in allowed):
            raise ValueError("Candidate outputs are immutable; use a new workspace")
        for name, frame in outputs.items():
            write_parquet_atomic(frame, workspace / "data" / (name + ".parquet"))
        result["output_sha256"] = {name: sha(workspace / "data" / (name + ".parquet")) for name in outputs}
        serialized = json.dumps(result, indent=2) + "\n"
        (workspace / "receipts" / f"aerocivil-{uuid4().hex}.json").write_text(serialized)
        accepted.write_text(serialized)
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["recipe", "certify", "availability"])
    parser.add_argument("--period", required=True)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--as-of")
    parser.add_argument("--collection")
    parser.add_argument("--baseline", help="Explicit previous candidate Parquet under baselines/")
    selections = parser.add_mutually_exclusive_group()
    selections.add_argument(
        "--metadata", action="store_true", help="Emit the supporting official dictionary selection"
    )
    selections.add_argument(
        "--availability",
        action="store_true",
        help="Emit one maximum-month query for the selected period's year",
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--execute", action="store_true")
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.mode == "recipe":
            recipe(args.period)
            if args.metadata:
                result = metadata_selection()
            elif args.availability:
                result = availability_selection(args.period[:4])
            else:
                result = recipe(args.period)
        else:
            if not all((args.workspace, args.as_of, args.collection)):
                raise ValueError("Certification requires workspace, cutoff and collection receipt ID")
            if args.mode == "availability":
                recipe(args.period)
                result = availability(args.workspace, args.period[:4], args.as_of, args.collection)
            else:
                result = run(
                    args.workspace,
                    args.period,
                    args.as_of,
                    args.collection,
                    execute=args.execute,
                    check=args.check,
                    baseline=args.baseline,
                )
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc), "activation": "none"}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
