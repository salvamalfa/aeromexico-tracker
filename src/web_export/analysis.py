"""Export approved analysis, one file per entity and period.

Read-only use of the existing approval flow: for every ``{period_id,
version}`` the local ledger currently has approved or published (see
``discover_approved_manifest``), this loads the matching ``analysis_runs/drafts/
<period_id>/<version>.json`` legacy record or
``<entity_key>/<period_id>/<version>.json`` entity record and calls
``src.analysis_agent.lifecycle.consumer_payload(record)`` — the
fail-closed handoff that gates every publication — and exports exactly what
it authorizes, plus a filter that drops any section the draft itself marks
reader-private (``web/`` applies the same filter client-side).

Never writes to the ledger, never approves or revokes anything. See
``src/web_export/README.md``.

Citations: each claim in ``consumer_payload``'s ``claims`` list also gets a
``citations`` array — built by ``_claim_citations``/``_citations_by_claim`` below,
run against ``verified_inputs()``'s
``package``/``calculations`` under the same fail-closed call
``consumer_payload`` makes, but exporting *only* the public fields: the public source URL, the visible
tooltip text, and the exact substring of the already-rendered claim text to
wrap. No excerpt/source/calculation object, no lineage, no provider
identifier ever leaves this module — see ``contracts/web/
analysis.schema.json`` (``additionalProperties: false`` on ``citation``)
and ``contracts/web/privacy.yaml``.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

from jsonschema import Draft202012Validator, FormatChecker

from src.analysis_agent import lifecycle as flow
from src.analysis_agent.analyst import formatted, lineage
from src.config import PATHS
from src.publish.manifest import analysis_identity, analysis_relative_path, analysis_sort_key
from src.web_export.privacy import check_privacy, load_privacy_rules
from src.web_export.schemas import ANALYSIS_SCHEMA
from src.web_export.writer import write_json

# The only hosts a citation's public source URL may point to (see
# contracts/web/analysis.schema.json's citation.href pattern, which must
# stay in sync with this list).
ALLOWED_CITATION_HOSTS = ("www.sec.gov", "sec.gov", "ir.aeromexico.com", "cdn.investorcloud.net")

DRAFTS_ROOT = PATHS.root / "analysis_runs" / "drafts"


class MissingAnalysisInput(RuntimeError):
    """A record or the approval ledger this exporter needs is not present locally."""


def _drafts_root_for(root: Path) -> Path:
    """The drafts directory that belongs to a given ledger ``root``.

    ``DRAFTS_ROOT`` (``analysis_runs/drafts``) and ``flow.ROOT``
    (``analysis_runs/lifecycle``) are siblings under ``analysis_runs``; an
    alternate ``root`` (e.g. an isolated ledger under ``tmp_path`` in tests)
    keeps that same relationship, so its drafts live at ``root.parent /
    "drafts"``. For the real ``flow.ROOT`` this resolves to ``DRAFTS_ROOT``
    unchanged.
    """

    return Path(root).parent / "drafts"


def discover_approved_manifest(root: Path = flow.ROOT) -> list[dict[str, str]]:
    """Return currently approved entity/period/version identities.

    Legacy entries omit entity_key and retain the original Aeroméxico path.

    Reads the same ledger
    ``lifecycle.consumer_payload`` itself checks instead: a draft that is
    not exactly, currently approved is silently skipped here, exactly as it
    would be refused there -- no fabricated approval, and a clean checkout
    with no local ``analysis_runs/`` simply yields an empty manifest.

    Raises ``ValueError`` if more than one version of the same
    entity/period is currently approved/published -- ambiguous, since
    ``export_analysis`` writes one file per entity and quarter.
    """

    drafts_root = _drafts_root_for(root)
    manifest: list[dict[str, str]] = []
    if not drafts_root.is_dir():
        return manifest
    for version_path in sorted(drafts_root.rglob("*.json")):
        record = json.loads(version_path.read_text(encoding="utf-8"))
        identity = _record_manifest_entry(record)
        expected = _record_path(identity, root)
        if version_path != expected:
            raise ValueError(f"Analysis record path does not match its entity/period/version: {version_path}")
        try:
            current = flow.state(record, root)
        except ValueError:
            continue
        if current["state"] in ("approved", "published"):
            manifest.append(identity)
    by_period: dict[tuple[str, str], list[str]] = {}
    for entry in manifest:
        by_period.setdefault(analysis_identity(entry), []).append(entry["version"])
    for (entity, period_id), versions in sorted(by_period.items()):
        if len(versions) > 1:
            versions_str = ", ".join(sorted(versions))
            raise ValueError(
                f"Multiple approved versions for period {period_id} (entity {entity}): {versions_str} — "
                "revoke one or select explicitly"
            )
    return sorted(manifest, key=analysis_sort_key)


def _record_manifest_entry(record: dict[str, Any]) -> dict[str, str]:
    draft = record["draft"]
    entry = {"period_id": draft["period_id"], "version": record["version"]}
    if "entity_key" in draft:
        entry["entity_key"] = draft["entity_key"]
    if draft.get("schema_version") == "entity_analyst_v1" and "entity_key" not in draft:
        raise ValueError("Entity analysis is missing its entity identity")
    analysis_identity(entry)
    if (
        not isinstance(entry["version"], str)
        or not entry["version"]
        or Path(entry["version"]).name != entry["version"]
        or "\\" in entry["version"]
    ):
        raise ValueError("Invalid analysis version")
    if "entity_key" in record and record["entity_key"] != entry.get("entity_key", "AEROMEXICO"):
        raise ValueError("Record and draft entity identities differ")
    return entry


def _record_path(entry: dict[str, Any], root: Path) -> Path:
    entity, period = analysis_identity(entry)
    base = _drafts_root_for(root)
    if "entity_key" in entry:
        base = base / entity
    return base / period / f"{entry['version']}.json"


def _load_record(
    period_id: str, version: str, root: Path = flow.ROOT, *, entity_key: str | None = None
) -> dict[str, Any]:
    entry = {"period_id": period_id, "version": version}
    if entity_key is not None:
        entry["entity_key"] = entity_key
    # Reject traversal before constructing a private expediente path.
    _record_manifest_entry({"draft": entry, "version": version})
    path = _record_path(entry, root)
    if not path.is_file():
        raise MissingAnalysisInput(
            f"analysis record for {period_id}/{version} is not present at {path}. "
            "analysis_runs/ is local, non-versioned expediente data; restore it or "
            "re-run the Analysis Agent locally, or pass --allow-missing-analysis for a dev build."
        )
    record = json.loads(path.read_text(encoding="utf-8"))
    if _record_manifest_entry(record) != entry:
        raise ValueError("Loaded analysis does not match the requested entity/period/version")
    return record


def validate_analysis_manifest(value: Any) -> list[dict[str, str]]:
    """Validate an exact selection; it never establishes human approval."""
    if isinstance(value, dict):
        schema = json.loads(
            (PATHS.root / "contracts/web/publication_manifest.schema.json").read_text(encoding="utf-8")
        )
        errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(value))
        if errors:
            raise ValueError(f"Invalid analysis publication manifest: {errors[0].message}")
        value = value["analysis_manifest"]
    if not isinstance(value, list):
        raise ValueError("Analysis manifest must be a publication manifest or an identity list")
    fields = {
        "entity_key", "period_id", "version", "content_hash", "evidence_fingerprint", "approval_event", "audit_hash",
    }
    selected = []
    seen = set()
    for entry in value:
        if (
            not isinstance(entry, dict)
            or not {"period_id", "version"} <= entry.keys()
            or not entry.keys() <= fields
            or any(not isinstance(v, str) or not v.strip() for v in entry.values())
        ):
            raise ValueError("Invalid analysis manifest entry: exact entity/period/version identity required")
        _record_manifest_entry({"draft": entry, "version": entry["version"]})
        identity = analysis_identity(entry)
        if identity in seen:
            raise ValueError(f"Multiple selected versions for entity/period {identity}")
        seen.add(identity)
        selected.append(dict(entry))
    return sorted(selected, key=analysis_sort_key)


def load_analysis_manifest(path: Path) -> list[dict[str, str]]:
    """Load the explicit CLI selector before generators or output mutations."""
    return validate_analysis_manifest(json.loads(path.read_text(encoding="utf-8")))


def _claim_citations(
    claim: dict[str, Any],
    package: dict[str, Any],
    calculations: dict[str, Any],
    numbers: dict[str, int],
    rendered_text: str | None = None,
) -> list[dict[str, Any]]:
    """Citation selection and href/title construction for one claim, minus
    the DOM text-splicing (the front-end
    does that itself against the already-rendered claim text — see
    web/src/views/executive/narrative.ts). ``numbers`` is the href->label
    map, shared and mutated across every claim in one record so citation
    numbering matches the published page (first-seen href wins the next
    number, in the same summary-then-sections document order — see
    ``_citations_by_claim``)."""

    if package.get("schema_version") == "entity_evidence_v1":
        return _entity_claim_citations(claim, package, calculations, numbers, rendered_text)
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


def _entity_claim_citations(claim, package, calculations, numbers, rendered_text=None):
    """Public links for both observed/derived values and qualitative entity claims.

    Reuses the verified lineage without exporting it. A multi-carrier ratio may
    link to each member's original, while a qualitative sentence links its
    literal rendered lead. Tooltips contain only a public period label.
    """
    nodes = {node["calculation_id"]: node for node in calculations["nodes"]}
    excerpts = {excerpt["excerpt_id"]: excerpt for excerpt in package["excerpts"]}
    sources = {source["artifact_id"]: source for source in package["sources"]}
    if rendered_text is None:
        rendered_text = claim.get("text", claim.get("text_template", ""))
        for alias, binding in claim.get("bindings", {}).items():
            rendered_text = rendered_text.replace(
                "{{" + alias + "}}", nodes[binding["calculation_id"]]["formatted_value"]
            )
    selections = []
    for binding in claim.get("bindings", {}).values():
        if binding.get("presentation") == "period_label":
            continue
        node = nodes[binding["calculation_id"]]
        value = node["formatted_value"]
        if not value or value not in rendered_text:
            continue
        for metric in lineage(node["calculation_id"], package, calculations):
            selections.append((metric["excerpt_id"], value))
    if not selections:
        lead = claim.get("lead")
        value = lead if lead and lead in rendered_text else rendered_text.split(". ", 1)[0]
        if value:
            selections.extend((eid, value) for eid in claim.get("evidence_ids", []))
    # Company explanations must remain linked even when the same claim also
    # has a quantitative binding whose lineage cites only operating tables.
    for span in claim.get("support_spans", []):
        value = claim.get("lead") or rendered_text.split(". ", 1)[0]
        if value and value in rendered_text:
            selections.append((span["excerpt_id"], value))
    # A displayed value can depend on many rows of the same report. Group
    # those rows before constructing anchors: one marker per value/document,
    # while retaining every primary document in the verified lineage.
    grouped = {}
    for excerpt_id, value in selections:
        excerpt = excerpts[excerpt_id]
        source = sources.get(excerpt.get("artifact_id"), {})
        url = excerpt.get("source_url") or source.get("source_url", "")
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_CITATION_HOSTS
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            continue
        document_url = url.split("#")[0]
        document_id = excerpt.get("artifact_id") or document_url
        group = grouped.setdefault((document_id, document_url, value), {})
        group.setdefault(excerpt_id, excerpt)
    result = []
    for (_, document_url, value), group in grouped.items():
        href = document_url
        excerpt = next(iter(group.values()))
        literal = excerpt.get("text", "").strip()
        if len(group) == 1 and urlparse(document_url).hostname in ("www.sec.gov", "sec.gov") and literal:
            # Short literal anchors only; the private excerpt object never leaves.
            anchor = literal.splitlines()[0][:120]
            href += "#:~:text=" + quote(anchor, safe="").replace("-", "%2D")
        label = str(numbers.setdefault(href, len(numbers) + 1))
        periods = sorted({item.get("period_id", package["period_id"]) for item in group.values()})
        title = "Reporte original · " + ", ".join(periods)
        if len(group) > 1:
            # Multiple rows support the value; link the report as a whole
            # rather than selecting one row as if it alone proved the ratio.
            title += " · varios insumos del cálculo"
        result.append(
            {
                "label": label,
                "href": href,
                "title": title,
                "value": value,
            }
        )
    return result


def _citations_by_claim(
    record: dict[str, Any],
    package: dict[str, Any],
    calculations: dict[str, Any],
    authorized: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """claim_id -> citations, numbered in document order: the summary list first
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
    rendered = {claim["claim_id"]: claim["text"] for claim in authorized["claims"]} if authorized else {}
    for claim_id in ordered_claim_ids:
        if claim_id in result:
            continue
        result[claim_id] = _claim_citations(
            claims[claim_id], package, calculations, numbers, rendered.get(claim_id)
        )
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


def export_period(
    period_id: str, version: str, *, root: Path = flow.ROOT, entity_key: str | None = None
) -> dict[str, Any]:
    """Load one record and return exactly what consumer_payload() authorizes."""

    record = (
        _load_record(period_id, version, root)
        if entity_key is None
        else _load_record(period_id, version, root, entity_key=entity_key)
    )
    try:
        authorized = flow.consumer_payload(record, root)
        package, calculations, _ = flow.verified_inputs(record)
    except ValueError as error:
        raise MissingAnalysisInput(
            f"{period_id}/{version} has no current human approval under {root}: {error}"
        ) from error
    if (
        authorized.get("entity_key", "AEROMEXICO"),
        authorized.get("period_id"),
        authorized.get("version"),
    ) != (entity_key or "AEROMEXICO", period_id, version):
        raise ValueError("Authorized analysis identity does not match requested entity/period/version")
    authorized = _drop_private_sections(authorized, record)
    citations = _citations_by_claim(record, package, calculations, authorized)
    for claim in authorized["claims"]:
        claim["citations"] = citations.get(claim["claim_id"], [])
    return authorized


def export_analysis(
    out_dir: Path,
    *,
    root: Path = flow.ROOT,
    allow_missing: bool = False,
    manifest: list[dict[str, str]] | dict[str, Any] | None = None,
) -> list[Path]:
    """Write legacy or namespaced analysis files for every currently approved
    or published draft under ``root`` (see ``discover_approved_manifest``).
    An explicit ``manifest`` selects exact identities without discovery. It
    may be an identity list or a full publication manifest; every selected
    record still passes the current consumer gate and must match any supplied
    receipt fields. Missing/unapproved selections always fail, including dev.

    With ``allow_missing`` (dev only), a period whose record or approval is
    not present locally is skipped with a stderr note instead of failing
    the whole export — a clean public clone has neither.

    Never leaves stale files behind: every period file is built under a
    fresh temporary directory next to ``out_dir/analysis`` and the whole
    directory is swapped in atomically only once every period has exported
    and validated cleanly, so a revoked period (or, with an empty approved
    manifest, every period) does not linger from an earlier export.
    """

    selection = discover_approved_manifest(root) if manifest is None else validate_analysis_manifest(manifest)
    validator = Draft202012Validator(ANALYSIS_SCHEMA)
    rules = load_privacy_rules()
    analysis_dir = out_dir / "analysis"
    analysis_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(dir=analysis_dir.parent, prefix=analysis_dir.name + ".tmp-"))
    written_names: list[str] = []
    try:
        for entry in selection:
            period_id, version = entry["period_id"], entry["version"]
            try:
                payload = export_period(
                    period_id,
                    version,
                    root=root,
                    **({"entity_key": entry["entity_key"]} if "entity_key" in entry else {}),
                )
            except MissingAnalysisInput as error:
                if not allow_missing or manifest is not None:
                    raise
                print(f"web_export.analysis: skipping {period_id} ({error})", file=sys.stderr)
                continue
            for field in ("content_hash", "evidence_fingerprint", "approval_event", "audit_hash"):
                if field in entry and payload.get(field) != entry[field]:
                    raise ValueError(f"Selected analysis {period_id}/{version} does not match manifest {field}")
            errors = [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(payload)]
            if errors:
                raise ValueError(f"analysis/{period_id}.json does not match its schema: {errors[:5]}")
            check_privacy(payload, rules)
            relative = analysis_relative_path(entry).relative_to("analysis")
            write_json(tmp_dir / relative, payload)
            written_names.append(relative.as_posix())

        previous = None
        if analysis_dir.exists():
            previous = tmp_dir.with_name(analysis_dir.name + ".prev-" + tmp_dir.name.rsplit("-", 1)[-1])
            analysis_dir.rename(previous)
        try:
            tmp_dir.rename(analysis_dir)
        except OSError:
            if previous is not None:
                previous.rename(analysis_dir)
            raise
        if previous is not None:
            shutil.rmtree(previous, ignore_errors=True)
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return [analysis_dir / name for name in sorted(written_names)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=PATHS.root / "web" / "public" / "data" / "v1")
    parser.add_argument(
        "--analysis-manifest", type=Path,
        help="Exact identity list or publication_manifest.json; selected versions still require current approval.",
    )
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
            allow_missing=args.allow_missing,
            manifest=load_analysis_manifest(args.analysis_manifest) if args.analysis_manifest else None,
        )
    except (MissingAnalysisInput, ValueError, OSError) as error:
        print(f"web_export.analysis: {error}", file=sys.stderr)
        return 1
    for path in sorted(written):
        print(f"{path.relative_to(args.out)}\t{path.stat().st_size:,} bytes")
    print(f"{len(written)} file(s) written under {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
