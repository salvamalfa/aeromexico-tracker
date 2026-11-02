"""Versioned, source-replayed business stories on the ordinary approval ledger.

This profile imports the four reviewed Q3 stories without reinterpreting any
historical editorial contract. Preparing/importing never audits or approves.
All native issuer packages must still pass their original offline verifier.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from src.config import PATHS

from .evidence import digest

PROFILE = "quarterly_business_story_v1"
ENTITIES = ("AEROMEXICO", "VIVA_AEROBUS", "VOLARIS", "INDUSTRY")
PERIOD = "2026Q3"


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _contexts(packages):
    """Rebuild every calculation from verified physical sources, never prose."""
    from .issuer_quarter import calculate as issuer_calculate
    from .quarterly_release import calculate as am_calculate
    from .volaris_original_quarter import PROFILE as ORIGINAL_PROFILE
    from .volaris_original_quarter import calculate as original_calculate

    if set(packages) != set(ENTITIES) - {"INDUSTRY"}:
        raise ValueError("Story requires the exact three verified issuer packages")
    contexts = {}
    for entity, package in packages.items():
        if package.get("entity_key") != entity or package.get("period_id") != PERIOD:
            raise ValueError("Story source entity or quarter differs")
        expected_profile = "quarterly_release_v1" if entity == "AEROMEXICO" else "issuer_quarter_v1"
        actual_profile = package.get("source_profile", package.get("schema_version"))
        if actual_profile != expected_profile and not (
            entity == "VOLARIS" and actual_profile == ORIGINAL_PROFILE
        ):
            raise ValueError("Unsupported story source profile")
        calculate = (
            am_calculate
            if entity == "AEROMEXICO"
            else original_calculate
            if actual_profile == ORIGINAL_PROFILE
            else issuer_calculate
        )
        contexts[entity] = (package, calculate(package))
    return contexts


def prepare(spec, packages, entity):
    from scripts.build_editorial_review import build

    if entity not in ENTITIES or spec.get("period_id") != PERIOD:
        raise ValueError("Unreviewed story entity or edition")
    contexts = _contexts(packages)
    review = build(spec, contexts)
    return _package(spec, packages, entity, review)


def _package(spec, packages, entity, review):
    # The exact review identity survives promotion. A new source, number or word
    # gets another identity and cannot silently reuse an owner's prior review.
    base = dict(
        schema_version="entity_evidence_v1",
        source_profile=PROFILE,
        entity_key=entity,
        period_id=PERIOD,
        cutoff_date=max(p["cutoff_date"] for p in packages.values()),
        source_packages=packages,
        review_spec=spec,
        review_version=review["version"],
        review_entity_version=review["analyses"][entity]["version"],
        sources=[],
        excerpts=[],
        metrics=[],
    )
    fingerprint = digest(base)
    return dict(base, evidence_fingerprint=fingerprint, package_id=f"{entity}_{PERIOD}_{fingerprint}")


def replay(package):
    from scripts.build_editorial_review import build

    contexts = _contexts(package["source_packages"])
    review = build(package["review_spec"], contexts)
    rebuilt = _package(package["review_spec"], package["source_packages"], package["entity_key"], review)
    if rebuilt != package:
        raise ValueError("Story frozen evidence or review identity changed")
    document = review["analyses"][package["entity_key"]]
    base = dict(
        schema_version="quarterly_story_calculations_v1",
        status="validated",
        entity_key=package["entity_key"],
        period_id=package["period_id"],
        package_id=package["package_id"],
        evidence_fingerprint=package["evidence_fingerprint"],
        source_calculation_fingerprints={e: c["calculation_fingerprint"] for e, (_, c) in contexts.items()},
        document=document,
        nodes=[],
    )
    return dict(base, calculation_fingerprint=digest(base))


def draft_for(package, calculations):
    document = calculations["document"]
    entity = package["entity_key"]
    spec = package["review_spec"]["analyses"][entity]
    claims = [
        dict(
            claim_id="thesis",
            type="observed_fact",
            text_template=document["thesis"],
            bindings={},
            evidence_ids=[],
        )
    ]
    for part in spec["parts"]:
        rendered = next(c for c in document["claims"] if c["claim_id"] == part["id"])
        claims.append(
            dict(
                claim_id=part["id"],
                type=part["type"],
                text_template=rendered["text"],
                bindings={},
                evidence_ids=[],
                lead=part.get("lead", ""),
                emphasis=part.get("emphasis", []),
                source_part=part,
            )
        )
    return dict(
        schema_version="entity_analyst_v1",
        source_profile=PROFILE,
        state="draft",
        entity_key=entity,
        period_id=PERIOD,
        period_label="3T26",
        cutoff_date=package["cutoff_date"],
        guidance_as_of="report_date",
        selection_mode="retrospective",
        language="es-MX",
        model=None,
        model_unavailable_reason=(
            "The host does not expose a verifiable model identifier for this retained editorial review."
        ),
        package_id=package["package_id"],
        evidence_fingerprint=package["evidence_fingerprint"],
        calculation_fingerprint=calculations["calculation_fingerprint"],
        review_version=package["review_version"],
        review_entity_version=package["review_entity_version"],
        editorial_criteria_sha256=sha(PATHS.root / ".agents/skills/airline-quarterly-story/SKILL.md"),
        thesis_claim_id="thesis",
        summary_claim_ids=[p["id"] for p in spec["parts"] if p.get("summary")],
        summary_format="paragraphs",
        sections=[
            dict(key=p["id"], title=p["title"], claim_ids=[p["id"]])
            for p in spec["parts"]
            if not p.get("summary")
        ],
        claims=claims,
    )


def validate(draft, package, calculations):
    # Comparing the full normalized structure prevents a literal replacement,
    # hidden paragraph, duplicate placement or changed source binding. All
    # numbers were resolved from source nodes/spans in replay(), not this text.
    if draft != draft_for(package, calculations):
        raise ValueError("Story differs from its source-supported, versioned review")
    document = calculations["document"]
    rendered = {"thesis": document["thesis"], **{c["claim_id"]: c["text"] for c in document["claims"]}}
    summary_words = sum(len(rendered[c].split()) for c in draft["summary_claim_ids"])
    detail_words = sum(len(rendered[c].split()) for s in draft["sections"] for c in s["claim_ids"])
    if not 200 <= summary_words + detail_words <= 400 or not summary_words or not detail_words:
        raise ValueError("Business story must contain a summary and development within 200–400 words")
    return dict(
        status="passed",
        analysis_state="draft",
        claims=len(rendered),
        rendered=rendered,
        summary_words=summary_words,
        detail_words=detail_words,
        total_words=summary_words + detail_words,
    )


def verified_inputs(record):
    draft = record["draft"]
    entity = draft.get("entity_key")
    if (
        entity not in ENTITIES
        or draft.get("period_id") != PERIOD
        or not re.fullmatch(rf"{entity}_{PERIOD}_[a-f0-9]{{64}}", draft.get("package_id", ""))
        or not re.fullmatch(r"[a-f0-9]{64}", draft.get("calculation_fingerprint", ""))
    ):
        raise ValueError("Invalid business story identity")
    package = read(PATHS.root / "analysis_runs/evidence" / (draft["package_id"] + ".json"))
    calculations = read(
        PATHS.root / "analysis_runs/quantitative" / (draft["calculation_fingerprint"] + ".json")
    )
    if replay(package) != calculations:
        raise ValueError("Business story source calculation replay differs")
    return package, calculations, validate(draft, package, calculations)


def code_version():
    from .entity_adapter import code_version as runtime_version

    return digest(
        {
            "runtime": runtime_version(),
            "generators": {
                name: sha(PATHS.root / name)
                for name in (
                    "scripts/build_editorial_review.py",
                    "scripts/build_afac_market_review.py",
                    "scripts/build_anac_route_review.py",
            "scripts/prepare_quarterly_story_release.py",
                    "web/.env.production",
                )
            },
        }
    )


def require_current_presentation(record):
    from .analyst import SKILL

    if record["code_version"] != code_version() or record["prompt_version"] != sha(SKILL):
        raise ValueError(
            "Business story implementation changed: import and independently audit a new version"
        )


def import_draft(package):
    from .analyst import SKILL
    from .issuer_quarter import immutable

    calculations = replay(package)
    draft = draft_for(package, calculations)
    checks = validate(draft, package, calculations)
    record = dict(
        draft=draft, prompt_version=sha(SKILL), code_version=code_version(), content_hash=digest(draft)
    )
    record["version"] = digest({k: record[k] for k in ("draft", "prompt_version", "code_version")})
    record.update(
        analysis_id=f"{draft['entity_key']}_{PERIOD}_{record['version']}",
        created_at=datetime.now(UTC).isoformat(),
        mechanical_checks={k: v for k, v in checks.items() if k != "rendered"},
    )
    immutable(PATHS.root / "analysis_runs/evidence" / (package["package_id"] + ".json"), package)
    immutable(
        PATHS.root / "analysis_runs/quantitative" / (calculations["calculation_fingerprint"] + ".json"),
        calculations,
    )
    path = PATHS.root / "analysis_runs/drafts" / draft["entity_key"] / PERIOD / (record["version"] + ".json")
    if not path.exists():
        immutable(path, record)
    verified_inputs(read(path))
    return path


def citations(claim, calculations, numbers):
    if claim["claim_id"] == "thesis":
        return []
    source = next(c for c in calculations["document"]["claims"] if c["claim_id"] == claim["claim_id"])
    return [dict(c, label=str(numbers.setdefault(c["href"], len(numbers) + 1))) for c in source["citations"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--contexts", type=Path, required=True)
    parser.add_argument("--entity", choices=ENTITIES, required=True)
    args = parser.parse_args()
    packages = {e: read(args.contexts / f"{e}-package.json") for e in ENTITIES if e != "INDUSTRY"}
    print(import_draft(prepare(read(args.spec), packages, args.entity)))


if __name__ == "__main__":
    main()
