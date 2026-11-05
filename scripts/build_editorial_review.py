"""Build an explicitly unapproved local reading from retained evidence only.

This review format is not an Analysis Agent approval/consumer payload. It never
writes site/, Gold or the ledger. Normal profile replay failures remain visible
in the receipt and must be resolved before promotion through the existing gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

TOKEN = re.compile(r"\{\{([a-z_]+)\}\}")
ENTITIES = ("AEROMEXICO", "VOLARIS", "VIVA_AEROBUS")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def build(spec, contexts):
    period = spec["period_id"]
    if not re.fullmatch(r"\d{4}Q[1-4]", period):
        raise ValueError("Invalid review quarter")
    documents = {}
    fingerprints = {}
    for entity in ENTITIES:
        package, calculations = contexts[entity]
        if package["period_id"] != period or calculations["period_id"] != period:
            raise ValueError("Mixed review quarters")
        if calculations["evidence_fingerprint"] != package["evidence_fingerprint"]:
            raise ValueError("Calculation/evidence mismatch")
        fingerprints[entity] = package["evidence_fingerprint"]
    for entity, draft in spec["analyses"].items():
        if entity not in (*ENTITIES, "INDUSTRY"):
            raise ValueError("Unknown review entity")
        claims, summaries, sections = [], [], []
        seen = set()
        for part in draft["parts"]:
            cid = part["id"]
            if cid in seen:
                raise ValueError("Duplicate review claim")
            seen.add(cid)
            template = part["text"]
            if re.search(r"\d", TOKEN.sub("", template)):
                raise ValueError("Unbound number in review prose")
            bindings = part.get("bindings", {})
            if set(TOKEN.findall(template)) != set(bindings):
                raise ValueError("Unresolved/unused review binding")
            rendered, citations = template, []
            # Immutable JSON sorts object keys. Preserve citations by their
            # first occurrence in prose, independently of mapping insertion order.
            for alias in dict.fromkeys(TOKEN.findall(template)):
                binding = bindings[alias]
                owner = binding.get("entity", entity)
                package, calculations = contexts[owner]
                if "key" in binding:
                    nodes = [
                        n
                        for n in calculations["nodes"]
                        if n["key"] == binding["key"] and n["period_id"] == binding.get("period", period)
                    ]
                    if len(nodes) != 1 or not math.isfinite(nodes[0]["value"]):
                        raise ValueError("Missing/ambiguous review metric")
                    n = nodes[0]
                    fmt = binding.get("format", "reported")
                    if fmt == "money":
                        if n["unit"] != "USD":
                            raise ValueError("Wrong money unit")
                        value = f"US${n['value'] / 1e6:,.1f} millones"
                    elif fmt == "percent":
                        if n["unit"] not in ("fraction", "percent_change", "percent", "%"):
                            raise ValueError("Wrong percentage unit")
                        value = f"{n['value'] * (100 if n['unit'] == 'fraction' else 1):.1f}%"
                    elif fmt == "unit":
                        if n["unit"] != "cents_USD_per_ASM":
                            raise ValueError("Incompatible unit revenue")
                        value = f"{n['value']:.2f}"
                    elif fmt == "reported":
                        value = n["formatted_value"]
                    else:
                        raise ValueError("Unknown review format")
                    title = f"{owner} · {n['period_id']} · {n['key']}"
                    source = package["sources"][0]
                else:
                    excerpt = next(e for e in package["excerpts"] if e["excerpt_id"] == binding["excerpt_id"])
                    if binding["span"] not in excerpt["text"] or binding["value"] not in binding["span"]:
                        raise ValueError("Unsupported retained-source number")
                    value = binding["value"]
                    source = next(s for s in package["sources"] if s["artifact_id"] == excerpt["artifact_id"])
                    title = f"{owner} · {period} · {excerpt['locator']}"
                rendered = rendered.replace("{{" + alias + "}}", value)
                citations.append(
                    dict(label=str(len(citations) + 1), href=source["source_url"], title=title, value=value)
                )
            for support in part.get("supports", []):
                package, _ = contexts[support.get("entity", entity)]
                excerpt = next(e for e in package["excerpts"] if e["excerpt_id"] == support["excerpt_id"])
                if support["span"] not in excerpt["text"]:
                    raise ValueError("Unsupported qualitative attribution")
                source = next(s for s in package["sources"] if s["artifact_id"] == excerpt["artifact_id"])
                anchor = support.get("anchor", part.get("lead", ""))
                if not anchor or anchor not in rendered:
                    raise ValueError("Missing citation anchor")
                citations.append(
                    dict(
                        label=str(len(citations) + 1),
                        href=source["source_url"],
                        title=f"{support.get('entity', entity)} · {excerpt['locator']}",
                        value=anchor,
                    )
                )
            if not citations:
                raise ValueError("Review claim needs source support")
            emphasis = part.get("emphasis", [])
            if any(phrase not in rendered for phrase in emphasis):
                raise ValueError("Emphasis changes text")
            claims.append(dict(claim_id=cid, type=part["type"], text=rendered, citations=citations))
            if part.get("summary"):
                summaries.append(
                    dict(claim_id=cid, text=rendered, lead=part.get("lead", ""), emphasis=emphasis)
                )
            else:
                sections.append(dict(title=part["title"], paragraphs=[rendered], claim_ids=[cid]))
        if not summaries or not sections:
            raise ValueError("Summary and full reading required")
        documents[entity] = dict(
            entity_key=entity,
            period_id=period,
            version=digest(draft),
            thesis=draft["title"],
            summary_items=summaries,
            sections=sections,
            claims=claims,
        )
    if set(documents) != {*ENTITIES, "INDUSTRY"}:
        raise ValueError("Four review readings required")
    return dict(
        schema_version="editorial_review_v1",
        state="draft",
        period_id=period,
        version=digest([spec, fingerprints]),
        analyses=documents,
        evidence_fingerprints=fingerprints,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    target = args.out.resolve()
    if not target.is_relative_to(root / "tmp"):
        raise ValueError("Editorial review output is local tmp only")
    contexts = {
        e: (read(args.contexts / f"{e}-package.json"), read(args.contexts / f"{e}-calculations.json"))
        for e in ENTITIES
    }
    result = build(read(args.spec), contexts)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "state": "draft",
                "version": result["version"],
                "entities": list(result["analyses"]),
                "out": str(args.out),
            }
        )
    )


if __name__ == "__main__":
    main()
