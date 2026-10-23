"""Physical baseline checks; synthetic source amounts and isolated scratch only."""

from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import openpyxl
import pandas as pd
import pytest

from src.source_updates.carrier_source_candidate import run
from src.source_updates.carrier_source_inputs import retain
from tests.test_source_update_carrier_independent import retained_sources as shared_sources
from tests.test_source_update_carrier_independent import synthetic_afac

retained_sources = shared_sources
CUTOFF = "2026-10-23T16:00:00-06:00"
BASELINE = "baselines/prior/data/silver/afac_carriers_source_native.parquet"


def physical_pair(retained_sources, *, future=False):
    synthetic_afac(retained_sources)
    root, original, records = retained_sources
    candidate = root / "candidate"
    saved = retain(
        candidate, original, "afac_carriers", {k: r["source_file"] for k, r in records.items()}, execute=True
    )
    prior_root = root / "prior-original"
    prior_root.mkdir()
    rows = copy.deepcopy(records)
    for role, row in rows.items():
        body = (original / row["source_file"]).read_bytes()
        if role == "database":
            with ZipFile(io.BytesIO(body)) as z:
                book = openpyxl.load_workbook(io.BytesIO(z.read("DB_AFAC.xlsx")))
            sheet = book["AFAC"]
            found = next(
                r
                for r in sheet.iter_rows(min_row=2)
                if r[0].value == 2024 and r[2].value == "Fletamento" and r[5].value == 1
            )
            found[7].value += 1
            output = io.BytesIO()
            book.save(output)
            archived = io.BytesIO()
            with ZipFile(archived, "w") as z:
                z.writestr("DB_AFAC.xlsx", output.getvalue())
            body = archived.getvalue()
        if future:
            row["downloaded_at"] = "2026-10-24T12:00:00+00:00"
        row.update(sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
        p = prior_root / row["source_file"]
        p.write_bytes(body)
        Path(str(p) + ".meta.json").write_text(json.dumps(row))
    (prior_root / "_manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows.values()))
    prior = candidate / "baselines/prior"
    kept = retain(
        prior, prior_root, "afac_carriers", {k: r["source_file"] for k, r in rows.items()}, execute=True
    )
    if future:
        path = prior / "receipts" / f"retained-{kept['run_id']}.json"
        receipt = json.loads(path.read_text())
        receipt["retained_at"] = "2026-10-25T12:00:00+00:00"
        path.write_text(json.dumps(receipt))
    prior_cutoff = "2026-10-26T16:00:00-06:00" if future else CUTOFF
    run(prior, "afac_carriers", "2026M08", prior_cutoff, kept["run_id"], execute=True)
    return candidate, saved, prior


def test_physical_baseline_detects_historical_revision_and_preserves_current_month(retained_sources):
    candidate, saved, prior = physical_pair(retained_sources)
    args = (candidate, "afac_carriers", "2026M08", CUTOFF, saved["run_id"])
    result = run(*args, execute=True, baseline=BASELINE)
    revisions = result["revisions"]
    assert revisions["changed"] == 1 and revisions["added"] == revisions["removed"] == 0
    assert revisions["baseline_table"] == "silver/afac_carriers_source_native"
    fields = ["entity_as_reported", "period_id", "service_type", "segment", "value", "unit"]
    current = pd.read_parquet(candidate / "data/gold/fact_afac_carrier_source.parquet")[fields]
    before = pd.read_parquet(prior / "data/gold/fact_afac_carrier_source.parquet")[fields]
    pd.testing.assert_frame_equal(
        current.sort_values(fields).reset_index(drop=True), before.sort_values(fields).reset_index(drop=True)
    )
    assert run(*args, check=True)["output_sha256"] == result["output_sha256"]


@pytest.mark.parametrize("change", ["native_only", "body", "retention_flags"])
def test_baseline_requires_native_and_physical_source_to_agree(retained_sources, change):
    candidate, saved, prior = physical_pair(retained_sources)
    if change == "native_only":
        path = prior / "data/silver/afac_carriers_source_native.parquet"
        frame = pd.read_parquet(path)
        row = frame.index[frame.service_type.eq("charter")][0]
        frame.loc[row, "value"] += 2
        frame.loc[row, "source_value"] = str(int(frame.loc[row, "value"]))
        frame.to_parquet(path, index=False)
    elif change == "body":
        path = prior / "data/bronze/database.zip"
        path.write_bytes(path.read_bytes() + b"altered")
    else:
        path = next((prior / "receipts").glob("retained-*.json"))
        receipt = json.loads(path.read_text())
        receipt["paid_requests"] = 1
        path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        run(candidate, "afac_carriers", "2026M08", CUTOFF, saved["run_id"], execute=True, baseline=BASELINE)
    assert not (candidate / "data/gold").exists()


def test_baseline_source_captured_after_current_cutoff_is_not_historical_evidence(retained_sources):
    candidate, saved, _ = physical_pair(retained_sources, future=True)
    with pytest.raises(ValueError):
        run(candidate, "afac_carriers", "2026M08", CUTOFF, saved["run_id"], execute=True, baseline=BASELINE)
    assert not (candidate / "data/gold").exists()


def test_global_release_binding_uses_financial_exhibit_only_and_keeps_support_lineage(retained_sources):
    from src.source_updates import global_readiness
    from tests.test_source_update_carrier import synthetic_volaris

    root = retained_sources[0]
    original = root / "volaris-original"
    original.mkdir()
    records = {}
    for role, (body, source) in synthetic_volaris().items():
        row = {
            **source,
            "bytes": len(body),
            "http_status": 200,
            "logical_version": 1,
            "filename_version": 1,
            "download_method": "synthetic_offline_fixture",
            "content_type": "application/json" if role in {"index", "submissions"} else "text/html",
            "logical_key": f"sec|synthetic_{role}|2026Q2|{Path(source['source_file']).suffix[1:]}",
        }
        path = original / row["source_file"]
        path.write_bytes(body)
        Path(str(path) + ".meta.json").write_text(json.dumps(row))
        records[role] = row
    (original / "_manifest.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records.values()))
    candidate = root / "volaris-candidate"
    saved = retain(
        candidate, original, "volaris_sec", {k: r["source_file"] for k, r in records.items()}, execute=True
    )
    run(candidate, "volaris_sec", "2026Q2", CUTOFF, saved["run_id"], execute=True)
    task = dict(
        id="volaris",
        product="volaris_sec",
        period="2026Q2",
        adapter="carrier_source",
        workspace=str(candidate),
        receipt_id=saved["run_id"],
        candidate_as_of=CUTOFF,
        cadence="quarterly",
        used=True,
        depends_on=[],
    )
    result = global_readiness.verify(task, root / "global")

    def identity(role):
        return {"source_url": records[role]["source_url"], "sha256": records[role]["sha256"]}

    assert result["financial_report_artifacts"] == [identity("html")]
    assert {json.dumps(r, sort_keys=True) for r in result["contributing_artifacts"]} == {
        json.dumps(identity(role), sort_keys=True) for role in records
    }
    for role in records:
        release = dict(
            entity="VOLARIS",
            period="2026Q2",
            kind="financial_report",
            confirmed=True,
            published_at="2026-07-21T21:30:26Z",
            document_url=records[role]["source_url"],
            source_sha256=records[role]["sha256"],
            task_id="volaris",
        )
        recipe = dict(
            version=1,
            round="quarterly",
            as_of=CUTOFF,
            monthly_period="2026M09",
            quarterly_period="2026Q2",
            items=[task],
            releases=[release],
        )
        checked = global_readiness.evaluate(recipe, {"volaris": result})
        blocked = (
            "VOLARIS:release_not_bound_to_verified_contributing_artifact" in checked["calendar_blockers"]
        )
        assert blocked is (role != "html")
        assert checked["ready_for_calendar_incorporation"] is False
