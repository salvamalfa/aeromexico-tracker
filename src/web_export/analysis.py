"""Export the reading tab's approved analysis, one file per period.

Read-only use of the existing approval flow: for every ``{period_id,
version}`` listed in the *published* page's ``#analysis-manifest`` (the
receipt ``src.analysis_agent.stage18.consumer_html`` already writes), this
loads the matching ``analysis_runs/drafts/<period_id>/<version>.json``
record and calls ``src.analysis_agent.lifecycle.consumer_payload(record)`` —
the same fail-closed handoff ``stage18`` uses before anything reaches an
HTML page — and exports exactly what it authorizes, plus a filter that
drops any section the draft itself marks reader-private (the same sections
``analysis_agent.reader_ui.refine`` strips from the published dialog).

Never writes to the ledger, never approves or revokes anything, never
touches ``static/aeromexico_tracker.html``. See ``src/web_export/README.md``
and ``docs/arquitectura/auditoria-arquitectura-20260926.md`` Fase 3.

Citations: each claim in ``consumer_payload``'s ``claims`` list also gets a
``citations`` array — a port of ``src.analysis_agent.reader_ui.cite()``'s
selection logic (see ``_claim_citations``/``_citations_by_claim`` below),
run against ``verified_inputs()``'s ``package``/``calculations`` under the
same fail-closed call ``stage18`` makes, but exporting *only* the fields
``cite()`` itself already puts on the public page: the public source URL,
the visible tooltip text, and the exact substring of the already-rendered
claim text to wrap. No excerpt/source/calculation object, no lineage, no
provider identifier ever leaves this module — see ``contracts/web/
analysis.schema.json`` (``additionalProperties: false`` on ``citation``)
and ``contracts/web/privacy.yaml``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from jsonschema import Draft202012Validator

from src.analysis_agent import lifecycle as flow
from src.analysis_agent.analyst import formatted, lineage
from src.config import PATHS
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.schemas import ANALYSIS_SCHEMA
from src.web_export.writer import write_json

# Same allow-list src.analysis_agent.reader_ui.cite() checks before it will
# ever put a source URL on the published page. Duplicated here (rather than
# imported) because reader_ui pulls in the flights HTML generator; keep the
# two lists in sync — tests/test_web_export.py checks that they match.
ALLOWED_CITATION_HOSTS = ("www.sec.gov", "sec.gov", "ir.aeromexico.com")

DEFAULT_PUBLISHED_HTML = PATHS.root / "static" / "aeromexico_tracker.html"
DRAFTS_ROOT = PATHS.root / "analysis_runs" / "drafts"

_MANIFEST_RE = re.compile(
    r'<script id="analysis-manifest" type="application/json">(.*?)</script>', re.DOTALL
)


class MissingAnalysisInput(RuntimeError):
    """A record or the approval ledger this exporter needs is not present locally."""


def read_manifest(published_html: Path = DEFAULT_PUBLISHED_HTML) -> list[dict[str, str]]:
    """Return the {period_id, version, ...} entries the published page lists."""

    if not published_html.is_file():
        raise MissingAnalysisInput(f"{published_html} is not present; cannot read its analysis manifest")
    match = _MANIFEST_RE.search(published_html.read_text(encoding="utf-8"))
    if not match:
        raise MissingAnalysisInput(f"{published_html} has no #analysis-manifest script tag")
    return json.loads(match.group(1))


def _load_record(period_id: str, version: str) -> dict[str, Any]:
    path = DRAFTS_ROOT / period_id / f"{version}.json"
    if not path.is_file():
        raise MissingAnalysisInput(
            f"analysis record for {period_id}/{version} is not present at {path}. "
            "analysis_runs/ is local, non-versioned expediente data; restore it or "
            "re-run the Analysis Agent locally, or pass --allow-missing-analysis for a dev build."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _claim_citations(
    claim: dict[str, Any],
    package: dict[str, Any],
    calculations: dict[str, Any],
    numbers: dict[str, int],
) -> list[dict[str, Any]]:
    """Port of src.analysis_agent.reader_ui.cite()'s selection and href/title
    construction for one claim, minus the DOM text-splicing (the front-end
    does that itself against the already-rendered claim text — see
    web/src/views/executive/narrative.ts). ``numbers`` is the href->label
    map, shared and mutated across every claim in one record so citation
    numbering matches the published page (first-seen href wins the next
    number, in the same summary-then-sections document order — see
    ``_citations_by_claim``)."""

    nodes = {n["calculation_id"]: n for n in calculations["nodes"]}
    excerpts = {e["excerpt_id"]: e for e in package["excerpts"]}
    sources = {s["artifact_id"]: s for s in package["sources"]}
    citations: list[dict[str, Any]] = []
    for binding in claim.get("bindings", {}).values():
        node = nodes[binding["calculation_id"]]
        if node["period_id"] != package["period_id"] or binding.get("presentation") == "period_label":
            continue
        if not (node["formula"].startswith("Reported normalized") or node["key"] == "ask"):
            continue
        leaves = lineage(node["calculation_id"], package, calculations)
        if len(leaves) != 1:
            continue
        metric = leaves[0]
        excerpt = excerpts[metric["excerpt_id"]]
        source = sources[metric["artifact_id"]]
        url = source["source_url"]
        if urlparse(url).scheme != "https" or urlparse(url).hostname not in ALLOWED_CITATION_HOSTS:
            continue
        cells = [c.strip() for c in excerpt["text"].split("|") if c.strip()]
        # Range directive spans table cells, whose separators are parser-only.
        fragment = quote(cells[0], safe="").replace("-", "%2D")
        if len(cells) > 1:
            fragment += "," + quote(cells[1], safe="").replace("-", "%2D")
        href = url.split("#")[0] + "#:~:text=" + fragment
        label = str(numbers.setdefault(href, len(numbers) + 1))
        value = formatted(node, business=True)
        title = (
            "Reporte original · "
            + cells[0]
            + (": " + cells[1] if len(cells) > 1 else "")
            + (
                " millones de asientos-milla; convertido a asientos-kilómetro."
                if node["key"] == "ask"
                else ""
            )
        )
        citations.append({"label": label, "href": href, "title": title, "value": value})
    return citations


def _citations_by_claim(
    record: dict[str, Any], package: dict[str, Any], calculations: dict[str, Any]
) -> dict[str, list[dict[str, Any]]]:
    """claim_id -> citations, numbered in the same document order
    src.analysis_agent.reader_ui.refine walks: the summary list first
    (``summary_claim_ids``), then every non reader-private section's
    paragraphs in order (``sections[*].claim_ids``) — thesis and context
    asides are never cited on the published page either."""

    d = record["draft"]
    claims = {c["claim_id"]: c for c in d["claims"]}
    private_keys = set(d.get("reader_private_section_keys", []))
    ordered_claim_ids = list(d["summary_claim_ids"])
    for section in d["sections"]:
        if section["key"] in private_keys:
            continue
        ordered_claim_ids.extend(section["claim_ids"])
    numbers: dict[str, int] = {}
    result: dict[str, list[dict[str, Any]]] = {}
    for claim_id in ordered_claim_ids:
        if claim_id in result:
            continue
        result[claim_id] = _claim_citations(claims[claim_id], package, calculations, numbers)
    return result


def _drop_private_sections(authorized: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Drop reader-private sections and attach each kept section's
    claim_ids (needed by the front-end to look up citations per
    paragraph, see _citations_by_claim). consumer_payload builds one
    authorized section per record["draft"]["sections"] entry, in the same
    order, so zipping by index (rather than matching titles) is correct
    even when two sections share a title."""

    private_keys = set(record["draft"].get("reader_private_section_keys", []))
    draft_sections = record["draft"]["sections"]
    authorized["sections"] = [
        {"title": rendered["title"], "paragraphs": rendered["paragraphs"], "claim_ids": draft["claim_ids"]}
        for draft, rendered in zip(draft_sections, authorized["sections"])
        if draft["key"] not in private_keys
    ]
    return authorized


def export_period(period_id: str, version: str, *, root: Path = flow.ROOT) -> dict[str, Any]:
    """Load one record and return exactly what consumer_payload() authorizes."""

    record = _load_record(period_id, version)
    try:
        authorized = flow.consumer_payload(record, root)
        package, calculations, _ = flow.verified_inputs(record)
    except ValueError as error:
        raise MissingAnalysisInput(
            f"{period_id}/{version} has no current human approval under {root}: {error}"
        ) from error
    authorized = _drop_private_sections(authorized, record)
    citations = _citations_by_claim(record, package, calculations)
    for claim in authorized["claims"]:
        claim["citations"] = citations.get(claim["claim_id"], [])
    return authorized


def export_analysis(
    out_dir: Path,
    *,
    published_html: Path = DEFAULT_PUBLISHED_HTML,
    root: Path = flow.ROOT,
    allow_missing: bool = False,
) -> list[Path]:
    """Write out_dir/analysis/<period_id>.json for every manifest entry.

    With ``allow_missing`` (dev only), a period whose record or approval is
    not present locally is skipped with a stderr note instead of failing
    the whole export — a clean public clone has neither.
    """

    manifest = read_manifest(published_html)
    validator = Draft202012Validator(ANALYSIS_SCHEMA)
    rules = load_privacy_rules()
    written: list[Path] = []
    for entry in manifest:
        period_id, version = entry["period_id"], entry["version"]
        try:
            payload = export_period(period_id, version, root=root)
        except MissingAnalysisInput as error:
            if not allow_missing:
                raise
            print(f"web_export.analysis: skipping {period_id} ({error})", file=sys.stderr)
            continue
        errors = [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(payload)]
        if errors:
            raise ValueError(f"analysis/{period_id}.json does not match its schema: {errors[:5]}")
        check_privacy(payload, rules)
        written.append(write_json(out_dir / "analysis" / f"{period_id}.json", payload))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=PATHS.root / "web" / "public" / "data" / "v1")
    parser.add_argument("--published-html", type=Path, default=DEFAULT_PUBLISHED_HTML)
    parser.add_argument(
        "--allow-missing-analysis",
        action="store_true",
        dest="allow_missing",
        help="Dev only: skip a period whose record/approval is not present locally instead of failing.",
    )
    args = parser.parse_args(argv)
    try:
        written = export_analysis(
            args.out,
            published_html=args.published_html,
            allow_missing=args.allow_missing,
        )
    except MissingAnalysisInput as error:
        print(f"web_export.analysis: {error}", file=sys.stderr)
        return 1
    for path in sorted(written):
        print(f"{path.relative_to(args.out)}\t{path.stat().st_size:,} bytes")
    print(f"{len(written)} file(s) written under {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
