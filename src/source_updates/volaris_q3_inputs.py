"""Import one authorized Library reconstruction ZIP, never an original SEC filing."""

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from bs4 import BeautifulSoup

from src.source_updates.collection import safe_workspace, writer
from src.source_updates.volaris_q3_reconstructed import (
    ALIAS,
    FILING,
    PERIOD,
    URLS,
    validate_filing_context,
    zoned_timestamp,
)

NAME = "Volaris_3T2026_paquete_reconstruido.zip"
SIZE = 39039
SHA = "b94aa81a91dc086f26b6ccb37567bf8151596d2cc40e51df221a296a7baca70f"
LIBRARY_SHA = "e5a5cce2b9ead192ccc9d8809ca989d09f758f1b049c8fa05facb128c63a853a"
JSON_NAME = "Volaris_3T2026_datos_reconstruidos.json"
HTML_NAME = "Volaris_3T2026_copia_editable.html"
MANIFEST_NAME = "Volaris_3T2026_manifest_reconstruccion.json"
MEMBERS = {
    HTML_NAME: (100376, "059f4b9013500d7221690fa6867062dee8f443832b476c390ed5247ff27c0208"),
    JSON_NAME: (323743, "d600f5d71a5186449f79c58d56396999c95adc5e59bb2106bac3889dcd6bb876"),
    MANIFEST_NAME: (4760, "bb8eb139f1db3e166bb4806d527a79f89a4414f0352dc0daab8fbbb824d8e72a"),
    "verification-independent.json": (
        44353,
        "14a1b237d14d6b642733c8aa14ce0381473bc415be6a4e982030dc8b22fdc12b",
    ),
    "LEEME.txt": (1386, "2e9e8e358f321902d8b3a138cb74bde35ebe8ec6620cd4ecf92ae1c2f4d58510"),
}
VERIFIED_AT = "2026-10-28T13:16:03.681938+00:00"
ROLE = "reconstruction_zip"


def validate_document(document):
    meta = document["metadata"]
    context = dict(
        FILING,
        source_urls={
            "exhibit": meta["source_url"],
            "primary": meta["cover_url"],
            "index": meta["index_url"],
            "submissions": meta["submissions_url"],
        },
    )
    for dst, src in [
        ("cik", "cik"),
        ("accession_number", "accession"),
        ("form", "form"),
        ("report_date", "report_date"),
        ("filing_date", "filing_date"),
        ("acceptance_at", "acceptance_datetime_utc"),
    ]:
        context[dst] = meta[src]
    validate_filing_context(context)
    if not (
        meta["period"] == PERIOD
        and meta["release_date"] == "2026-10-26"
        and meta["reconstruido"] is True
        and meta["hash_original"] is None
        and meta["original_downloaded"] is False
        and meta["original_byte_count_verified"] is False
    ):
        raise ValueError("Volaris derivative cannot claim SEC original bytes or another period")
    tables = document["tables"]
    if (
        len(tables),
        sum(len(t["rows"]) for t in tables),
        sum(len(r["cells"]) for t in tables for r in t["rows"]),
    ) != (20, 309, 1198):
        raise ValueError("Volaris reconstructed substantive table inventory differs")
    seen, numeric, dashes = set(), 0, 0
    for t in tables:
        if t["source_dom_table_index"] in seen or t["source_url"] != URLS["exhibit"]:
            raise ValueError("Volaris reconstructed table identity differs")
        seen.add(t["source_dom_table_index"])
        positions = [r["source_row_index"] for r in t["rows"]]
        if positions != sorted(set(positions)):
            raise ValueError("Volaris reconstructed source row identifiers differ")
        for r in t["rows"]:
            for cell in r["cells"]:
                if cell["kind"] == "number":
                    raw = cell["display"].strip()
                    token = re.sub(r"(?:%| pp|x|Ps\.\s*|\$)", "", raw).replace(",", "")
                    value = Decimal(token.replace("(", "-").replace(")", ""))
                    if type(cell["value"]) not in (int, float) or Decimal(str(cell["value"])) != value:
                        raise ValueError("Volaris raw and normalized reconstructed cells disagree")
                    numeric += 1
                elif cell["kind"] == "reported_dash":
                    if cell["value"] is not None or cell["display"].strip() != "-":
                        raise ValueError("Volaris unknown dash must not become zero")
                    dashes += 1
    if numeric != 668 or dashes != 7:
        raise ValueError("Volaris reconstructed numeric and unknown-cell counts differ")
    return {
        "substantive_tables": 20,
        "represented_rows": 309,
        "represented_cells": 1198,
        "normalized_number_cells_checked": numeric,
        "unknown_dash_cells": dashes,
    }


def decode(raw):
    if len(raw) != SIZE or hashlib.sha256(raw).hexdigest() != SHA:
        raise ValueError("Authorized Volaris reconstructed ZIP differs; this is not an SEC original pin")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if len(z.infolist()) != len(MEMBERS) or set(z.namelist()) != set(MEMBERS):
            raise ValueError("Volaris reconstruction requires its five exact bounded ZIP members")
        files = {}
        for name, (size, sha) in MEMBERS.items():
            info = z.getinfo(name)
            if (
                info.file_size != size
                or info.flag_bits & 1
                or (info.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError("Volaris ZIP member structure differs")
            files[name] = z.read(name)
            if hashlib.sha256(files[name]).hexdigest() != sha:
                raise ValueError("Volaris reconstructed member bytes differ")
    document = json.loads(files[JSON_NAME])
    proof = validate_document(document)
    manifest = json.loads(files[MANIFEST_NAME])
    if manifest["metadata"] != document["metadata"] or manifest["coverage"] != document["coverage"]:
        raise ValueError("Volaris reconstructed manifest identity/coverage differs")
    if {x["filename"]: (x["size_bytes"], x["sha256"]) for x in manifest["derived_files"]} != {
        name: pair for name, pair in MEMBERS.items() if name != MANIFEST_NAME
    }:
        raise ValueError("Volaris manifest must bind actual derivative files only")
    verification = json.loads(files["verification-independent.json"])
    if verification["verified_at_utc"] != VERIFIED_AT or verification["hash_original"] is not None:
        raise ValueError("Volaris independent visible-read time/original claims differ")
    # Read structure and text only. The pinned editable UI script is never run.
    soup = BeautifulSoup(files[HTML_NAME], "html.parser")
    html_tables = soup.find_all("table")
    if len(html_tables) != 20:
        raise ValueError("Volaris reconstructed HTML table inventory differs")
    for html, table in zip(html_tables, document["tables"], strict=True):
        rows = html.find_all("tr")
        if len(rows) != len(table["rows"]):
            raise ValueError("Volaris reconstructed HTML/JSON row count differs")
        for tr, row in zip(rows, table["rows"], strict=True):
            cells = tr.find_all(["td", "th"], recursive=False)
            if len(cells) != len(row["cells"]):
                raise ValueError("Volaris reconstructed HTML/JSON column count differs")
            for col, (td, cell) in enumerate(zip(cells, row["cells"], strict=True)):
                if (
                    td.get("data-source-row") != str(row["source_row_index"])
                    or td.get("data-source-column") != str(col)
                    or " ".join(td.get_text().split()) != " ".join(cell["display"].split())
                    or int(td.get("colspan", 1)) != cell["colspan"]
                    or int(td.get("rowspan", 1)) != cell["rowspan"]
                ):
                    raise ValueError("Volaris reconstructed HTML/JSON text, spans or locator differ")
    return document, {
        **proof,
        "source_representation": "authorized_visible_reconstruction",
        "source_observed_at": VERIFIED_AT,
        "source_observation_semantics": "independent_visible_read_completed_at_not_HTTP_or_first_publication",
        "source_original_sha256": None,
        "source_original_bytes_acquired": False,
        "upstream_metadata_is_observed_not_original_documents": True,
        "reconstructed_artifact_sha256": SHA,
        "visual_browser_QA": "not_completed",
        "provenance_warning": "Reconstrucción editable autorizada; cifras y metadatos observados en SEC, "
        "sin bytes originales SEC ni equivalencia binaria; notas resumidas propias. No publicación.",
    }


def validate_record(row):
    if zoned_timestamp(row.get("downloaded_at")) < zoned_timestamp(VERIFIED_AT):
        raise ValueError("Volaris local import cannot predate its independently verified visible read")
    if not (
        row.get("source_system") == ALIAS
        and row.get("source_url") == URLS["exhibit"]
        and row.get("sha256") == SHA
        and row.get("bytes") == SIZE
        and type(row.get("bytes")) is int
        and row.get("representation_role") == ROLE
        and row.get("representation_kind") == "authorized_visible_reconstruction"
        and row.get("download_method") == "authorized_visible_reconstruction_import"
        and row.get("http_status") == 0
        and type(row.get("http_status")) is int
        and row.get("source_http_status") is None
        and row.get("source_original_sha256") is None
        and row.get("source_original_bytes_acquired") is False
        and row.get("source_observed_at") == VERIFIED_AT
        and row.get("timestamp_semantics") == "local_import_not_SEC_HTTP_capture"
        and row.get("source_url_role") == "upstream_visible_reference_not_artifact_download_URL"
        and row.get("content_type") == "application/zip"
        and hashlib.sha256(str(row.get("library_file_id")).encode()).hexdigest() == LIBRARY_SHA
    ):
        raise ValueError(
            "Volaris derivative metadata cannot impersonate a SEC capture or another Library file"
        )


def validate_import_artifact(root, row):
    from src.source_updates.primary_review import within

    validate_record(row)
    path = within(root, row["source_file"])
    sidecar = within(root, row["source_file"] + ".meta.json")
    if (
        path.stat().st_size != SIZE
        or hashlib.sha256(path.read_bytes()).hexdigest() != SHA
        or json.loads(sidecar.read_text()) != row
        or os.getxattr(path, "user.library-file-id", follow_symlinks=False).decode() != row["library_file_id"]
    ):
        raise ValueError("Volaris derived packet body, sidecar or Library identity differs")
    if not any(json.loads(line) == row for line in (root / "_manifest.jsonl").read_text().splitlines()):
        raise ValueError("Volaris derived packet absent from its physical import manifest")
    decode(path.read_bytes())
    return path


def import_packet(source, workspace, *, execute=False):
    source, workspace = Path(source), safe_workspace(Path(workspace))
    if not source.is_file() or any(p.is_symlink() for p in (source, *source.parents)):
        raise ValueError("Use a regular materialized Library ZIP without symlinks")
    source = source.resolve()
    if source.is_relative_to(workspace):
        raise ValueError("Use a regular materialized Library ZIP outside the new import workspace")
    identity = os.getxattr(source, "user.library-file-id", follow_symlinks=False).decode()
    if hashlib.sha256(identity.encode()).hexdigest() != LIBRARY_SHA:
        raise ValueError("Volaris packet Library identity differs from the verified handoff")
    _, proof = decode(source.read_bytes())
    plan = {
        "product": "volaris_sec",
        "period": PERIOD,
        "proof": proof,
        "network_requests": 0,
        "source_original_sha256": None,
        "source_representation": "authorized_visible_reconstruction",
        "activation": "none",
        "publication": "not_authorized",
    }
    if not execute:
        return {**plan, "status": "planned_not_executed"}
    with writer(workspace):
        manifest = workspace / "data/bronze/_manifest.jsonl"
        if (workspace / "data/bronze").exists():
            raise ValueError("Use a new Volaris import workspace; preserve prior/partial imports")
        imported_at = datetime.now(UTC).isoformat()
        relative = "volaris/reconstructed/" + NAME
        row = dict(
            source_system=ALIAS,
            source_url=URLS["exhibit"],
            source_file=relative,
            sha256=SHA,
            bytes=SIZE,
            content_type="application/zip",
            http_status=0,
            source_http_status=None,
            downloaded_at=imported_at,
            timestamp_semantics="local_import_not_SEC_HTTP_capture",
            source_observed_at=VERIFIED_AT,
            download_method="authorized_visible_reconstruction_import",
            representation_kind="authorized_visible_reconstruction",
            representation_role=ROLE,
            source_original_sha256=None,
            source_original_bytes_acquired=False,
            source_url_role="upstream_visible_reference_not_artifact_download_URL",
            library_file_id=identity,
            logical_key=f"{ALIAS}|VOLARIS_{ROLE}|{PERIOD}|zip",
            logical_version=1,
            filename_version=1,
            is_content_alias=False,
        )
        validate_record(row)
        dest = workspace / "data/bronze" / relative
        dest.parent.mkdir(parents=True)
        shutil.copy2(source, dest)
        if hashlib.sha256(dest.read_bytes()).hexdigest() != SHA:
            raise ValueError("Volaris reconstruction changed during import")
        Path(str(dest) + ".meta.json").write_text(json.dumps(row, indent=2) + "\n")
        manifest.write_text(json.dumps(row) + "\n")
        result = {
            **plan,
            "status": "imported_reconstruction_unvalidated",
            "run_id": uuid4().hex,
            "mode": "reconstruction_import",
            "imported_at": imported_at,
            "records": {ROLE: row},
            "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        }
        receipts = workspace / "receipts"
        receipts.mkdir(exist_ok=True)
        (receipts / f"volaris-reconstruction-import-{result['run_id']}.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--execute", action="store_true")
    group.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            import_packet(args.source, args.workspace, execute=args.execute), indent=2, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
