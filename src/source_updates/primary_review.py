"""Offline verification of documentary review maps, never approval or Gold activation.

Matching a passage verifies its location, not the reviewer's semantic judgement.
The result deliberately retains unresolved mappings and curated decisions.
"""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path

from lxml import html
from pypdf import PdfReader

from src.source_updates.calendar import local_time
from src.source_updates.retained import public_original


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def within(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Review input must be relative without traversal")
    result = root / path
    if not result.resolve().is_relative_to(root.resolve()) or not result.is_file():
        raise ValueError("Review input escapes root or is missing")
    if any(part.is_symlink() for part in [result, *result.parents] if part != root.parent):
        raise ValueError("Review input may not use symlinks")
    return result


def original(root: Path, source: dict) -> Path:
    """Verify a single original against both manifest and sidecar, without copies."""
    path = within(root, source["source_file"])
    if sha(path) != source["sha256"] or path.stat().st_size != source["bytes"]:
        raise ValueError("Review source body hash/size mismatch")
    local_time(source["downloaded_at"])
    manifest = within(root, "_manifest.jsonl")
    rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    keys = ("source_file", "source_system", "source_url", "sha256", "bytes", "downloaded_at")
    matches = [row for row in rows if all(row.get(k) == source[k] for k in keys)]
    if not matches:
        raise ValueError("Review original absent from manifest")
    if matches[0].get("http_status") not in {None, 200}:
        raise ValueError("Failed HTTP response cannot support documentary facts")
    public_original(matches[0])
    sidecar = within(root, source["source_file"] + ".meta.json")
    meta = json.loads(sidecar.read_text())
    if any(meta.get(k) != source[k] for k in keys):
        raise ValueError("Review sidecar identity mismatch")
    if meta.get("http_status") != matches[0].get("http_status"):
        raise ValueError("Review sidecar HTTP status mismatch")
    if source.get("sidecar_sha256") and sha(sidecar) != source["sidecar_sha256"]:
        raise ValueError("Review sidecar hash mismatch")
    return path


def normalize(text: str) -> str:
    return " ".join(text.split())


def verify_evidence(evidence: dict, path: Path, cache: dict) -> None:
    locator = evidence["locator"]
    if "json_pointer" in locator:
        value = cache.setdefault((path, "json"), json.loads(path.read_text()))
        pointer = locator["json_pointer"]
        if not pointer.startswith("/"):
            raise ValueError("Expected absolute JSON pointer")
        for token in pointer[1:].split("/"):
            token = token.replace("~1", "/").replace("~0", "~")
            value = value[int(token)] if isinstance(value, list) else value[token]
        if (
            evidence.get("projection")
            == "sorted distinct forms observed; not an exhaustive lifetime catalogue"
        ):
            value = sorted(set(value))
        elif evidence.get("projection"):
            raise ValueError("Unknown evidence projection")
        if value != evidence["value"]:
            raise ValueError("JSON evidence value mismatch")
        return
    if "pdf_page_1based" in locator:
        key = (path, "pdf")
        if key not in cache:
            cache[key] = PdfReader(path)
        page = locator["pdf_page_1based"]
        if not isinstance(page, int) or not 1 <= page <= len(cache[key].pages):
            raise ValueError("PDF evidence page outside document")
        text = normalize(cache[key].pages[page - 1].extract_text())
    else:
        key = (path, "html")
        if key not in cache:
            cache[key] = html.fromstring(path.read_bytes())
        tree = cache[key]
        if "html_xpath" in locator:
            # lxml HTML preserves ix: tags, but XPath treats their colons as
            # namespace prefixes. Compare canonical getpath identities instead.
            nodes = [n for n in tree.iter() if n.getroottree().getpath(n) == locator["html_xpath"]]
            if len(nodes) != 1 or any(
                nodes[0].get(k) != v for k, v in evidence.get("attributes", {}).items()
            ):
                raise ValueError("HTML evidence path/attributes mismatch")
            text = normalize(" ".join(nodes[0].itertext()))
        else:
            text = normalize(" ".join(tree.itertext()))
    excerpt = evidence.get("excerpt", locator.get("excerpt"))
    if not isinstance(excerpt, str) or not excerpt:
        raise ValueError("Evidence requires an exact nonempty excerpt")
    if "normalized_char_start" in locator:
        start, end = locator["normalized_char_start"], locator["normalized_char_end"]
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end:
            raise ValueError("Invalid evidence offset")
        found = text[start:end] == excerpt
    else:
        found = excerpt in text
    if not found or evidence.get("matched_phrase", excerpt) not in excerpt:
        raise ValueError("Documentary evidence excerpt mismatch")


def no_activation(value) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"agent_eligible", "approval_granted", "activation_performed"} and item is not False:
                raise ValueError("Documentary review cannot confer approval or eligibility")
            no_activation(item)
    elif isinstance(value, list):
        for item in value:
            no_activation(item)


def verify(bundle: dict, roots: dict[str, Path], repository: Path) -> dict:
    no_activation(bundle)
    if bundle.get("schema_version") != 1 or bundle.get("agent_eligible") is not False:
        raise ValueError("Expected an explicitly ineligible documentary map")
    inputs = bundle.get("local_inputs", {})
    if not inputs or any(sha(within(repository, name)) != digest for name, digest in inputs.items()):
        raise ValueError("Reviewed local inputs changed or absent")
    paths = {}
    for key, source in bundle["sources"].items():
        root = roots[source.get("root_id", "old_public")]
        if source.get("source_system") == "dot_primary_review_candidate":
            # Unregistered DOT material is audit-only; it cannot borrow FAA's
            # active catalogue alias or enter Silver/Gold through this tool.
            capture = within(root, "capture-results.json")
            if sha(capture) != source["capture_results_sha256"]:
                raise ValueError("DOT audit capture receipt changed")
            local_time(source["captured_at"])
            records = json.loads(capture.read_text())
            records = records["results"] if isinstance(records, dict) else records
            match = [
                r
                for r in records
                if r.get("source_hash") == source["sha256"]
                and r.get("source_url") == source["source_url"]
                and r.get("http_status") == 200
                and r.get("source_file") == source["source_file"]
            ]
            if len(match) != 1 or source.get("catalogue_registration") != "not_active_no_alias_relabelling":
                raise ValueError("DOT audit capture missing, failed or mislabelled")
            path = within(root, source["source_file"])
            if any(match[0].get(k) != source[k] for k in ("captured_at", "bytes")):
                raise ValueError("DOT audit capture timestamp/size mismatch")
            if sha(path) != source["sha256"] or path.stat().st_size != source["bytes"]:
                raise ValueError("DOT audit body mismatch")
        else:
            path = original(root, source)
        paths[key] = path
    cache = {}
    for evidence in bundle["evidence"].values():
        verify_evidence(evidence, paths[evidence["source_id"]], cache)
    assessments = [
        a
        for carrier in bundle.get("carriers", {}).values()
        for a in carrier["attribute_assessments"].values()
    ]
    for item in [*assessments, *bundle.get("events", [])]:
        if item.get("agent_eligible") is not False:
            raise ValueError("Every assessment must remain ineligible")
        if any(key not in bundle["evidence"] for key in item.get("evidence_ids", [])):
            raise ValueError("Assessment references missing evidence")
        for dated in item.get("date_kinds", []):
            kind, value = dated["kind"], dated["value"]
            if kind == "reported_traffic_month":
                if len(value) != 7:
                    raise ValueError("Expected reported month YYYY-MM")
                date.fromisoformat(value + "-01")
            elif kind == "SEC_acceptance_timestamp":
                local_time(value)
            else:
                if len(value) != 10:
                    raise ValueError("Expected typed calendar date YYYY-MM-DD")
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError("Expected canonical typed calendar date")
            if (
                not kind
                or not dated.get("evidence_ids")
                or any(key not in bundle["evidence"] for key in dated["evidence_ids"])
            ):
                raise ValueError("Typed date references missing evidence")
    return {
        "mode": "offline_documentary_review",
        "status": "verified_document_locations_only",
        "sources": len(paths),
        "evidence": len(bundle["evidence"]),
        "profiles": len(bundle.get("carriers", {})),
        "attribute_assessments": len(assessments),
        "events": len(bundle.get("events", [])),
        "findings": bundle.get("findings", []),
        "semantic_curation_approved": False,
        "agent_eligible": False,
        "network_requests": 0,
        "writes": 0,
        "activation": "none",
        "layers": ["original_identity", "documentary_locator", "reviewed_input_hash"],
        "silver_gold_certification": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--root", action="append", default=[], help="ID=/path/to/originals")
    parser.add_argument("--repository", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    try:
        roots = dict(pair.split("=", 1) for pair in args.root)
        result = verify(
            json.loads(args.bundle.read_text()), {k: Path(v) for k, v in roots.items()}, args.repository
        )
    except (ValueError, KeyError, OSError, TypeError, IndexError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc), "activation": "none"}))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
