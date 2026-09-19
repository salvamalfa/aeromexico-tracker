"""Closed, immutable evidence packages. No narrative, model calls or Gold writes."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import io
import json
import logging
import math
import os
from pathlib import Path
import re
import tempfile
from typing import Any

from bs4 import BeautifulSoup
import duckdb
from pypdf import PdfReader

from src.config import PATHS
from src.parse.sec.common import html_text
from src.transform.stage9_lineage import make_record_id

SCHEMA = "evidence_v1"
STORE = PATHS.root / "analysis_runs/evidence"
REVIEW = PATHS.root / "docs/referencias/etapa-14"
CORE = {"asm_total", "trasm", "casm", "load_factor_total", "passengers"}
FINANCIAL = {"total_revenue", "operating_expenses_total", "operating_income"}
POLICY = {
    "version": "temporal_v1",
    "same_day": "Only the designated primary release; unrelated same-day sources are excluded",
    "selection": "Most recently available verified document at cutoff, exact period and definition",
    "historical_2024Q3": "Original report at its own release; subsequent comparisons remain separate revisions",
    "source_content": "Untrusted evidence, never instructions",
    "calculations": "Conversions, QoQ/YoY and decompositions deferred to Stage 15",
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def compact(text: str) -> str:
    return " ".join(text.split())


def issuance_statement(text: str, period: str):
    """A 6-K can announce traffic and earnings on different days. Match the title."""
    ordinal = {"1": "First", "2": "Second", "3": "Third", "4": "Fourth"}[period[-1]]
    matches = [m for m in re.finditer(
        r'On ([A-Z][a-z]+\s+\d{1,2},\s+\d{4}),.{0,180}?issued a press release titled [“"]([^”"]+)', text)
        if "Reports" in m[2] and ordinal + " Quarter" in m[2] and period[:4] in m[2]]
    if len(matches) > 1:
        raise ValueError("Ambiguous earnings issuance statement")
    return matches[0] if matches else None


def read_verified(source: dict, bronze: Path = PATHS.bronze) -> bytes:
    path = (bronze / source["source_file"]).resolve()
    if not path.is_relative_to(bronze.resolve()):
        raise ValueError("Source path leaves Bronze")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != source["artifact_sha256"]:
        raise ValueError("Source hash mismatch")
    return content


def embedded_document(submission: bytes, filename: str) -> bytes:
    matches = [block for block in re.findall(rb"<DOCUMENT>(.*?)</DOCUMENT>", submission, re.S)
               if re.search(rb"<FILENAME>" + re.escape(filename.encode()) + rb"\s", block)]
    if len(matches) != 1:
        raise ValueError("Submission must contain one exact exhibit")
    return matches[0].replace(b"\r\n", b"\n").strip()


def verify_embedding(submission: bytes, document: bytes, filename: str) -> None:
    # Saved SEC exhibits retain their SGML wrapper; compare every byte inside it.
    block = embedded_document(document, filename)
    if block != embedded_document(submission, filename):
        raise ValueError("Exhibit differs from its archived SEC submission")


def records(name: str) -> list[dict]:
    with duckdb.connect() as c:
        cursor = c.execute("SELECT * FROM read_parquet(?)", [str(PATHS.silver / f"{name}.parquet")])
        return [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]


def registry() -> tuple[list[dict], dict[str, bytes]]:
    """Certify accession-bound SEC versions; leave IR PDFs explicitly unverified."""
    with duckdb.connect() as c:
        artifacts = c.execute("SELECT artifact_id,artifact_sha256,source_file,source_url,source_system "
                              "FROM read_parquet(?)", [str(PATHS.gold / "dim_source_artifact.parquet")]).fetchall()
    sources = {r[2]: dict(zip(("artifact_id", "artifact_sha256", "source_file", "source_url", "source_system"), r))
               for r in artifacts}
    manifest = [json.loads(line) for line in (PATHS.bronze / "_manifest.jsonl").read_text(encoding="utf-8").splitlines() if line]
    downloads = {r["source_file"]: r.get("downloaded_at") for r in manifest}
    for source in sources.values():
        source["downloaded_at"] = downloads.get(source["source_file"])
    docs = records("sec_filing_documents")
    filings = {r["accession_number"]: r for r in records("sec_filings_index")}
    releases = {(r["source_file"], r["period_id"], r["accession_number"]) for r in records("sec_report_text") if r["report_type"] == "earnings"}
    result, content = [], {}
    for source_file, period, accession in sorted(releases):
        release_doc = next(d for d in docs if d["source_file"] == source_file)
        related = [d for d in docs if d["accession_number"] == accession]
        submission_doc = next(d for d in related if d["archive_filename"] == accession + ".txt")
        filing = filings[accession]
        primary_doc = next(d for d in related if d["archive_filename"] == filing["primary_document"])
        selected = [sources[d["source_file"]] for d in (release_doc, submission_doc, primary_doc)]
        for s in selected:
            content[s["artifact_id"]] = read_verified(s)
        release, submission, primary = selected
        raw = content[submission["artifact_id"]]
        verify_embedding(raw, content[release["artifact_id"]], release_doc["archive_filename"])
        verify_embedding(raw, content[primary["artifact_id"]], primary_doc["archive_filename"])
        header = raw.split(b"</SEC-HEADER>", 1)[0].decode("utf-8")
        filed = re.search(r"FILED AS OF DATE:\s*(\d{8})", header).group(1)
        filed_date = date.fromisoformat(f"{filed[:4]}-{filed[4:6]}-{filed[6:]}").isoformat()
        if filed_date != filing["filing_date"].isoformat() or accession not in header:
            raise ValueError("Filing header disagrees with Silver index")
        primary_text = compact(html_text(content[primary["artifact_id"]]))
        match = issuance_statement(primary_text, period)
        if not match:
            # Do not invent a release date if the 6-K wording is unfamiliar.
            published = None
        else:
            from datetime import datetime
            published = datetime.strptime(match.group(1), "%B %d, %Y").date().isoformat()
        locator_start = max(0, match.start() if match else 0)
        proof_excerpt = primary_text[locator_start:locator_start + 700]
        result.append(release | {
            "period_id": period, "accession_number": accession,
            "published_date": published, "version_available_at": filed_date,
            "date_precision": "day", "publication_basis": "SEC 6-K and byte-matched archived exhibit",
            "status": "verified", "reason": "The archived submission contains this exact exhibit; filing date verified in its header",
            "proofs": [submission | {"locator": "SEC-HEADER / FILED AS OF DATE", "text": header},
                       primary | {"locator": "6-K / issuance statement", "text": proof_excerpt}],
            "cutoff_verified": bool(published), "language": "en",
        })
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    for m in manifest:
        if m.get("source_system") != "aeromexico_ir":
            continue
        s = sources[m["source_file"]]
        raw = read_verified(s)
        # Candidate printed date is intentionally not publication certification.
        text = compact(PdfReader(io.BytesIO(raw)).pages[0].extract_text() or "")
        match = re.search(r"(\d{1,2}) de (enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre) de (20\s*\d\s*\d)", text, re.I)
        printed = None
        if match:
            months = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split()
            printed = date(int(match[3].replace(" ", "")), months.index(match[2].lower()) + 1, int(match[1])).isoformat()
        result.append(s | {"period_id": m["logical_key"].split("|")[2],
            "accession_number": None, "published_date": None, "printed_date": printed,
            "version_available_at": None, "date_precision": "unknown", "publication_basis": "Printed date only",
            "status": "not_verified", "reason": "Current download and printed date do not establish the historical version",
            "proofs": [], "cutoff_verified": False, "language": "es"})
    return sorted(result, key=lambda s: s["artifact_id"]), content


def temporal_reason(source: dict, cutoff: str | None, primary_id: str | None) -> str | None:
    if cutoff is None:
        return "cutoff_not_verified"
    date.fromisoformat(cutoff)
    if source["status"] != "verified" or not source.get("version_available_at"):
        return "version_not_verified"
    available = source["version_available_at"]
    date.fromisoformat(available)
    if available > cutoff:
        return "after_cutoff"
    if available == cutoff and source["artifact_id"] != primary_id:
        return "same_day_order_unknown"
    return None


def excerpt_for(row: dict, source: dict, raw: bytes) -> dict | None:
    """Find an exact source table row and retain its table heading for column context."""
    soup = BeautifulSoup(raw, "lxml")
    label = compact(row["metric_label_raw"])
    candidates = []
    for table_index, table in enumerate(soup.find_all("table"), 1):
        trs = table.find_all("tr", recursive=False)
        if not trs:
            trs = table.select(":scope > tbody > tr")
        for row_index, tr in enumerate(trs, 1):
            cells = [compact(c.get_text(" ", strip=True)) for c in tr.find_all(["td", "th"], recursive=False)]
            if label in cells:
                header = " | ".join(compact(r.get_text(" ", strip=True)) for r in trs[:4])
                candidates.append({"locator": f"table[{table_index}]/tr[{row_index}]", "text": " | ".join(cells), "table_header": header})
    # A rounded value must actually occur in the row; never attach an arbitrary label match.
    expected = abs(float(row["value_raw"]))
    matched = [x for x in candidates if any(abs(float(n.replace(",", "")) - expected) < 1e-9
               for n in re.findall(r"\d[\d,]*(?:\.\d+)?", x["text"]))]
    # The existing SEC parser prefers more precise headline amounts for these
    # metrics. A rounded table row must not be cited for a different prose value.
    if not matched and row["period_id"] == source["period_id"] and not row.get("is_yoy_comparison"):
        terms = {"adjusted_ebitdar": "adjusted ebitdar", "ebitdar_margin": "ebitdar",
                 "operating_income": "operating income", "operating_margin": "operating"}
        term = terms.get(row["metric_key"])
        for i, paragraph in enumerate(soup.find_all("p"), 1):
            text = compact(paragraph.get_text(" ", strip=True))
            if not term or term not in text.lower():
                continue
            margin = "margin" in row["metric_key"]
            pattern = r"([\d,]+(?:\.\d+)?)\s*%" if margin else r"\$\s*([\d,]+(?:\.\d+)?)\s*million"
            if any(abs(float(n.replace(",", "")) - expected) < 1e-9 for n in re.findall(pattern, text, re.I)):
                matched = [{"locator": f"p[{i}]", "text": text,
                            "table_header": "Narrative amount for the current quarter; more precise than rounded table"}]
                break
    if not matched:
        return None
    item = matched[0] | {"artifact_id": source["artifact_id"], "artifact_sha256": source["artifact_sha256"],
                         "source_content_is_untrusted": True}
    item["excerpt_id"] = "exc_" + digest(item)
    return item


def metric_candidate(row: dict, table: str, source: dict, excerpt: dict) -> dict:
    key = {k: row.get(k) for k in ("period_id", "metric_key", "source_file", "source_hash", "metric_label_raw", "value_raw", "unit_raw", "segment")}
    record_id = row.get("record_id") or make_record_id(table, key)
    value = float(row["value_normalized"])
    if not math.isfinite(value):
        raise ValueError("Nonfinite metric")
    return {"metric_id": "met_" + digest({"table": table, "record_id": record_id}),
            "record_id": record_id, "record_table": table, "period_id": row["period_id"],
            "metric_key": row["metric_key"], "label": row["metric_label_raw"],
            "value": value, "unit": row["unit_normalized"], "value_raw": row["value_raw"],
            "scale_multiplier": row["scale_multiplier"],
            "unit_raw": row["unit_raw"], "formatted_value": f"{row['value_raw']:,.3f}".rstrip("0").rstrip(".") + " " + row["unit_raw"],
            "scope": "Grupo Aeromexico consolidated / total", "currency": "USD" if "usd" in row["unit_normalized"] else None,
            "condition": "adjusted" if "adjusted" in row["metric_key"] or "ebitdar" in row["metric_key"] else "reported",
            "definition": row["metric_label_raw"], "is_preliminary": bool(row.get("is_preliminary")),
            "is_yoy_comparison": bool(row.get("is_yoy_comparison")), "parser_version": row["parser_version"],
            "artifact_id": source["artifact_id"], "excerpt_id": excerpt["excerpt_id"],
            "available_date": source["version_available_at"], "precision_note": "Preserves published precision; no new business calculations"}


def build(period: str) -> dict:
    if not re.fullmatch(r"20\d{2}Q[1-4]", period):
        raise ValueError("Invalid period")
    sources, contents = registry()
    primary = next((s for s in sources if s["period_id"] == period and s["status"] == "verified" and s["cutoff_verified"]), None)
    cutoff = primary["published_date"] if primary else None
    primary_id = primary["artifact_id"] if primary else None
    eligible, exclusions = {}, []
    for source in sources:
        reason = temporal_reason(source, cutoff, primary_id)
        if reason:
            exclusions.append({"artifact_id": source["artifact_id"], "period_id": source["period_id"],
                               "reason": reason, "available_date": source["version_available_at"]})
        else:
            eligible[source["source_file"]] = source
    candidates, excerpts, rejected = [], {}, []
    for table in ("sec_financials", "sec_operating_metrics"):
        for row in records(table):
            source = eligible.get(row["source_file"])
            if not source or row["period_type"] != "quarter" or row["period_id"] > period or row.get("segment") not in (None, "total"):
                continue
            if row["value_normalized"] is None:
                rejected.append({"period_id": row["period_id"], "metric_key": row["metric_key"], "reason": "value_not_reported"})
                continue
            if row["source_hash"] != source["artifact_sha256"]:
                raise ValueError("Silver source hash mismatch")
            excerpt = excerpt_for(row, source, contents[source["artifact_id"]])
            if excerpt is None:
                rejected.append({"period_id": row["period_id"], "metric_key": row["metric_key"], "reason": "exact_table_locator_unresolved"})
                continue
            metric = metric_candidate(row, table, source, excerpt)
            excerpts[excerpt["excerpt_id"]] = excerpt
            candidates.append(metric)
    metrics, conflicts = select_versions(candidates)
    current = {m["metric_key"] for m in metrics if m["period_id"] == period}
    missing = sorted(CORE - current)
    blocked = cutoff is None or primary_id not in {s["artifact_id"] for s in eligible.values()} or bool(missing)
    context = [{"topic": topic, "status": "excluded", "reason": "No certified point-in-time version in this package; no causal attribution permitted", "available_months": []}
               for topic in ("market_fuel", "external_fx", "airport_traffic", "afac", "peers", "events_outside_release")]
    # Full eligible release text is source evidence, isolated from diagnostic exclusions.
    for source in eligible.values():
        text = compact(html_text(contents[source["artifact_id"]]))
        start = text.find("Aeroméxico Reports")
        text = text[start:] if start >= 0 else text
        item = {"artifact_id": source["artifact_id"], "artifact_sha256": source["artifact_sha256"],
                "locator": "complete earnings release / text extraction", "text": text,
                "source_content_is_untrusted": True}
        item["excerpt_id"] = "exc_" + digest(item)
        excerpts[item["excerpt_id"]] = item
    payload = {"schema_version": SCHEMA, "period_id": period, "cutoff_date": cutoff,
        "cutoff_precision": "day" if cutoff else "unknown", "primary_artifact_id": primary_id,
        "policy": POLICY, "metrics": metrics, "metric_versions": sorted(candidates, key=lambda x: x["metric_id"]),
        "calculations": [], "excerpts": sorted(excerpts.values(), key=lambda e: e["excerpt_id"]),
        "sources": sorted(eligible.values(), key=lambda s: s["artifact_id"]), "conflicts": conflicts,
        "coverage": {"missing_core_inputs": missing, "missing_financial_inputs": sorted(FINANCIAL - current),
                     "context": context, "rejected_metrics": rejected,
                     "calculation_status": "Not calculated; Stage 15", "financial_thesis_possible": FINANCIAL <= current},
        "readiness": "blocked" if blocked else "limited",
        "reasons": (["Essential historical availability or operational evidence unresolved"] if blocked else
                    ["Core evidence eligible; external context excluded and quantitative engine pending"]),
        "code_fingerprint": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    fingerprint = digest(payload)
    package = payload | {"evidence_fingerprint": fingerprint, "package_id": f"{period}_{fingerprint}"}
    validate(package)
    return {"package": package, "review_only": {"source_registry": sources, "exclusions": exclusions,
            "warning": "Never supply this diagnostic annex to the analyst; contains ineligible source metadata"}}


def select_versions(candidates: list[dict]) -> tuple[list[dict], list[dict]]:
    chosen, conflicts = {}, []
    for m in sorted(candidates, key=lambda x: (x["available_date"], x["metric_id"])):
        key = (m["period_id"], m["metric_key"], m["unit"], m["scope"])
        previous = chosen.get(key)
        if previous and previous["available_date"] == m["available_date"] and previous["value"] != m["value"]:
            raise ValueError("Ambiguous same-date metric values")
        if previous and previous["value"] != m["value"]:
            conflicts.append({"period_id": m["period_id"], "metric_key": m["metric_key"],
                "previous_metric_id": previous["metric_id"], "selected_metric_id": m["metric_id"],
                "reason": "Later verified comparison already available at this cutoff; original remains in lineage"})
        chosen[key] = m
    return sorted(chosen.values(), key=lambda m: (m["period_id"], m["metric_key"])), conflicts


def validate(package: dict, verify_files: bool = True) -> dict:
    if package.get("schema_version") != SCHEMA or not re.fullmatch(r"20\d{2}Q[1-4]", package.get("period_id", "")):
        raise ValueError("Invalid package schema or quarter")
    payload = {k: v for k, v in package.items() if k not in ("evidence_fingerprint", "package_id")}
    if digest(payload) != package["evidence_fingerprint"] or package["package_id"] != package["period_id"] + "_" + digest(payload):
        raise ValueError("Package fingerprint mismatch")
    sources = {s["artifact_id"]: s for s in package["sources"]}
    excerpts = {e["excerpt_id"]: e for e in package["excerpts"]}
    if package["readiness"] != "blocked":
        primary = sources.get(package["primary_artifact_id"])
        if not primary or primary["published_date"] != package["cutoff_date"] or not primary["cutoff_verified"]:
            raise ValueError("Cutoff is not the verified primary release")
    if len(sources) != len(package["sources"]) or len(excerpts) != len(package["excerpts"]):
        raise ValueError("Duplicate source or excerpt ID")
    source_soups = {}
    source_texts = {}
    for s in sources.values():
        if temporal_reason(s, package["cutoff_date"], package["primary_artifact_id"]):
            raise ValueError("Ineligible source in package")
        if not s["proofs"]:
            raise ValueError("Missing publication proof")
        if verify_files:
            raw = read_verified(s)
            source_soups[s["artifact_id"]] = BeautifulSoup(raw, "lxml")
            source_texts[s["artifact_id"]] = compact(html_text(raw))
            proof_raw = [read_verified(proof) for proof in s["proofs"]]
            verify_embedding(proof_raw[0], raw, s["source_url"].rsplit("/", 1)[1])
            filed = re.search(rb"FILED AS OF DATE:\s*(\d{8})", proof_raw[0]).group(1).decode()
            if s["version_available_at"] != f"{filed[:4]}-{filed[4:6]}-{filed[6:]}":
                raise ValueError("Availability date differs from archived header")
            primary_text = compact(html_text(proof_raw[1]))
            if compact(s["proofs"][1]["text"]) not in primary_text:
                raise ValueError("Publication proof excerpt mismatch")
            if s["published_date"]:
                from datetime import datetime
                issued = issuance_statement(primary_text, s["period_id"])
                if not issued or datetime.strptime(issued[1], "%B %d, %Y").date().isoformat() != s["published_date"]:
                    raise ValueError("Publication date differs from the official issuance statement")
    all_metrics = package["metric_versions"]
    if len({m["metric_id"] for m in all_metrics}) != len(all_metrics):
        raise ValueError("Duplicate metric version")
    for m in all_metrics:
        if m["artifact_id"] not in sources or m["excerpt_id"] not in excerpts:
            raise ValueError("Unresolved evidence reference")
        if m["period_id"] > package["period_id"] or not math.isfinite(m["value"]):
            raise ValueError("Invalid metric period or value")
        if not math.isclose(m["value_raw"] * m["scale_multiplier"], m["value"], rel_tol=1e-12, abs_tol=1e-10):
            raise ValueError("Reported scale disagrees with normalized value")
        if m["available_date"] != sources[m["artifact_id"]]["version_available_at"]:
            raise ValueError("Metric availability differs from its source")
    ids = {m["metric_id"] for m in all_metrics}
    if any(m["metric_id"] not in ids for m in package["metrics"]):
        raise ValueError("Selected metric missing original version")
    expected, expected_conflicts = select_versions(all_metrics)
    if package["metrics"] != expected or package["conflicts"] != expected_conflicts:
        raise ValueError("Selected metric differs from eligible version policy")
    for e in excerpts.values():
        if e["excerpt_id"] != "exc_" + digest({k: v for k, v in e.items() if k != "excerpt_id"}):
            raise ValueError("Excerpt fingerprint mismatch")
        if e["artifact_id"] not in sources or e["artifact_sha256"] != sources[e["artifact_id"]]["artifact_sha256"]:
            raise ValueError("Excerpt source mismatch")
        if verify_files:
            soup = source_soups[e["artifact_id"]]
            row_locator = re.fullmatch(r"table\[(\d+)\]/tr\[(\d+)\]", e["locator"])
            paragraph_locator = re.fullmatch(r"p\[(\d+)\]", e["locator"])
            if row_locator:
                table = soup.find_all("table")[int(row_locator[1]) - 1]
                rows = table.find_all("tr", recursive=False) or table.select(":scope > tbody > tr")
                row = rows[int(row_locator[2]) - 1]
                expected_text = " | ".join(compact(c.get_text(" ", strip=True)) for c in row.find_all(["td", "th"], recursive=False))
            elif paragraph_locator:
                expected_text = compact(soup.find_all("p")[int(paragraph_locator[1]) - 1].get_text(" ", strip=True))
            elif e["locator"] == "complete earnings release / text extraction":
                expected_text = source_texts[e["artifact_id"]]
                start = expected_text.find("Aeroméxico Reports")
                expected_text = expected_text[start:] if start >= 0 else expected_text
            else:
                raise ValueError("Unknown excerpt locator")
            if e["text"] != expected_text:
                raise ValueError("Excerpt does not match its source locator")
    current = {m["metric_key"] for m in package["metrics"] if m["period_id"] == package["period_id"]}
    if package["readiness"] != "blocked" and (not package["cutoff_date"] or not CORE <= current):
        raise ValueError("Readiness contradicts essential evidence")
    return {"status": "passed", "package_id": package["package_id"], "metrics": len(package["metrics"]),
            "versions": len(all_metrics), "excerpts": len(excerpts), "sources": len(sources)}


def preserve(package: dict, root: Path = STORE) -> Path:
    validate(package)
    root.mkdir(parents=True, exist_ok=True)
    path = root / (package["package_id"] + ".json")
    data = canonical(package)
    fd, temporary_name = tempfile.mkstemp(prefix=".package-", suffix=".tmp", dir=root)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # Atomic, no replacement: concurrent preparations cannot overwrite a version.
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != data:
                raise ValueError("Immutable package already exists with different content")
    finally:
        temporary.unlink(missing_ok=True)
    return path


def run(period: str) -> dict:
    result = build(period)
    path = preserve(result["package"])
    REVIEW.mkdir(parents=True, exist_ok=True)
    (REVIEW / f"{period}_review.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    receipt = validate(result["package"]) | {"readiness": result["package"]["readiness"], "path": str(path.relative_to(PATHS.root))}
    (REVIEW / f"{period}_validation.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["prepare", "validate"])
    parser.add_argument("target", help="Quarter for prepare; frozen package path for validate")
    args = parser.parse_args()
    print(json.dumps(run(args.target) if args.operation == "prepare" else
                     validate(json.loads(Path(args.target).read_bytes())), indent=2))
