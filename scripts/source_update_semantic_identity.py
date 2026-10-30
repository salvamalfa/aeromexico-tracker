"""Versioned business/context identity, separate from immutable capture provenance.

Only already-verified, retained dossiers are read. This module acquires nothing,
changes no ledger and does not admit a new edition or representation.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from bs4 import BeautifulSoup, Comment
from pypdf import PdfReader

from scripts.source_update_coordinator import digest
from src.pipeline.offline import block_network
from src.source_updates.retained import originals

SCHEMA = "source_semantic_identity_v2"
FINANCIALS = {"am_financials", "viva_financials", "volaris_sec"}
# Keep the original v1 projection intact for existing source IDs/worker receipts.
LEGACY_PROVENANCE = {
    "record_id",
    "source_file",
    "source_hash",
    "ingested_at",
    "parser_version",
    "source_locator",
    "source_row_number",
    "source_column",
    "source_table",
    "native_parent_record_ids",
    "native_parent_record_id",
}
CAPTURE_FIELDS = {"downloaded_at", "artifact_id", "source_url"}


def compact(value):
    return " ".join(value.split())


def visible_text(node):
    for comment in node.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for child in node.find_all(["script", "style"]):
        child.decompose()
    node.smooth()
    return compact(node.get_text(" ", strip=True))


def html_text(raw):
    return visible_text(BeautifulSoup(raw, "html.parser"))


def pdf_text(raw):
    if not raw.startswith(b"%PDF-") or not 0 < len(raw) <= 4_000_000:
        raise ValueError("Primary financial PDF is missing or outside reviewed bounds")
    pages = [compact(page.extract_text() or "") for page in PdfReader(io.BytesIO(raw)).pages]
    if not pages or any(not page for page in pages):
        raise ValueError("Primary financial context requires nonempty text on every admitted page")
    return compact(" ".join(pages))


def primary_context(item):
    """Normalize visible admitted report content, never its container/capture hash."""
    product, period = item["product"], item["period"]
    if product not in FINANCIALS:
        return None
    if period not in {"2026Q2", "2026Q3"}:
        raise ValueError("Semantic context supports only the already reviewed Q2/Q3 dossiers")
    with block_network():
        inputs, _ = originals(Path(item["workspace"]), product, item["receipt_id"], item["candidate_as_of"])
        if product == "am_financials":
            if period == "2026Q3" and set(inputs) == {"html"}:
                from src.source_updates.financials_html import document

                raw, meta = inputs["html"]
                context = {"financial_exhibit_99_1": visible_text(document(raw, meta))}
            elif period == "2026Q2" and set(inputs) == {"pdf"}:
                context = {"pdf": pdf_text(inputs["pdf"][0])}
            else:
                raise ValueError("AM context needs the exact reviewed primary role/edition")
        elif product == "viva_financials":
            if set(inputs) != {"pdf", "prior_quarter"}:
                raise ValueError("Viva context needs its primary report and comparative support")
            context = {role: pdf_text(raw) for role, (raw, _) in sorted(inputs.items())}
        elif period == "2026Q3":
            from src.source_updates.volaris_q3_inputs import ROLE, decode, validate_record

            if set(inputs) != {ROLE}:
                raise ValueError("Volaris Q3 context requires its admitted reconstruction")
            raw, meta = inputs[ROLE]
            validate_record(meta)
            document, _ = decode(raw)  # Exact authorized ZIP/member pins remain mandatory.
            context = {
                "representation": "authorized_visible_reconstruction_not_SEC_original",
                "tables": [
                    [compact(cell["display"]) for row in table["rows"] for cell in row["cells"]]
                    for table in document["tables"]
                ],
                "notes": document["notes_es"],
            }
        elif set(inputs) == {"html", "primary", "submissions", "index"}:
            context = {"financial_exhibit": html_text(inputs["html"][0])}
        else:
            raise ValueError("Volaris context needs the complete reviewed original Q2 dossier")
    if not context or any(not value for value in context.values()):
        raise ValueError("Missing primary financial context; never fall back to Gold only")
    return context


def identity(item, legacy_facts):
    tables = {
        name: sorted(
            [{key: value for key, value in row.items() if key not in CAPTURE_FIELDS} for row in rows],
            key=lambda row: json.dumps(row, sort_keys=True, allow_nan=False),
        )
        for name, rows in legacy_facts["tables"].items()
    }
    return {
        "schema_version": SCHEMA,
        "product": item["product"],
        "period": item["period"],
        "tables": tables,
        "primary_context": primary_context(item),
    }


def versions(item, legacy_facts):
    value = identity(item, legacy_facts)
    return {
        "data_version": digest(value),
        "legacy_data_version": digest(legacy_facts),
        "meaningful_identity": {"schema_version": SCHEMA, "sha256": digest(value)},
    }


def bound_matches(source, fresh):
    """Continue old worker IDs only after exact replay of their own original binding."""
    if fresh.get("meaningful_identity") != {"schema_version": SCHEMA, "sha256": fresh["data_version"]}:
        raise ValueError("Verified source lacks its complete semantic identity")
    if source["checked"]["output_sha256"] != fresh["checked"]["output_sha256"]:
        return False
    marker = source.get("meaningful_identity")
    if marker is None:
        return source["data_version"] == fresh.get("legacy_data_version")
    if marker != fresh.get("meaningful_identity"):
        return False
    return source["data_version"] in {fresh["data_version"], fresh.get("legacy_data_version")}


def same_observation(prior, fresh, replay_previous):
    """Compare two physically verified editions; annotate only the existing source metadata."""
    if fresh.get("meaningful_identity") != {"schema_version": SCHEMA, "sha256": fresh["data_version"]}:
        raise ValueError("Verified source lacks its complete semantic identity")
    previous = replay_previous(prior["source_binding"])
    if not bound_matches(prior, previous):
        raise ValueError("Previous source no longer matches its immutable physical binding")
    if previous["meaningful_identity"] != fresh["meaningful_identity"]:
        return False
    prior["meaningful_identity"] = previous["meaningful_identity"]
    return True
