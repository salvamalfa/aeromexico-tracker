"""Immutable, source-replayed entity drafts integrated with the approval ledger.

Review capsules stay in ignored analysis_runs. Only pinned, reviewed offline
extractors execute; sources, captured versions, calculations and approved prose
are rechecked before every handoff. Legacy analyst_v1 is unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from src.config import PATHS

from .evidence import canonical, digest

ENTITIES = {"VIVA_AEROBUS", "VOLARIS", "INDUSTRY"}
REPLAY_CODE = {
    "VIVA_AEROBUS": ("prepare.py", "9b8a6a0dd5732764047a56f14b9a1aa76dd3087642bb41c6d7b40f8072d06203"),
    "VOLARIS": ("prepare.py", "3b1edea60088851ea0272e8fe1ba80363c7aca56bafa8964562018f0ee9bdb25"),
    "INDUSTRY": ("build_context.py", "1a99818ff7927331c429e477f4795da4b7a39d22b74aa0a7ab116b24c3eb5e0a"),
}
TOKEN = re.compile(r"\{\{([^{}]+)\}\}")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def code_version():
    root = PATHS.root
    paths = {root / name for name in ("src/dashboard/entities.py", "src/config.py", "uv.lock")}
    # Conservatively bind all first-party Python runtime code, including
    # transitive imports (analytics, evidence filtering, lazy/relative imports)
    # and future packages. A directory allowlist can miss a dependency outside
    # dashboard/export; static import traversal can miss dynamic imports.
    # Unrelated Python changes intentionally require a fresh technical review.
    paths.update((root / "src").rglob("*.py"))
    paths.update(path for path in (root / "contracts/web").rglob("*") if path.is_file())
    test_directories = {"test", "tests", "spec", "specs", "__tests__", "__specs__"}
    web_root = root / "web/src"
    for path in web_root.rglob("*"):
        if (
            path.is_file()
            and path.suffix in {".ts", ".tsx", ".js", ".jsx", ".json", ".css"}
            and not test_directories.intersection(path.relative_to(web_root).parts)
            and not re.search(r"(?:^|[._-])(?:test|spec)(?:[._-]|$)", path.name)
        ):
            paths.add(path)
    for name in ("index.html", "package.json", "package-lock.json", "vite.config.ts"):
        path = root / "web" / name
        if path.is_file():
            paths.add(path)
    paths.update((root / "web").glob("tsconfig*.json"))
    names = sorted(path.relative_to(root).as_posix() for path in paths if path.is_file())
    for name in ("src/dashboard/entities.py", "src/config.py", "uv.lock"):
        if name not in names:
            raise ValueError(f"Required entity dependency is missing: {name}")
    return digest({name: sha(root / name) for name in names})


def require_current_presentation(record):
    from .analyst import SKILL

    if record["code_version"] != code_version() or record["prompt_version"] != sha(SKILL):
        raise ValueError("Entity implementation changed: import and audit a new version")


def capsule_path(package):
    key = package["capsule_fingerprint"]
    if not re.fullmatch(r"[a-f0-9]{64}", key):
        raise ValueError("Invalid capsule identity")
    return PATHS.root / "analysis_runs/entity_review_bundles" / key


def _files(folder):
    return {
        p.name: sha(p)
        for p in sorted(folder.iterdir())
        if p.is_file() and p.suffix in {".json", ".py", ".md"}
    }


def _context(folder):
    return read(folder / ("context.json" if (folder / "context.json").exists() else "closed-context.json"))


def _sources(evidence):
    result = []
    for source in evidence["artifacts"]:
        name = source.get("source_file")
        if not name:
            raw = source.get("local_path", source.get("original_file", ""))
            name = raw.split("/data/bronze/", 1)[-1]
        path = (PATHS.bronze / name).resolve()
        if not path.is_relative_to(PATHS.bronze.resolve()):
            raise ValueError("Source path escapes Bronze")
        expected = source.get("artifact_sha256", source.get("sha256"))
        if sha(path) != expected:
            raise ValueError("Original source bytes differ")
        meta_path = Path(str(path) + ".meta.json")
        meta = read(meta_path)
        url = source["source_url"]
        if meta["sha256"] != expected or meta["source_url"] != url or meta["http_status"] != 200:
            raise ValueError("Captured source version disagrees with original")
        captured = datetime.fromisoformat(meta["downloaded_at"])
        if captured.tzinfo is None or captured.date().isoformat() > "2026-10-13":
            raise ValueError("Source version was not captured by the retrospective cutoff")
        result.append(
            {
                "artifact_id": source["artifact_id"],
                "source_file": name,
                "source_url": url,
                "artifact_sha256": expected,
                "capture_proof_sha256": sha(meta_path),
                "version_available_at": captured.isoformat(),
            }
        )
    return result


def _verify_capsule(package):
    folder = capsule_path(package)
    if _files(folder) != package["capsule_files"]:
        raise ValueError("Reviewed capsule bytes changed")
    evidence = read(
        folder / ("source-evidence.json" if package["entity_key"] == "VIVA_AEROBUS" else "evidence.json")
    )
    if _sources(evidence) != package["sources"]:
        raise ValueError("Source version/capture proof changed")
    return folder, evidence


def _replay(package, folder):
    entity = package["entity_key"]
    filename, expected = REPLAY_CODE[entity]
    if sha(folder / filename) != expected:
        raise ValueError("Unreviewed extractor: refusing execution")
    frozen = _context(folder)
    with tempfile.TemporaryDirectory(prefix="entity-replay-") as temporary:
        args = [sys.executable, str(folder / filename)]
        args += ["--freeze"] if entity == "VIVA_AEROBUS" else ["freeze"] if entity == "VOLARIS" else []
        args += ["--tracker-root", str(PATHS.root), "--output-dir", temporary]
        subprocess.run(args, check=True, capture_output=True, text=True, timeout=120)
        reproduced = _context(Path(temporary))
        keys = (
            ("inputs", "financial_inputs", "values", "carrier_values", "aggregate_values", "excerpts")
            if entity == "INDUSTRY"
            else ("inputs", "calculations")
        )
        if any(frozen[key] != reproduced[key] for key in keys):
            raise ValueError("Original-source calculation replay differs from reviewed context")
    return frozen


def _require_unique_ids(items, field):
    seen = set()
    for item in items:
        identity = item.get(field)
        if not isinstance(identity, str) or not identity:
            raise ValueError(f"Invalid {field}")
        if identity in seen:
            raise ValueError(f"Duplicate {field}: {identity}")
        seen.add(identity)


def _normalize(package, context, evidence, candidate):
    _require_unique_ids(package["sources"], "artifact_id")
    _require_unique_ids(evidence["excerpts"], "excerpt_id")
    excerpts = []
    for original in evidence["excerpts"]:
        excerpt = dict(original)
        excerpt["text"] = original.get(
            "text",
            original.get(
                "literal_text", original.get("literal_table_fragment", original.get("literal_fragment", ""))
            ),
        )
        source_file = excerpt.get("source_file")
        if not isinstance(source_file, str) or not source_file:
            raise ValueError("Excerpt source_file is required")
        matches = [s for s in package["sources"] if s["source_file"] == source_file]
        if len(matches) != 1:
            raise ValueError("Excerpt source identity is ambiguous")
        artifact_id = matches[0]["artifact_id"]
        if "artifact_id" in excerpt and excerpt["artifact_id"] != artifact_id:
            raise ValueError("Excerpt artifact identity differs from its source_file")
        excerpt["artifact_id"] = artifact_id
        excerpts.append(excerpt)
    by_excerpt = {e["excerpt_id"]: e for e in excerpts}
    raw_inputs = context["inputs"]
    inputs = list(raw_inputs.values()) if isinstance(raw_inputs, dict) else list(raw_inputs)
    inputs += context.get("financial_inputs", [])
    metrics = []
    for item in inputs:
        eid = item["excerpt_id"]
        metrics.append(
            dict(item, metric_id=item.get("input_id", eid), artifact_id=by_excerpt[eid]["artifact_id"])
        )
    raw_nodes = context.get("calculations", context.get("values"))
    nodes = (
        [dict(n) for n in raw_nodes.values()] if isinstance(raw_nodes, dict) else [dict(n) for n in raw_nodes]
    )
    for node in nodes:
        refs = node.get("input_ids", node.get("input_references", list(node.get("inputs", {}).values())))
        node.update(
            input_ids=refs,
            formula=node.get("formula", node.get("formula_python", "")),
            status="available",
            key=node["calculation_id"],
            entity_formatted=True,
        )
        node["formatted_value"] = node["formatted"] if "formatted" in node else node["formatted_value"]
    by_node = {n["calculation_id"]: n for n in nodes}
    draft = json.loads(canonical(candidate))
    for claim in draft["claims"]:
        bindings = {}
        template = claim["text_template"]
        for alias, binding in claim["bindings"].items():
            key = "n_" + alias.lower()
            if key in bindings:
                raise ValueError("Normalized binding alias collision")
            binding = dict(binding)
            if binding.get("presentation") == "absolute_money":
                parent = by_node[binding["calculation_id"]]
                clone = dict(
                    parent,
                    calculation_id=parent["calculation_id"] + "__absolute",
                    value=abs(parent["value"]),
                    input_ids=[parent["calculation_id"]],
                    formula="absolute magnitude",
                    formatted_value=parent["formatted_value"].removeprefix("-"),
                )
                if clone["calculation_id"] not in by_node:
                    nodes.append(clone)
                    by_node[clone["calculation_id"]] = clone
                binding["calculation_id"] = clone["calculation_id"]
            binding.pop("presentation", None)
            bindings[key] = binding
            template = template.replace("{{" + alias + "}}", "{{" + key + "}}")
        claim.update(text_template=template, bindings=bindings)
    calculations = {
        "schema_version": "entity_quantitative_v1",
        "entity_key": package["entity_key"],
        "period_id": package["period_id"],
        "status": "validated",
        "nodes": nodes,
    }
    calculations["calculation_fingerprint"] = digest(calculations)
    package = dict(package, excerpts=excerpts, metrics=metrics)
    draft.update(
        schema_version="entity_analyst_v1",
        package_id=package["package_id"],
        evidence_fingerprint=package["evidence_fingerprint"],
        calculation_fingerprint=calculations["calculation_fingerprint"],
        entity_key=package["entity_key"],
        period_label="2T26 (abril–junio de 2026)",
        cutoff_date="2026-10-13",
        selection_mode="retrospective",
        guidance_as_of="report_date",
    )
    return package, calculations, draft


def validate(draft, package, calculations):
    from .analyst import TYPES, lineage

    if draft["schema_version"] != "entity_analyst_v1" or draft["state"] != "draft":
        raise ValueError("Invalid entity drafting contract")
    for field in ("entity_key", "period_id", "package_id", "evidence_fingerprint"):
        if draft[field] != package[field]:
            raise ValueError("Entity draft/input identity mismatch")
    if draft["calculation_fingerprint"] != calculations["calculation_fingerprint"]:
        raise ValueError("Entity calculation identity mismatch")
    nodes = {n["calculation_id"]: n for n in calculations["nodes"]}
    excerpts = {e["excerpt_id"]: e for e in package["excerpts"]}
    rendered = {}
    for claim in draft["claims"]:
        cid = claim["claim_id"]
        if cid in rendered or claim["type"] not in TYPES:
            raise ValueError("Invalid entity claim identity/type")
        template = claim["text_template"]
        if re.search(r"\d|[{}]", TOKEN.sub("", template)) or set(TOKEN.findall(template)) != set(
            claim["bindings"]
        ):
            raise ValueError("Unbound numeric prose or malformed binding")
        if not set(claim["evidence_ids"]) <= set(excerpts):
            raise ValueError("Unresolved evidence")
        for alias, binding in claim["bindings"].items():
            node = nodes[binding["calculation_id"]]
            if not isinstance(node["value"], (int, float)) or not math.isfinite(node["value"]):
                raise ValueError("Non-finite entity calculation")
            if node["unit"] != binding["unit"] or node["period_id"] != binding["period_id"]:
                raise ValueError("Binding unit/period mismatch")
            lineage(node["calculation_id"], package, calculations)
            template = template.replace("{{" + alias + "}}", node["formatted_value"])
        for key in claim["support_calculation_ids"]:
            lineage(key, package, calculations)
        for span in claim.get("support_spans", []):
            if (
                span["excerpt_id"] not in claim["evidence_ids"]
                or span["text"] not in excerpts[span["excerpt_id"]]["text"]
            ):
                raise ValueError("Attribution span is not in exact cited original")
        if claim["type"] == "company_attribution" and not claim.get("support_spans"):
            raise ValueError("Attribution without literal source")
        if claim["type"] == "hypothesis" and not claim["limitations"]:
            raise ValueError("Hypothesis without limits")
        if claim.get("lead") and not template.startswith(claim["lead"]):
            raise ValueError("Unsupported summary emphasis")
        rendered[cid] = template
    expected = {key: value.replace("**", "") for key, value in package["approved_rendered"].items()}
    if rendered != expected:
        raise ValueError("Canonical prose differs from the exact owner-reviewed text")
    summary = sum(len(rendered[c].split()) for c in draft["summary_claim_ids"])
    detail = sum(
        len(rendered[c].split())
        for s in draft["sections"]
        if s["key"] != "methodology"
        for c in s["claim_ids"]
    )
    if not 150 <= summary <= 250 or not 600 <= detail <= 1000:
        raise ValueError("Entity editorial length outside contract")
    return {"status": "passed", "rendered": rendered, "summary_words": summary, "detail_words": detail}


def verified_inputs(record):
    if record["draft"].get("source_profile") == "issuer_quarter_v1":
        from .issuer_quarter import verified_inputs as verify_issuer
        return verify_issuer(record)
    draft = record["draft"]
    entity, period = draft.get("entity_key"), draft.get("period_id")
    if entity not in ENTITIES or not isinstance(period, str) or not re.fullmatch(r"\d{4}Q[1-4]", period):
        raise ValueError("Invalid entity input identity")
    if not re.fullmatch(f"{entity}_{period}_[a-f0-9]{{64}}", draft.get("package_id", "")):
        raise ValueError("Invalid entity package path")
    if not re.fullmatch(r"[a-f0-9]{64}", draft.get("calculation_fingerprint", "")):
        raise ValueError("Invalid entity calculation path")
    package = read(PATHS.root / "analysis_runs/evidence" / (draft["package_id"] + ".json"))
    calculations = read(
        PATHS.root / "analysis_runs/quantitative" / (draft["calculation_fingerprint"] + ".json")
    )
    core = {
        k: v
        for k, v in package.items()
        if k not in {"package_id", "evidence_fingerprint", "excerpts", "metrics"}
    }
    if (
        digest(core) != package["evidence_fingerprint"]
        or package["package_id"] != f"{package['entity_key']}_{package['period_id']}_{digest(core)}"
    ):
        raise ValueError("Entity evidence fingerprint mismatch")
    folder, evidence = _verify_capsule(package)
    context = _replay(package, folder)
    rebuilt, recomputed, normalized = _normalize(
        core | {"package_id": package["package_id"], "evidence_fingerprint": package["evidence_fingerprint"]},
        context,
        evidence,
        read(folder / "draft.json"),
    )
    if rebuilt != package or recomputed != calculations or normalized != draft:
        raise ValueError("Entity canonical replay mismatch")
    return package, calculations, validate(draft, package, calculations)


def import_entity(bundle, entity):
    from .analyst import SKILL
    from .lifecycle import atomic_json

    if entity not in ENTITIES:
        raise ValueError("Unknown review entity")
    original = Path(bundle) / entity
    files = _files(original)
    fingerprint = digest(files)
    folder = PATHS.root / "analysis_runs/entity_review_bundles" / fingerprint
    if not folder.exists():
        folder.mkdir(parents=True)
        for name in files:
            shutil.copy2(original / name, folder / name)
    evidence = read(folder / ("source-evidence.json" if entity == "VIVA_AEROBUS" else "evidence.json"))
    core = {
        "schema_version": "entity_evidence_v1",
        "entity_key": entity,
        "period_id": "2026Q2",
        "cutoff_date": "2026-10-13",
        "selection_mode": "retrospective",
        "capsule_fingerprint": fingerprint,
        "capsule_files": files,
        "sources": _sources(evidence),
        "approved_rendered": read(folder / "rendered-claims.json"),
    }
    package = dict(core, evidence_fingerprint=digest(core), package_id=f"{entity}_2026Q2_{digest(core)}")
    context = _replay(package, folder)
    package, calculations, draft = _normalize(package, context, evidence, read(folder / "draft.json"))
    checks = validate(draft, package, calculations)
    for path, value in [
        (PATHS.root / "analysis_runs/evidence" / (package["package_id"] + ".json"), package),
        (
            PATHS.root / "analysis_runs/quantitative" / (calculations["calculation_fingerprint"] + ".json"),
            calculations,
        ),
    ]:
        if not path.exists():
            atomic_json(path, value)
        elif read(path) != value:
            raise ValueError("Immutable inputs differ")
    record = {
        "draft": draft,
        "prompt_version": sha(SKILL),
        "code_version": code_version(),
        "content_hash": digest(draft),
    }
    record["version"] = digest({k: record[k] for k in ("draft", "prompt_version", "code_version")})
    record.update(
        analysis_id=f"{entity}_2026Q2_{record['version']}",
        created_at=datetime.now(timezone.utc).isoformat(),
        mechanical_checks={k: v for k, v in checks.items() if k != "rendered"},
    )
    path = PATHS.root / "analysis_runs/drafts" / entity / "2026Q2" / (record["version"] + ".json")
    if not path.exists():
        atomic_json(path, record)
    verified_inputs(read(path))
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path)
    args = parser.parse_args()
    for entity in sorted(ENTITIES):
        print(import_entity(args.bundle, entity))
