"""Same-dataset Aerocivil metadata and bounded availability discovery, without activation."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

from src.ingest.international_routes import CO_URL
from src.source_updates.calendar import local_time
from src.source_updates.checks import verify_bronze
from src.source_updates.collection import safe_workspace, validate_url

METADATA_URL = "https://www.datos.gov.co/api/views/jh8x-n6h6.json"


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
