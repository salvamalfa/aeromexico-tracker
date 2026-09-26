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

Citations (the superscript source links the published page overlays on top
of this text) are out of scope: they come from ``verified_inputs()``
(calculations, excerpts, source URLs), not from ``consumer_payload``, and
this exporter never reads that private evidence. See ``web/README.md`` for
the resulting, accepted parity gap.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from src.analysis_agent import lifecycle as flow
from src.config import PATHS
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.schemas import ANALYSIS_SCHEMA
from src.web_export.writer import write_json

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


def _drop_private_sections(authorized: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    private_keys = set(record["draft"].get("reader_private_section_keys", []))
    private_titles = {
        section["title"] for section in record["draft"]["sections"] if section["key"] in private_keys
    }
    authorized["sections"] = [s for s in authorized["sections"] if s["title"] not in private_titles]
    return authorized


def export_period(period_id: str, version: str, *, root: Path = flow.ROOT) -> dict[str, Any]:
    """Load one record and return exactly what consumer_payload() authorizes."""

    record = _load_record(period_id, version)
    try:
        authorized = flow.consumer_payload(record, root)
    except ValueError as error:
        raise MissingAnalysisInput(
            f"{period_id}/{version} has no current human approval under {root}: {error}"
        ) from error
    return _drop_private_sections(authorized, record)


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
