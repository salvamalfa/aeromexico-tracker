"""Add one audited quarterly release without rebuilding monthly datasets.

Existing theses are fully revalidated with their original implementation;
the new thesis uses the current lifecycle, with a passing independent audit
and exact-version authorization. Both are rechecked under lock before swap.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

from src.config import PATHS
from src.analysis_agent.quarterly_release import PERIOD, calculate, verify
from . import manifest as manifests
from .approval_cohorts import verify_approval_cohorts
from .frozen_data import data_identities
from .verify import verify_site


def executive_projection(baseline, package):
    """Append Aeromexico only; preserve every prior record/view and peer block."""
    from src.dashboard.executive_summary import _period_view

    verify(package)
    nodes = {n["key"]: n["value"] for n in calculate(package)["nodes"] if n["period_id"] == PERIOD}
    document = copy.deepcopy(baseline)
    if PERIOD in document["views"] or any(r["period_id"] == PERIOD for r in document["records"]):
        raise ValueError("Quarterly release must add an absent financial period")
    record = dict(
        period_id=PERIOD,
        period_label="3T26",
        passengers=nodes["passengers"],
        ask_km=nodes["ask"],
        load_factor_reported=nodes["load"],
        rask_cents_per_km=nodes["rask"],
        cask_cents_per_km=nodes["cask"],
        unit_margin_cents_per_km=nodes["spread"],
    )
    prior = {r["period_id"]: r for r in document["records"]}
    view = _period_view(record, prior)
    # Printed native unit KPIs are converted by one exact distance factor.
    # Preserve the distinction from financial operating margin and statement cost.
    note = (
        "Fuente: reporte financiero no auditado 3T26, publicado el 19 oct 2026. "
        "TRASM/CASM reportados por asiento-milla, convertidos a asiento-kilómetro con 1.609344. "
        "Cifras redondeadas; el costo unitario publicado conserva su definición y no se iguala "
        "a gastos del estado de resultados. Las comparaciones calculadas pueden diferir de las "
        "variaciones publicadas. El mapa de vuelos conserva sus propios cortes mensuales."
    )
    view["narrative"] = {"headline": "Ingresos récord, margen bajo presión", "paragraphs": [note]}
    document["records"].append(record)
    document["views"][PERIOD] = view
    block = document["entities"]["AEROMEXICO"]
    entity_record = {
        **record,
        "load_factor": record["load_factor_reported"],
        "load_factor_basis": "reported",
        "rpk_km": nodes["rpm"] * 1.609344,
        "cask_ex_fuel_cents_per_km": nodes["casm_ex"] / 1.609344,
    }
    del entity_record["load_factor_reported"]
    block["records"].append(entity_record)
    block["views"][PERIOD] = copy.deepcopy(view)
    block["last_period"] = PERIOD
    block["quarter_count"] = len(block["records"])
    block["note"] += " " + note
    metadata = document["metadata"]
    metadata.update(
        default_period=PERIOD,
        last_period=PERIOD,
        quarter_count=len(document["records"]),
        coverage_label="23 trimestres de Aeroméxico · 1T21–3T26",
        data_as_of="21 oct 2026",
    )
    metadata["source_view"] += " + reporte financiero 3T26 verificado"
    metadata["method_note"] += " " + note
    # The existing correlation describes the frozen historical sample; do not
    # silently relabel it as a recalculation over an expanded series.
    metadata["load_rask_interpretation"] += " Cálculo histórico conservado hasta 2T26."
    return document


def require_preserved_data(candidate, baseline, new_executive, new_analysis, analysis_path):
    before = data_identities(baseline, flights=True)
    after = data_identities(candidate, flights=True)
    changed = {"data/v1/executive.json", analysis_path}
    if set(after) != set(before) | {analysis_path}:
        raise ValueError("Quarterly publication added or removed unrelated datasets")
    if any(after[p] != identity for p, identity in before.items() if p not in changed):
        raise ValueError("Quarterly publication changed a frozen published dataset")
    if json.loads((candidate / "data/v1/executive.json").read_bytes()) != new_executive:
        raise ValueError("Quarterly executive projection differs from verified evidence")
    if json.loads((candidate / analysis_path).read_bytes()) != new_analysis:
        raise ValueError("Quarterly thesis differs from its approved consumer payload")


def publish_quarterly(record_paths: list[Path], out_dir: Path):
    from . import gate

    manifests.refuse_if_build_inputs_dirty()
    records = gate.load_records(record_paths)
    new = [r for r in records if r["draft"].get("source_profile") == "quarterly_release_v1"]
    if len(new) != 1 or new[0]["draft"]["period_id"] != PERIOD:
        raise gate.PublicationRefused("One approved Aeromexico 3Q26 quarterly record is required")
    baseline = PATHS.root / "site"
    out_dir = Path(out_dir).resolve()
    commit = gate._trusted_site_commit(PATHS.root)
    gate.require_trusted_site_baseline(baseline, trusted_commit=commit)
    problems = verify_site(baseline)
    if problems:
        raise gate.PublicationRefused(f"Invalid baseline: {problems[:3]}")
    expected = manifests.load_manifest(baseline)
    root = gate.flow.ROOT

    def verified():
        current = gate._verify_under_lock(new, root)[0]
        if current[2].get("schema_version") != "quarterly_release_v1":
            raise ValueError("Quarterly draft is not bound to the primary-source edition")
        payload = gate._analysis_payload(*current)
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        current_entry = gate._analysis_manifest_entry(current[1])
        pending = {
            "entry": current_entry,
            "bytes": raw,
            "file": {
                "path": "data/v1/" + manifests.analysis_relative_path(current_entry).as_posix(),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
            },
        }
        cohorts = verify_approval_cohorts(record_paths, PATHS.root, commit, expected, root, pending=pending)
        prior = [
            (a, p)
            for a, p in zip(cohorts["authorized"], cohorts["payloads"])
            if gate._analysis_manifest_entry(a) != current_entry
        ]
        entries = [gate._analysis_manifest_entry(a) for a, _ in prior]
        if sorted(entries, key=manifests.analysis_sort_key) != expected["analysis_manifest"]:
            raise ValueError("Existing thesis identities differ from the trusted publication")
        for entry, (_, payload) in zip(entries, prior):
            path = baseline / "data/v1" / manifests.analysis_relative_path(entry)
            if json.loads(path.read_bytes()) != payload:
                raise ValueError("Existing thesis bytes differ from their authorized payload")
        return cohorts, current

    with gate.flow.writer(root):
        cohorts, entry = verified()
    analysis = gate._analysis_payload(*entry)
    new_entry = gate._analysis_manifest_entry(entry[1])
    analysis_path = "data/v1/" + manifests.analysis_relative_path(new_entry).as_posix()
    if (baseline / analysis_path).exists():
        raise gate.PublicationRefused("This financial quarter already has a published thesis")
    executive = executive_projection(json.loads((baseline / "data/v1/executive.json").read_bytes()), entry[2])
    web = gate.WEB_DATA_V1
    if web.exists():
        shutil.rmtree(web)
    shutil.copytree(baseline / "data/v1", web)
    (web / "executive.json").write_text(
        json.dumps(executive, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    target = web / manifests.analysis_relative_path(new_entry)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(analysis, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    dist = gate.build_web(gate.WEB_DIR)
    require_preserved_data(dist, baseline, executive, analysis, analysis_path)
    manifest_entries = sorted([*expected["analysis_manifest"], new_entry], key=manifests.analysis_sort_key)

    def validate(candidate):
        require_preserved_data(candidate, baseline, executive, analysis, analysis_path)
        problems = verify_site(candidate)
        if problems:
            raise ValueError(f"Quarterly candidate failed verification: {problems[:3]}")

    with gate.flow.writer(root):
        gate.require_trusted_site_baseline(baseline, trusted_commit=commit)
        final_cohorts, final_entry = verified()
        if final_cohorts != cohorts or final_entry != entry:
            raise gate.PublicationRefused("An approval or source changed during the build")
        manifest = gate.assemble_site(dist, manifest_entries, out_dir, validate_candidate=validate)
    receipt = gate.write_receipt(manifest, cohorts["authorized"], out_dir)
    return {"manifest": manifest, "receipt": receipt}
