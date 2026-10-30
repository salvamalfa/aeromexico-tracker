"""Prove an AM source arrival adds no material change to its published 3Q26.

Read-only, edition-specific bridge. Replays the candidate and the historical
approval/producer; never approves the arriving source or rewrites a thesis.
"""

from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

from src.source_updates import readiness
from src.source_updates.catalog import ROOT
from src.source_updates.closed_editions import accepted
from src.source_updates.financials import PATTERNS, value
from src.source_updates.financials_html import LABELS, document, text
from src.source_updates.retained import originals

CONTACT = (
    "CONTACT:InvestorRelationsaminvestorrelations@aeromexico.com"
    "CorporateCommunicationsamcomunicacioncorporativa@aeromexico.com"
)
TITLE = "AeroméxicoReportsUnauditedThirdQuarter2026Results"
# Source-native units/definitions. No ASM -> ASK renaming or dollar rounding.
SUMMARY = {key: (unit, definition) for key, _, unit, definition in PATTERNS}
OLD_LABELS = {
    "adjusted_ebitdar": "Adjusted EBITDAR (1) (USD millions)",
    "ebitdar_margin": "Adjusted EBITDAR margin (1) (% of revenue)",
    "operating_margin": "Operating income margin (% of revenue)",
    "asm": "Total ASMs (millions)",
    "rpm": "Total RPMs (millions)",
    "load_factor": "Load factor on scheduled flights (%)",
    "passengers": "Passengers ('000)",
    "fuel_liters": "Total liters of fuel ('000)",
    "casm_ex_fuel": "Total cost excluding fuel / ASM (USD cents)",
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path):
    path = Path(path)
    if not path.is_file() or any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("AM proof inputs must be physical regular files without symlinks")
    return json.loads(path.read_bytes())


def compact_layout(value):
    """Ignore whitespace only; preserve case, decimal points, signs and symbols."""
    return re.sub(r"\s+", "", value)


def financial_body(old_body, new_body):
    """Remove only the enumerated framing differences of the two known formats.

    Every remaining character, including ALL tables, narratives and footnotes,
    must match. This is deliberately fail closed for any new document layout.
    """
    old, new = compact_layout(old_body), compact_layout(new_body)
    prefix = "Document" + CONTACT + TITLE
    if not old.endswith(CONTACT) or not new.startswith(prefix) or not new.endswith("13"):
        raise ValueError("AM distribution-format framing changed")
    old, new = old[: -len(CONTACT)], new[len(prefix) : -2]
    for original, marker in [
        (old, "MEXICOCITY,Oct.19,2026(GLOBENEWSWIRE)--"),
        (new, "MexicoCity,Mexico,October19,2026-"),
    ]:
        if original.count(marker) != 1:
            raise ValueError("AM printed report day or distribution dateline changed")
    old = old.replace("MEXICOCITY,Oct.19,2026(GLOBENEWSWIRE)--", "", 1)
    new = new.replace("MexicoCity,Mexico,October19,2026-", "", 1).replace("•", "")
    if new.count("3Q26RESULTS") != 12:
        raise ValueError("AM financial page-footer inventory changed")
    for number in range(1, 13):
        marker = ("" if number == 1 else str(number)) + "3Q26RESULTS"
        if marker not in new:
            raise ValueError("AM financial page-footer sequence changed")
        new = new.replace(marker, "", 1)
    for prefix, number in [
        ("Footnotes", 1),
        ("IFRSmeasure.", 2),
        ("revolvingcreditfacility.", 3),
        ("totalpassengerrevenue.", 4),
    ]:
        marker = f"{prefix}({number})"
        if new.count(marker) != 1:
            raise ValueError("AM footnote marker changed")
        new = new.replace(marker, prefix, 1)
    if old != new:
        raise ValueError("AM source has changed financial text, numbers, scope or interpretation")
    return {"characters_compared": len(old), "financial_body_sha256": sha(old.encode())}


def compare_twenty(frame, old_soup):
    """Compare all twenty native observations to the approved original tables."""
    if len(frame) != 20 or set(frame.metric_key) != set(LABELS) or frame.metric_key.duplicated().any():
        raise ValueError("AM candidate must preserve exactly twenty unique metrics")
    tables = old_soup.find_all("table")
    if len(tables) != 14:
        raise ValueError("Published original table inventory changed")
    compared = []
    for row in frame.itertuples(index=False):
        summary = row.metric_key in SUMMARY
        unit, definition = SUMMARY[row.metric_key] if summary else ("USD millions", "reported")
        label = OLD_LABELS[row.metric_key] if summary else LABELS[row.metric_key]
        table = tables[
            1
            if summary
            and row.metric_key
            in {"adjusted_ebitdar", "ebitdar_margin", "operating_margin", "asm", "passengers", "casm_ex_fuel"}
            else 9
            if summary
            else 5
        ]
        rows = [[text(c) for c in tr.find_all(["td", "th"], recursive=False)] for tr in table.find_all("tr")]
        matches = [cells for cells in rows if cells and cells[0] == label]
        if len(matches) != 1 or len(matches[0]) != 7:
            raise ValueError("Published AM metric row is missing or ambiguous")
        old_value = value(matches[0][1])
        if (
            row.period_id != "2026Q3"
            or row.period_type != "quarter"
            or row.carrier_key != "AEROMEXICO"
            or row.unit != unit
            or row.definition != definition
            or not row.not_ytd
            or not row.is_unaudited
            or row.normalized_unit_conversion_performed
            or Decimal(str(row.value)) != Decimal(str(old_value))
        ):
            raise ValueError(f"AM metric value, units or scope changed: {row.metric_key}")
        compared.append(
            {"metric_key": row.metric_key, "value": row.value, "unit": unit, "definition": definition}
        )
    return sorted(compared, key=lambda item: item["metric_key"])


def verify(item: dict, expected_binding: dict, record_path: Path, site: Path | None = None) -> dict:
    """Return deterministic physical proof for the two no-change job results."""
    from src.publish.financial_scope import anchor
    from src.publish.financial_sources import approved_projection

    if (item.get("product"), item.get("period"), item.get("adapter")) != (
        "am_financials",
        "2026Q3",
        "retained",
    ):
        raise ValueError("AM equivalence bridge supports the reviewed financial edition only")
    cutoff = item["candidate_as_of"]
    recipe = {"version": 1, "as_of": cutoff, "required_items": [item["id"]], "items": [item]}
    selected = readiness.preflight(recipe, ROOT / "tmp/source-updates/am-equivalence-check")[0]
    checked = readiness.check_task(selected, cutoff, cutoff)
    if not accepted(selected, checked):
        raise ValueError("AM source candidate or its availability is not independently verified")
    binding = {key: item[key] for key in ("product", "period", "receipt_id", "candidate_as_of")}
    binding["output_sha256"] = checked["output_sha256"]
    if binding != expected_binding:
        raise ValueError("AM equivalence targets another source version")
    spec = anchor(ROOT)
    record_path = Path(record_path)
    record = load(record_path)
    record_hash = sha(record_path.read_bytes())
    if record["version"] != spec["analysis_entry"]["version"]:
        raise ValueError("AM proof targets a different published analysis")
    # Full original sources, exact current approval and old producer are replayed.
    package_path = ROOT / "analysis_runs/evidence" / (spec["package_id"] + ".json")
    package = load(package_path)
    package_hash = sha(package_path.read_bytes())
    projected = approved_projection([record_path], spec, ROOT / "analysis_runs/lifecycle", ROOT)
    release = next(source for source in package["sources"] if source["artifact_id"] == "release")
    release_path = ROOT / "data/bronze" / release["source_file"]
    release_raw = release_path.read_bytes()
    if sha(release_raw) != release["artifact_sha256"]:
        raise ValueError("Published original release changed during comparison")
    source_inputs, _ = originals(Path(item["workspace"]), "am_financials", item["receipt_id"], cutoff)
    if set(source_inputs) != {"html"}:
        raise ValueError("AM equivalence requires the reviewed official financial HTML")
    body, metadata = source_inputs["html"]
    candidate = document(body, metadata)
    soup = BeautifulSoup(release_raw, "lxml")
    old_bodies = soup.select("div.article-body")
    if len(old_bodies) != 1:
        raise ValueError("Published primary-release body is ambiguous")
    body_proof = financial_body(text(old_bodies[0]), text(candidate))
    frame = pd.read_parquet(
        Path(item["workspace"]) / "data/gold/fact_am_retained_quarterly_source_metrics.parquet"
    )
    compared = compare_twenty(frame, soup)
    site = Path(site or ROOT / "site")
    publication = load(site / "publication_manifest.json")
    baseline_hashes = {
        name: sha((site / name).read_bytes())
        for name in ("publication_manifest.json", "data/v1/analysis/2026Q3.json", "data/v1/executive.json")
    }
    if spec["analysis_entry"] not in publication["analysis_manifest"]:
        raise ValueError("Baseline does not contain the exact approved AM reading")
    relevant = ["data/v1/analysis/2026Q3.json", "data/v1/executive.json"]
    for name in relevant:
        raw = (site / name).read_bytes()
        entry = {"path": name, "sha256": sha(raw), "bytes": len(raw)}
        if entry not in publication["files"]:
            raise ValueError("AM baseline payload differs from publication manifest")
    if sha((site / relevant[0]).read_bytes()) != spec["analysis_sha256"]:
        raise ValueError("AM served-baseline reading differs from its approved cohort")
    executive = load(site / relevant[1])
    if (
        executive["entities"]["AEROMEXICO"] != projected["entities"]["AEROMEXICO"]
        or executive["views"]["2026Q3"] != projected["views"]["2026Q3"]
        or [r for r in executive["records"] if r["period_id"] == "2026Q3"]
        != [r for r in projected["records"] if r["period_id"] == "2026Q3"]
    ):
        raise ValueError("Published AM financial charts differ from their approved producer")
    from src.analysis_agent.lifecycle import state

    current = state(record, ROOT / "analysis_runs/lifecycle")
    if (
        current["state"] not in {"approved", "published"}
        or current["approval"]["event_hash"] != spec["analysis_entry"]["approval_event"]
    ):
        raise ValueError("AM historical approval changed during equivalence verification")
    if sha(record_path.read_bytes()) != record_hash or sha(package_path.read_bytes()) != package_hash:
        raise ValueError("AM historical record/package changed during equivalence verification")
    for name, expected in checked["output_sha256"].items():
        if sha((Path(item["workspace"]) / "data" / (name + ".parquet")).read_bytes()) != expected:
            raise ValueError("AM candidate output changed during equivalence verification")
    if any(sha((site / name).read_bytes()) != expected for name, expected in baseline_hashes.items()):
        raise ValueError("AM baseline changed during equivalence verification")
    return {
        "schema_version": "published_am_equivalence_v1",
        "analysis_status": "no_material_analysis_change",
        "dashboard_status": "no_visual_change",
        "entity": "AEROMEXICO",
        "period": "2026Q3",
        "source_binding": binding,
        "existing_analysis_entry": spec["analysis_entry"],
        "existing_record_sha256": record_hash,
        "existing_package_sha256": package_hash,
        "baseline_manifest_sha256": sha((site / "publication_manifest.json").read_bytes()),
        "baseline_executive_sha256": sha((site / relevant[1]).read_bytes()),
        "producer_commit": spec["producer_commit"],
        "compared_native_metrics": compared,
        **body_proof,
        "scope": "AM 2026Q3 financial arrival only; other sources/products are independent",
        "new_approval": False,
        "publication_performed": False,
        "live_deployment_checked": False,
    }
