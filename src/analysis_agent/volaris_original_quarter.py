"""Freeze and replay original Volaris SEC Q3 sources, with no approval effects."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from src.config import PATHS
from src.pipeline.offline import block_network
from src.source_updates.volaris_q3_original import document_receipts, native_frame, originals, sha

from .evidence import digest

PROFILE = "volaris_original_quarter_v1"


def package_for(workspace):
    from src.source_updates.carrier_source_contract import identifier

    from .analyst import formatted
    from .issuer_quarter import NOTES, SPECS, UNITS

    workspace = Path(workspace).resolve()
    with block_network():
        inputs = originals(workspace)
        frame, details = native_frame(inputs)
    frame["record_id"] = frame.apply(identifier, axis=1)
    sources, excerpts, metrics = [], [], []
    for role, (raw, meta) in inputs.items():
        sources.append(
            dict(
                artifact_id="art_" + meta["sha256"],
                source_file=meta["source_file"],
                source_url=meta["source_url"],
                artifact_sha256=sha(raw),
                captured_at=meta["downloaded_at"],
                publication_basis="Original SEC HTTP response retained at the actual capture time",
                role=role,
            )
        )
    for key, (statement, name, segment) in SPECS["VOLARIS"].items():
        for year in (2026, 2025):
            selected = frame[
                frame.statement.eq(statement)
                & frame.metric_key.eq(name)
                & frame.segment.eq(segment)
                & frame.period_type.eq("quarter")
                & frame.period_id.eq(f"{year}Q3")
            ]
            if len(selected) != 1:
                raise ValueError("Original SEC metric is missing or ambiguous")
            row = next(selected.itertuples())
            excerpt = dict(
                artifact_id="art_" + row.source_hash,
                locator=row.source_locator,
                text=row.source_excerpt,
                period_id=f"{year}Q3",
                source_content_is_untrusted=True,
            )
            excerpt["excerpt_id"] = "exc_" + digest(excerpt)
            if excerpt not in excerpts:
                excerpts.append(excerpt)
            unit = "fraction" if row.unit == "percent" else UNITS.get(row.unit, row.unit)
            metric = dict(
                metric_key=key,
                value=float(Decimal(str(row.value)) * Decimal(str(row.scale))),
                unit=unit,
                period_id=f"{year}Q3",
                artifact_id=excerpt["artifact_id"],
                excerpt_id=excerpt["excerpt_id"],
                definition=row.metric_key,
                scope=row.segment,
                source_record_id=row.record_id,
                record_id=row.record_id,
            )
            metric["formatted_value"] = formatted(
                {**metric, "formatted_value": str(metric["value"])}, business=True
            )
            metric["metric_id"] = "metric_" + digest(metric)
            metrics.append(metric)
    base = dict(
        schema_version="entity_evidence_v1",
        source_profile=PROFILE,
        entity_key="VOLARIS",
        period_id="2026Q3",
        cutoff_date=max(m["downloaded_at"][:10] for _, m in inputs.values()),
        report_date="2026-10-26",
        workspace=workspace.relative_to(PATHS.root).as_posix(),
        capture_sha256=sha((workspace / "capture.json").read_bytes()),
        document_checks=document_receipts(inputs),
        sources=sources,
        excerpts=excerpts,
        metrics=metrics,
        source_checks={
            k: details[k]
            for k in (
                "reconciliations_passed",
                "numeric_warning_count",
                "unresolved_dash_observations",
                "no_dash_imputed_as_zero",
            )
        },
        selection_mode="retrospective_source_edition",
        public_notes=NOTES
        + [
            "Original SEC HTTP responses captured and hashed; "
            "SEC's empty transport script is checked separately from indexed document size."
        ],
    )
    fingerprint = digest(base)
    return dict(base, evidence_fingerprint=fingerprint, package_id=f"VOLARIS_2026Q3_{fingerprint}")


def verify(package):
    if package.get("source_profile") != PROFILE or package_for(PATHS.root / package["workspace"]) != package:
        raise ValueError("Original SEC frozen package replay differs")


def calculate(package):
    from .issuer_quarter import calculate_verified

    verify(package)
    return calculate_verified(package)
