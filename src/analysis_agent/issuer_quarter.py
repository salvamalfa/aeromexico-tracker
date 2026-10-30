"""Source-replayed compact entity theses, using the ordinary approval ledger.

The first reviewed editions are Viva/Volaris 2026Q3. No acquisition, Gold
activation, audit, approval or publication occurs in this adapter.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pypdf import PdfReader

from src.config import PATHS
from src.pipeline.offline import block_network

from .evidence import compact, digest

PROFILE = "issuer_quarter_v1"
ENTITIES = {"VIVA_AEROBUS": "viva_financials", "VOLARIS": "volaris_sec"}
TOKEN = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")
# Explicit statement selection prevents duplicate highlight/income observations.
SPECS = {
    "VIVA_AEROBUS": {
        "revenue": ("income", "total_revenue", "consolidated"),
        "operating_income": ("income", "operating_income", "consolidated"),
        "net_income": ("income", "net_income", "consolidated"),
        "operating_margin": ("income", "operating_margin", "consolidated"),
        "ebitdar": ("indicators", "ebitdar_non_ifrs", "consolidated"),
        "ebitdar_margin": ("indicators", "ebitdar_margin", "consolidated"),
        "asm": ("indicators", "asm", "total"),
        "rpm": ("indicators", "rpm", "total"),
        "passengers": ("indicators", "booked_passengers", "total"),
        "load": ("indicators", "scheduled_load_factor", "total"),
        "trasm": ("indicators", "trasm", "total"),
        "casm": ("indicators", "casm", "total"),
        "casm_ex": ("indicators", "casm_ex_fuel", "total"),
        "fare": ("indicators", "fare_per_booked_passenger", "total"),
        "ancillary_per_passenger": ("indicators", "ancillary_per_booked_passenger", "total"),
        "ancillary_revenue": ("income", "ancillary_revenue", "consolidated"),
        "fuel": ("income", "fuel", "consolidated"),
    },
    "VOLARIS": {
        "revenue": ("income_quarter", "total_revenue", "total"),
        "operating_income": ("income_quarter", "operating_result", "total"),
        "net_income": ("income_quarter", "net_result", "total"),
        "operating_margin": ("operations_quarter", "operating_margin", "total"),
        "ebitdar": ("highlights", "ebitdar", "total"),
        "ebitdar_margin": ("highlights", "ebitdar_margin", "total"),
        "asm": ("operations_quarter", "asm_total", "total"),
        "rpm": ("operations_quarter", "rpm_total", "total"),
        "passengers": ("operations_quarter", "booked_passengers_total", "total"),
        "load": ("operations_quarter", "load_factor_total", "total"),
        "trasm": ("operations_quarter", "trasm", "total"),
        "casm": ("operations_quarter", "casm", "total"),
        "casm_ex": ("operations_quarter", "casm_ex_fuel", "total"),
        "fare": ("operations_quarter", "base_fare_per_passenger", "total"),
        "ancillary_per_passenger": ("operations_quarter", "ancillary_revenue_per_passenger", "total"),
        "ancillary_revenue": ("ancillary_quarter", "ancillary_revenues", "total"),
        "fuel": ("income_quarter", "fuel_expense", "total"),
    },
}
UNITS = {
    "usd": "USD",
    "USD_cents_per_seat_mile": "cents_USD_per_ASM",
    "usd_cents_per_seat_mile": "cents_USD_per_ASM",
    "booked_passengers": "count",
    "revenue_passenger_miles": "passenger_miles",
    "USD_per_booked_passenger": "USD_per_booked_passenger",
    "usd_per_booked_passenger": "USD_per_booked_passenger",
}
NOTES = [
    "Pasajeros con boleto comprado; no equivale necesariamente a pasajeros transportados.",
    "Ocupación reportada de vuelos regulares; las métricas totales pueden incluir chárter.",
    "EBITDAR es una medida alternativa de la empresa, no utilidad neta ni flujo de caja.",
]


def read(path):
    return json.loads(Path(path).read_bytes())


def immutable(path, value):
    from .lifecycle import atomic_json

    path = Path(path)
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("Analysis output cannot traverse symlinks")
    if not any(
        path.resolve().is_relative_to((PATHS.root / name).resolve())
        for name in ("analysis_runs", "tmp/source-updates")
    ):
        raise ValueError("Analysis artifacts must stay in private ignored destinations")
    if path.exists():
        if read(path) != value:
            raise ValueError("Immutable analysis artifact differs")
    else:
        atomic_json(path, value)


def replay(workspace, entity, period, retention, cutoff):
    """Rebuild all source layers from retained originals, not trusted cached values."""
    if entity not in ENTITIES or period != "2026Q3":
        raise ValueError("Unreviewed entity/edition")
    workspace = Path(workspace)
    if any(p.is_symlink() for p in [workspace, *workspace.parents]):
        raise ValueError("Issuer workspace cannot traverse symlinks")
    workspace = workspace.resolve()
    if not workspace.is_relative_to((PATHS.root / "tmp/source-updates").resolve()) or any(
        p.is_symlink() for p in workspace.rglob("*")
    ):
        raise ValueError("Issuer workspace must be local, isolated and without symlinks")
    if (workspace / ".source-update.lock").exists():
        raise ValueError("Issuer source writer is active")
    product = ENTITIES[entity]
    with block_network():
        if entity == "VIVA_AEROBUS":
            from src.source_updates.retained import originals
            from src.source_updates.viva_financial_gold import frames
            from src.source_updates.viva_financials import parse

            inputs, receipt_hash = originals(workspace, product, retention, cutoff)
            native, details = parse(inputs, period)
            outputs, _ = frames(workspace, product, period, native, details)
            table = "fact_viva_retained_financial_source_metrics"
        else:
            from src.source_updates.carrier_source_gold import frames
            from src.source_updates.carrier_source_inputs import inputs as originals
            from src.source_updates.volaris_sec_source import read as parse

            inputs, receipt_hash = originals(workspace, product, retention, cutoff)
            native, details = parse(inputs, period)
            outputs, _ = frames(workspace, product, period, native, details)
            table = "fact_volaris_sec_source"
        for name, frame in outputs.items():
            try:
                pd.testing.assert_frame_equal(
                    pd.read_parquet(workspace / "data" / (name + ".parquet")), frame, check_exact=True
                )
            except AssertionError as exc:
                raise ValueError(f"Issuer source replay differs: {name}") from exc
    return inputs, outputs[f"gold/{table}"], receipt_hash, details


def package_for(workspace, entity, period, retention, cutoff):
    inputs, frame, receipt_hash, details = replay(workspace, entity, period, retention, cutoff)
    workspace = Path(workspace).resolve()
    sources, excerpts, metrics = [], [], []
    for role, (raw, meta) in sorted(inputs.items()):
        source = dict(
            artifact_id="art_" + meta["sha256"],
            source_file=meta["source_file"],
            source_url=meta["source_url"],
            artifact_sha256=meta["sha256"],
            captured_at=meta["downloaded_at"],
            period_id="2026Q2" if role == "prior_quarter" else period,
            version_available_at=meta["downloaded_at"],
            publication_basis="Retained source capture; printed issuer period replayed separately",
            role=role,
        )
        sources.append(source)
        if entity == "VIVA_AEROBUS" and role == "pdf":
            for index, page in enumerate(PdfReader(io.BytesIO(raw)).pages, 1):
                excerpt = dict(
                    artifact_id=source["artifact_id"],
                    locator=f"page={index}",
                    text=compact(page.extract_text() or ""),
                    period_id=period,
                    source_content_is_untrusted=True,
                )
                excerpt["excerpt_id"] = "exc_" + digest(excerpt)
                excerpts.append(excerpt)

    def add_metric(row, key, actual_period):
        aid = "art_" + row.source_hash
        if entity == "VIVA_AEROBUS":
            page = int(row.source_locator.split("/")[0].split(":")[1])
            eid = next(e["excerpt_id"] for e in excerpts if e["locator"] == f"page={page}")
        else:
            excerpt = dict(
                artifact_id=aid,
                locator=row.source_locator,
                text=row.source_excerpt,
                period_id=actual_period,
                source_content_is_untrusted=True,
            )
            excerpt["excerpt_id"] = "exc_" + digest(excerpt)
            if excerpt not in excerpts:
                excerpts.append(excerpt)
            eid = excerpt["excerpt_id"]
        metric = dict(
            metric_key=key,
            value=float(row.value),
            unit=UNITS.get(row.unit, row.unit),
            period_id=actual_period,
            artifact_id=aid,
            excerpt_id=eid,
            definition=row.metric_key,
            scope=row.segment,
            source_record_id=row.record_id,
            record_id=row.record_id,
        )
        from .analyst import formatted

        metric["formatted_value"] = formatted(
            {**metric, "formatted_value": str(metric["value"])}, business=True
        )
        metric["metric_id"] = "metric_" + digest(metric)
        metrics.append(metric)

    for key, (statement, name, segment) in SPECS[entity].items():
        for year in (2026, 2025):
            selected = frame[
                (frame.edition == period)
                & (frame.period_type == "quarter")
                & (frame.period_start_date == f"{year}-07-01")
                & (frame.period_end_date == f"{year}-09-30")
                & (frame.statement == statement)
                & (frame.metric_key == name)
                & (frame.segment == segment)
            ]
            if len(selected) != 1:
                raise ValueError(f"Exact comparable metric missing/ambiguous: {key}/{year}")
            add_metric(next(selected.itertuples()), key, f"{year}Q3")
    if entity == "VIVA_AEROBUS":
        days = set(frame.loc[frame.edition == period, "report_date"])
        if len(days) != 1:
            raise ValueError("Ambiguous issuer report date")
        report_date = next(iter(days))
    else:
        report_date = details["report_date"]
    if datetime.fromisoformat(report_date).date().isoformat() != report_date:
        raise ValueError("Issuer report date must be an exact day")
    if report_date > datetime.fromisoformat(cutoff).date().isoformat():
        raise ValueError("Issuer report date follows the source cutoff")
    base = dict(
        schema_version="entity_evidence_v1",
        source_profile=PROFILE,
        entity_key=entity,
        period_id=period,
        cutoff_date=datetime.fromisoformat(cutoff).date().isoformat(),
        report_date=report_date,
        source_cutoff=cutoff,
        workspace=workspace.relative_to(PATHS.root).as_posix(),
        retention_id=retention,
        retention_receipt_sha256=receipt_hash,
        source_binding=dict(
            product=ENTITIES[entity],
            period=period,
            receipt_id=retention,
            candidate_as_of=cutoff,
            output_sha256={
                p.relative_to(workspace / "data").with_suffix("").as_posix(): hashlib.sha256(
                    p.read_bytes()
                ).hexdigest()
                for p in sorted((workspace / "data").rglob("*.parquet"))
            },
        ),
        selection_mode="retrospective_source_edition",
        sources=sources,
        excerpts=excerpts,
        metrics=metrics,
        public_notes=NOTES
        + (
            [
                "Volaris: cifras de una reconstrucción visible autorizada de SEC; "
                "no son bytes originales del archivo SEC."
            ]
            if entity == "VOLARIS"
            else []
        ),
    )
    fingerprint = digest(base)
    return dict(base, evidence_fingerprint=fingerprint, package_id=f"{entity}_{period}_{fingerprint}")


def verify(package):
    if package.get("source_profile") != PROFILE:
        raise ValueError("Unexpected issuer profile")
    rebuilt = package_for(
        PATHS.root / package["workspace"],
        package["entity_key"],
        package["period_id"],
        package["retention_id"],
        package["source_cutoff"],
    )
    if rebuilt != package:
        raise ValueError("Issuer evidence changed after freezing")
    return {"status": "passed", "package_id": package["package_id"]}


def calculate(package):
    from .analyst import formatted
    from .quantitative import calculate as operation
    from .quantitative import node

    verify(package)
    nodes, lookup = [], {}

    def put(n):
        n["entity_formatted"] = True
        n["formatted_value"] = formatted(n, business=True)
        if n["unit"] == "USD_per_booked_passenger":
            n["formatted_value"] = f"{n['value']:.2f} dólares por pasajero con boleto"
        if n["unit"] == "cents_USD_per_ASM":
            n["formatted_value"] = f"{n['value']:.2f} centavos de dólar por asiento-milla ofrecido"
        nodes.append(n)
        lookup[(n["period_id"], n["key"])] = n
        return n

    for metric in package["metrics"]:
        n = node(
            metric["period_id"],
            metric["metric_key"],
            metric["unit"],
            metric["value"],
            [metric["value"], metric["value"]],
            [metric["metric_id"]],
            "Reported normalized source value, original published precision",
            basis={"definition": metric["definition"], "scope": metric["scope"]},
        )
        put(n)
    for period in ("2026Q3", "2025Q3"):
        for key, parent, unit, factor in [
            ("ask", "asm", "seat_km", 1.609344),
            ("rask", "trasm", "cents_USD_per_ASK", 1 / 1.609344),
            ("cask", "casm", "cents_USD_per_ASK", 1 / 1.609344),
        ]:
            put(operation(period, key, "scale", [lookup[(period, parent)]], unit, factor))
    for key in SPECS[package["entity_key"]]:
        current, prior = lookup[("2026Q3", key)], lookup[("2025Q3", key)]
        if prior["value"] > 0:
            delta = put(operation("2026Q3", key + "_delta", "subtract", [current, prior], current["unit"]))
            put(operation("2026Q3", key + "_yoy", "divide", [delta, prior], "percent_change", 100))
    result = dict(
        schema_version="entity_quantitative_v1",
        entity_key=package["entity_key"],
        period_id=package["period_id"],
        package_id=package["package_id"],
        evidence_fingerprint=package["evidence_fingerprint"],
        nodes=nodes,
        status="validated",
    )
    return dict(result, calculation_fingerprint=digest(result))


def validate(draft, package, calculations):
    from .analyst import TYPES, lineage

    if (
        draft.get("schema_version") != "entity_analyst_v1"
        or draft.get("state") != "draft"
        or draft.get("source_profile") != PROFILE
    ):
        raise ValueError("Unexpected compact entity draft")
    for key in ("entity_key", "period_id", "package_id", "evidence_fingerprint"):
        if draft.get(key) != package[key]:
            raise ValueError("Issuer draft identity differs")
    expected_metadata = dict(
        period_label=f"{package['period_id'][-1]}T{package['period_id'][2:4]}",
        cutoff_date=package["cutoff_date"],
        guidance_as_of=package["report_date"],
        selection_mode=package["selection_mode"],
    )
    if any(draft.get(key) != value for key, value in expected_metadata.items()):
        raise ValueError("Issuer public metadata differs from verified evidence")
    if any(
        calculations.get(key) != package[key]
        for key in ("entity_key", "period_id", "package_id", "evidence_fingerprint")
    ):
        raise ValueError("Issuer calculation input identity differs")
    if (
        calculations.get("status") != "validated"
        or draft.get("calculation_fingerprint") != calculations["calculation_fingerprint"]
    ):
        raise ValueError("Issuer calculation identity differs")
    if draft.get("reader_private_section_keys") or draft.get("context_claim_ids"):
        raise ValueError("Compact issuer profile cannot hide or duplicate public claims")
    if draft.get("summary_format", "paragraphs") != "paragraphs":
        raise ValueError("Compact issuer summary format is paragraphs")
    if (
        draft.get("language") != "es-MX"
        or draft.get("model") is None
        and not draft.get("model_unavailable_reason")
    ):
        raise ValueError("Missing language or model provenance")
    nodes = {n["calculation_id"]: n for n in calculations["nodes"]}
    excerpts = {e["excerpt_id"]: e for e in package["excerpts"]}
    rendered = {}
    for claim in draft["claims"]:
        cid = claim["claim_id"]
        if cid in rendered or not re.fullmatch(r"[a-z][a-z0-9_]*", cid) or claim["type"] not in TYPES:
            raise ValueError("Duplicate/invalid issuer claim")
        text = claim["text_template"]
        if re.search(r"\d|[{}]", TOKEN.sub("", text)) or set(TOKEN.findall(text)) != set(claim["bindings"]):
            raise ValueError("Unbound number in issuer prose")
        if not claim.get("confidence_reason") or not (
            claim.get("evidence_ids") or claim.get("bindings") or claim.get("support_calculation_ids")
        ):
            raise ValueError("Claim requires explicit support")
        if not set(claim["evidence_ids"]) <= set(excerpts):
            raise ValueError("Unknown source excerpt")
        for alias, binding in claim["bindings"].items():
            n = nodes[binding["calculation_id"]]
            if (
                not math.isfinite(n["value"])
                or binding["unit"] != n["unit"]
                or binding["period_id"] != n["period_id"]
            ):
                raise ValueError("Invalid unit, period or value")
            lineage(n["calculation_id"], package, calculations)
            text = text.replace("{{" + alias + "}}", n["formatted_value"])
        for key in claim.get("support_calculation_ids", []):
            lineage(key, package, calculations)
        for span in claim.get("support_spans", []):
            if (
                span["excerpt_id"] not in claim["evidence_ids"]
                or not span["text"].strip()
                or span["text"] not in excerpts[span["excerpt_id"]]["text"]
            ):
                raise ValueError("Unsupported literal attribution")
        if claim["type"] == "company_attribution" and not claim.get("support_spans"):
            raise ValueError("Company explanation needs a literal source span")
        if claim["type"] == "hypothesis" and not claim.get("limitations"):
            raise ValueError("Interpretation requires limitations")
        lead = claim.get("lead", "")
        if lead and (not text.startswith(lead) or re.search(r"[<>]", lead)):
            raise ValueError("Claim lead must be an exact supported prefix")
        for phrase in claim.get("emphasis", []):
            if not phrase or text.count(phrase) != 1 or re.search(r"[<>]", phrase):
                raise ValueError("Claim emphasis must be an exact supported span")
        rendered[cid] = text
    placements = [draft["thesis_claim_id"], *draft["summary_claim_ids"]]
    for section in draft["sections"]:
        if not section["claim_ids"] or re.search(r"\d|[{}]", section["title"]):
            raise ValueError("Invalid compact section")
        placements += section["claim_ids"]
    if len(placements) != len(set(placements)) or set(placements) != set(rendered):
        raise ValueError("Claims must appear exactly once")
    words = sum(len(rendered[c].split()) for c in placements if c != draft["thesis_claim_id"])
    if not 200 <= words <= 300:
        raise ValueError(f"Compact issuer thesis outside 200–300 words: {words}")
    return dict(
        status="passed",
        analysis_state="draft",
        claims=len(rendered),
        rendered=rendered,
        summary_words=sum(len(rendered[c].split()) for c in draft["summary_claim_ids"]),
        detail_words=sum(len(rendered[c].split()) for s in draft["sections"] for c in s["claim_ids"]),
        total_words=words,
    )


def verified_inputs(record):
    d = record["draft"]
    entity, period = d.get("entity_key"), d.get("period_id")
    if (
        entity not in ENTITIES
        or period != "2026Q3"
        or not re.fullmatch(f"{entity}_{period}_[a-f0-9]{{64}}", d.get("package_id", ""))
        or not re.fullmatch(r"[a-f0-9]{64}", d.get("calculation_fingerprint", ""))
    ):
        raise ValueError("Invalid issuer input identity")
    package = read(PATHS.root / "analysis_runs/evidence" / (d["package_id"] + ".json"))
    calculations = read(PATHS.root / "analysis_runs/quantitative" / (d["calculation_fingerprint"] + ".json"))
    if calculate(package) != calculations:
        raise ValueError("Issuer calculation replay changed")
    return package, calculations, validate(d, package, calculations)


def import_draft(package, draft):
    from .analyst import SKILL
    from .entity_adapter import code_version, sha

    calculate_result = calculate(package)
    checks = validate(draft, package, calculate_result)
    record = dict(
        draft=draft, prompt_version=sha(SKILL), code_version=code_version(), content_hash=digest(draft)
    )
    record["version"] = digest({k: record[k] for k in ("draft", "prompt_version", "code_version")})
    record.update(
        analysis_id=f"{draft['entity_key']}_{draft['period_id']}_{record['version']}",
        created_at=datetime.now(timezone.utc).isoformat(),
        mechanical_checks={k: v for k, v in checks.items() if k != "rendered"},
    )
    path = (
        PATHS.root
        / "analysis_runs/drafts"
        / draft["entity_key"]
        / draft["period_id"]
        / (record["version"] + ".json")
    )
    if not path.exists():
        immutable(path, record)
    else:
        from .lifecycle_identity import verify_record

        verify_record(read(path))
        verified_inputs(read(path))
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["prepare", "import-draft"])
    p.add_argument("--entity", choices=sorted(ENTITIES))
    p.add_argument("--workspace", type=Path)
    p.add_argument("--retention")
    p.add_argument("--as-of")
    p.add_argument("--package", type=Path)
    p.add_argument("--input", type=Path)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.mode == "prepare":
        package = package_for(a.workspace, a.entity, "2026Q3", a.retention, a.as_of)
        calculations = calculate(package)
        immutable(PATHS.root / "analysis_runs/evidence" / (package["package_id"] + ".json"), package)
        immutable(
            PATHS.root / "analysis_runs/quantitative" / (calculations["calculation_fingerprint"] + ".json"),
            calculations,
        )
        immutable(a.output, dict(package=package, calculations=calculations))
    else:
        path = import_draft(read(a.package), read(a.input))
        immutable(
            a.output,
            dict(
                record_path=str(path),
                record_sha256=__import__("hashlib").sha256(path.read_bytes()).hexdigest(),
            ),
        )


if __name__ == "__main__":
    main()
