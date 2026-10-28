"""Offline import and verification of one authorized ASUR editable reconstruction."""

import argparse
import csv
import hashlib
import io
import json
import os
import re
import shutil
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from bs4 import BeautifulSoup

from src.source_updates.asur_reconstructed import ALIAS, PERIOD, URL
from src.source_updates.calendar import local_time
from src.source_updates.collection import safe_workspace, writer

FILES = {
    "reconstruction_json": (
        "asur-september-2026-reconstructed.json",
        183344,
        "b6254c5108ed4128f0d3d7eae4418e342843bcbb893ef0d0abcc5e555b056835",
        "application/json",
    ),
    "reconstruction_html": (
        "asur-september-2026-reconstructed.html",
        155721,
        "09fdac34a5a3aa057128953ef2171ef5da124f32312c08dbedfff6b2af746301",
        "text/html",
    ),
    "reconstruction_csv": (
        "asur-september-2026-reconstructed.csv",
        35398,
        "28f8fcc45b631a23c9df26d9e36fe684397810e8c159706f49ce8df12a360c26",
        "text/csv",
    ),
    "reconstruction_manifest": (
        "asur-september-2026-reconstructed-manifest.json",
        4248,
        "e39bb0783c540f5cd2c8be7a342e7623da27bece0314984e8565f9050d3abbe2",
        "application/json",
    ),
}
KEYS = ("september_2025", "september_2026", "september_change_pct", "ytd_2025", "ytd_2026", "ytd_change_pct")
TABLES = (
    ("summary", "Passenger Traffic Summary", 15),
    ("mexico", "Mexico Passenger Traffic", 30),
    ("brazil_and_others", "Brazil and Others Passenger Traffic", 75),
    ("san_juan", "U.S. Passenger Traffic, San Juan Airport (LMM)", 3),
    ("colombia", "Colombia Passenger Traffic", 21),
)
OBSERVED_AT = "2026-10-28T01:53:22Z"
LIBRARY_IDENTITY_SET_SHA = "f1dba30cef92a89f535e33b74e29dcfdd8f296a2496e18cc61543939db2d6019"


def validate_library_identities(identities):
    # Bind the actual four materialized Library identities without publishing
    # their private identifiers in code. This is provenance, not an approval.
    actual = hashlib.sha256(
        json.dumps(identities, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if set(identities) != set(FILES) or actual != LIBRARY_IDENTITY_SET_SHA:
        raise ValueError("ASUR Library identities differ from the verified reconstruction handoff")


def validate_document(document):
    """Validate raw cells independently of the parent producer's QA flags."""
    meta = document["metadata"]
    contract = meta["data_contract"]
    if not (
        meta["reconstructed"] is True
        and meta["reconstruido"] is True
        and meta["not_original"] is True
        and meta["source_original_bytes_acquired"] is False
        and meta["source_original_sha256"] is None
        and meta["source_url"] == URL
        and meta["source_publication_date"] == "2026-10-07"
        and meta["observation_time_utc"] == OBSERVED_AT
        and meta["production_publication"] is False
        and meta["calendar_or_ingestion_enabled"] is False
        and contract["unit"] == "passenger_count"
        and contract["percent_unit"] == "percent_change"
        and contract["columns_order"] == list(KEYS)
        and contract["raw_cells_authoritative"] is True
        and contract["periods"]["monthly_2025"] == {"start": "2025-09-01", "end": "2025-09-30"}
        and contract["periods"]["monthly_2026"] == {"start": "2026-09-01", "end": "2026-09-30"}
        and contract["periods"]["ytd"]["start_date_explicit_in_source"] is None
        and contract["periods"]["ytd"]["coverage_uniform_across_portfolio"] is False
    ):
        raise ValueError("ASUR reconstruction identity, units, periods or provenance claims differ")
    observation = local_time(meta["observation_time_utc"])
    if observation.date().isoformat() < "2026-10-07":
        raise ValueError("ASUR visible observation predates the report")
    tables = document["tables"]
    if len(tables) != 5:
        raise ValueError("Require all five retained reconstructed tables")
    dashes, cells, percentages = 0, 0, 0
    for table, (identifier, title, count) in zip(tables, TABLES, strict=True):
        if table["id"] != identifier or table["title_raw"] != title or len(table["rows"]) != count:
            raise ValueError("ASUR table identity, coverage or row domain changed")
        for position, row in enumerate(table["rows"], 1):
            if row["source_row_number"] != position or row["label_cells_raw"] != (
                ([row["code_raw"]] if row["code_raw"] else []) + [row["label_raw"]]
            ):
                raise ValueError("ASUR reconstructed label or physical row identity changed")
            if any(set(row[field]) != set(KEYS) for field in ("cells_raw", "values", "cell_status")):
                raise ValueError("ASUR reconstructed count/percent column domain changed")
            for key in KEYS:
                raw, value, status = row["cells_raw"][key], row["values"][key], row["cell_status"][key]
                cells += 1
                if raw == "-":
                    if value is not None or status != "source_dash_not_interpreted_as_zero":
                        raise ValueError("ASUR source dash must remain unknown, never zero")
                    dashes += 1
                    continue
                pct = key.endswith("pct")
                pattern = r"(?:\d+\.\d|\(\d+\.\d\))" if pct else r"(?:0|[1-9]\d*|[1-9]\d{0,2}(?:,\d{3})+)"
                if not isinstance(raw, str) or not re.fullmatch(pattern, raw):
                    raise ValueError("ASUR raw cell precision or count units changed")
                expected = Decimal(raw.replace(",", "").replace("(", "-").replace(")", ""))
                if (
                    isinstance(value, bool)
                    or value is None
                    or Decimal(str(value)) != expected
                    or status != "reported"
                ):
                    raise ValueError("ASUR normalized value differs from authoritative raw cell")
            for prefix in ("september", "ytd"):
                a, b, pct = [row["values"][prefix + suffix] for suffix in ("_2025", "_2026", "_change_pct")]
                if a is not None and b is not None and pct is not None and a != 0:
                    calculated = (Decimal(str(b)) / Decimal(str(a)) - 1) * 100
                    if abs(calculated - Decimal(str(pct))) > Decimal("0.05"):
                        raise ValueError("ASUR printed percentage is inconsistent with its raw counts")
                    percentages += 1
            if identifier == "brazil_and_others" and any(
                row["cells_raw"][a] != row["cells_raw"][b]
                for a, b in (("september_2025", "ytd_2025"), ("september_2026", "ytd_2026"))
            ):
                raise ValueError("ASUR reviewed CPC coverage no longer repeats its acquisition-month counts")
    if (cells, dashes, percentages) != (864, 155, 236):
        raise ValueError("ASUR full retained cell/dash/percentage inventory changed")
    return {
        "tables": 5,
        "rows": 144,
        "cells": cells,
        "unknown_dash_cells": dashes,
        "printed_percentage_checks": percentages,
        "CPC_YTD_not_nine_months": True,
    }


def decode(files):
    """Check all formats; hashes below identify generated representations only."""
    if set(files) != set(FILES):
        raise ValueError("ASUR reconstruction requires JSON, HTML, CSV and reconstruction manifest")
    for role, raw in files.items():
        _, size, sha, _ = FILES[role]
        if len(raw) != size or hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError("Reviewed reconstructed artifact bytes changed; not a SEC-original hash")
    document = json.loads(files["reconstruction_json"])
    proof = validate_document(document)
    manifest = json.loads(files["reconstruction_manifest"])
    if (
        manifest["source_url"] != URL
        or manifest["reconstruido"] is not True
        or manifest["source_original_sha256"] is not None
        or manifest["source_original_bytes_acquired"] is not False
        or manifest["observed_at_utc"] != document["metadata"]["observation_time_utc"]
    ):
        raise ValueError("Reconstruction manifest makes incompatible original/observation claims")
    expected_artifacts = {
        name: (size, sha, mime)
        for role, (name, size, sha, mime) in FILES.items()
        if role != "reconstruction_manifest"
    }
    if {
        r["filename"]: (r["bytes"], r["sha256"], r["mime_type"]) for r in manifest["artifacts"]
    } != expected_artifacts:
        raise ValueError("ASUR manifest does not bind the three generated views")
    tables_sha = hashlib.sha256(
        json.dumps(document["tables"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if manifest["tables_content_sha256"] != tables_sha:
        raise ValueError("ASUR reconstructed tables fingerprint changed")
    soup = BeautifulSoup(files["reconstruction_html"], "html.parser")
    scripts = soup.find_all("script")
    if (
        len(scripts) != 1
        or scripts[0].get("type") != "application/json"
        or scripts[0].get("id") != "asur-reconstructed-data"
    ):
        raise ValueError("Reconstruction may contain data JSON only, never executable script")
    if json.loads(scripts[0].string) != document:
        raise ValueError("ASUR editable HTML embedded representation differs from JSON")
    html_tables = soup.find_all("table")
    flat = []
    if len(html_tables) != 5:
        raise ValueError("ASUR editable HTML table inventory differs")
    for html, table in zip(html_tables, document["tables"], strict=True):
        rows = html.find_all("tr", attrs={"data-source-line": True})
        if len(rows) != len(table["rows"]):
            raise ValueError("ASUR HTML row inventory differs")
        for hr, row in zip(rows, table["rows"], strict=True):
            visible = [c.get_text(" ", strip=True) for c in hr.find_all(["td", "th"], recursive=False)]
            expected = [row["code_raw"] or "", row["label_raw"]] + [row["cells_raw"][k] for k in KEYS]
            if visible != expected or hr["data-source-line"] != str(row["source_visible_line"]):
                raise ValueError("ASUR editable HTML raw cells/labels differ")
            flat.append((table, row))
    csv_rows = list(csv.DictReader(io.StringIO(files["reconstruction_csv"].decode("utf-8-sig"))))
    if len(csv_rows) != len(flat):
        raise ValueError("ASUR editable CSV row inventory differs")
    for cr, (table, row) in zip(csv_rows, flat, strict=True):
        expected = {
            "reconstructed": "true",
            "source_url": URL,
            "observation_date": document["metadata"]["observation_date"],
            "table_id": table["id"],
            "table_title": table["title_raw"],
            **{k: str(row[k]) for k in ("source_page", "source_visible_line", "source_row_number")},
            **{
                k: row[k] or ""
                for k in ("traffic_type", "group_context", "country_context", "code_raw", "label_raw")
            },
            **row["cells_raw"],
        }
        if cr != expected:
            raise ValueError("ASUR editable CSV raw cells/labels differ")
    return document, {
        **proof,
        "all_four_reconstructed_artifacts_verified": True,
        "tables_sha256": tables_sha,
        "original_SEC_hash": None,
    }


def validate_record(row):
    role = row.get("representation_role")
    if role not in FILES:
        raise ValueError("Unknown ASUR reconstruction artifact role")
    name, size, sha, mime = FILES[role]
    if not (
        row.get("source_system") == ALIAS
        and row.get("source_url") == URL
        and row.get("source_file") == "asur/reconstructed/" + name
        and row.get("bytes") == size
        and row.get("sha256") == sha
        and row.get("content_type") == mime
        and row.get("timestamp_semantics") == "local_import_not_SEC_HTTP_capture"
        and row.get("source_url_role") == "upstream_visible_reference_not_artifact_download_URL"
        and row.get("source_observed_at") == OBSERVED_AT
        and row.get("logical_key") == f"{ALIAS}|ASUR_{role}|{PERIOD}|{name.rsplit('.', 1)[1]}"
        and type(row.get("logical_version")) is int
        and row["logical_version"] == 1
        and type(row.get("filename_version")) is int
        and row["filename_version"] == 1
        and row.get("is_content_alias") is False
        and row.get("download_method") == "authorized_visible_reconstruction_import"
        and row.get("http_status") == 0
        and row.get("source_http_status") is None
        and row.get("representation_kind") == "authorized_visible_reconstruction"
        and row.get("source_original_sha256") is None
        and row.get("source_original_bytes_acquired") is False
    ):
        raise ValueError("ASUR derived provenance cannot claim original SEC download/bytes/hash")


def import_representation(source_root, workspace, *, execute=False):
    source_root, workspace = safe_workspace(Path(source_root)), safe_workspace(Path(workspace))
    if (
        source_root == workspace
        or source_root.is_relative_to(workspace)
        or workspace.is_relative_to(source_root)
    ):
        raise ValueError("ASUR Library representations and import workspace must be disjoint")
    raw, identities = {}, {}
    for role, (name, _, _, _) in FILES.items():
        path = source_root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Require regular, materialized reconstructed files, without symlinks")
        identity = os.getxattr(path, "user.library-file-id", follow_symlinks=False).decode()
        if not re.fullmatch(r"libfile_[a-f0-9]{32}", identity):
            raise ValueError("Preserve the reconstructed file's actual Library identity")
        raw[role], identities[role] = path.read_bytes(), identity
    validate_library_identities(identities)
    document, proof = decode(raw)
    plan = {
        "mode": "reconstruction_import" if execute else "dry_run",
        "product": "asur_traffic",
        "period": PERIOD,
        "source_representation": "authorized_visible_reconstruction",
        "is_original_SEC_HTML": False,
        "source_original_sha256": None,
        "source_observed_at": document["metadata"]["observation_time_utc"],
        "library_file_ids": identities,
        "proof": proof,
        "network_requests": 0,
        "activation": "none",
        "publication": "not_authorized",
    }
    if not execute:
        return plan
    manifest = workspace / "data/bronze/_manifest.jsonl"
    if manifest.exists() or (workspace / "data/bronze").exists():
        raise ValueError("Use a new reconstruction import workspace; never overwrite an existing candidate")
    imported_at = datetime.now(UTC).isoformat()
    if local_time(imported_at) < local_time(plan["source_observed_at"]):
        raise ValueError("Reconstruction import predates its visible-source observation")
    records = {}
    with writer(workspace):
        if manifest.exists():
            raise ValueError("ASUR reconstruction import already exists")
        for role, (name, size, sha, mime) in FILES.items():
            relative = "asur/reconstructed/" + name
            record = dict(
                source_system=ALIAS,
                source_url=URL,
                source_file=relative,
                sha256=sha,
                bytes=size,
                content_type=mime,
                http_status=0,
                source_http_status=None,
                downloaded_at=imported_at,
                timestamp_semantics="local_import_not_SEC_HTTP_capture",
                source_observed_at=plan["source_observed_at"],
                download_method="authorized_visible_reconstruction_import",
                representation_kind="authorized_visible_reconstruction",
                representation_role=role,
                source_original_sha256=None,
                source_original_bytes_acquired=False,
                source_url_role="upstream_visible_reference_not_artifact_download_URL",
                library_file_id=identities[role],
                logical_key=f"{ALIAS}|ASUR_{role}|{PERIOD}|{name.rsplit('.', 1)[1]}",
                logical_version=1,
                filename_version=1,
                is_content_alias=False,
            )
            validate_record(record)
            path = workspace / "data/bronze" / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                raise ValueError("Preserve partial reconstruction imports, never overwrite")
            shutil.copy2(source_root / name, path)
            if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                raise ValueError("Reconstructed file changed during import")
            Path(str(path) + ".meta.json").write_text(json.dumps(record, indent=2) + "\n")
            records[role] = record
        manifest.write_text("".join(json.dumps(r) + "\n" for r in records.values()))
        result = {
            **plan,
            "status": "imported_reconstruction_unvalidated",
            "run_id": uuid4().hex,
            "imported_at": imported_at,
            "records": records,
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        }
        receipts = workspace / "receipts"
        receipts.mkdir(exist_ok=True)
        (receipts / f"asur-reconstruction-import-{result['run_id']}.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        print(
            json.dumps(
                import_representation(args.source_root, args.workspace, execute=args.execute),
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        return 0
    except (ValueError, KeyError, OSError, TypeError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc), "activation": "none"}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
