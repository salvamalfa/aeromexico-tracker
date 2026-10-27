"""Synthetic physical review contracts, not actual issuer release assertions."""

import copy
import hashlib
import json
import shutil
from datetime import date
from uuid import uuid4

import pytest

from src.source_updates import calendar
from src.source_updates import global_readiness as gate
from src.source_updates.catalog import ROOT


@pytest.fixture
def holidays():
    return json.loads((ROOT / "config/source_update_holidays.json").read_text())


@pytest.fixture
def workflow_workspace():
    path = ROOT / "tmp/source-updates" / ("pragmatic-flow-" + uuid4().hex)
    yield path
    if path.exists():
        shutil.rmtree(path)


def release(entity="AEROMEXICO", day="2026-10-30"):
    return dict(
        entity=entity,
        period="2026Q3",
        kind="financial_report",
        confirmed=True,
        published_at=None,
        publication_precision="day",
        published_on=day,
        document_url="https://ir.aeromexico.com/synthetic-report.html",
        source_sha256="a" * 64,
        task_id="quarterly_am_financials",
    )


def test_day_stays_day_and_crosses_bank_holiday(holidays):
    rows = [release(entity) for entity in calendar.CENTRAL]
    before = copy.deepcopy(rows)
    assert calendar.quarterly("2026Q3", rows, "2026-10-31T08:00:00-06:00", holidays)["date"] == "2026-11-04"
    assert rows == before and all(row["published_at"] is None for row in rows)
    assert calendar.report_day(rows[0], "2026-10-30T01:00:00-06:00") == date(2026, 10, 30)


@pytest.mark.parametrize(
    "defect", ["malformed", "future", "both", "no_precision", "wrong_kind", "quarter_end", "wrong_quarter"]
)
def test_invalid_release_never_dates_complete_round(holidays, defect):
    rows = [release(entity) for entity in sorted(calendar.CENTRAL)]
    changes = {
        "malformed": dict(published_on="2026-10-3"),
        "future": dict(published_on="2026-11-01"),
        "both": dict(published_at="2026-10-30T00:00:00-06:00"),
        "no_precision": dict(publication_precision="timestamp"),
        "wrong_kind": dict(kind="earnings_call"),
        "quarter_end": dict(published_on="2026-09-30"),
        "wrong_quarter": dict(period="2026Q2"),
    }
    rows[0].update(changes[defect])
    assert calendar.quarterly("2026Q3", rows, "2026-10-31T08:00:00-06:00", holidays)["date"] is None


def test_day_precision_cannot_supply_unverified_year(holidays):
    rows = [dict(release(entity, "2027-01-20"), period="2026Q4") for entity in calendar.CENTRAL]
    with pytest.raises(ValueError, match="Unverified banking calendar for 2027"):
        calendar.quarterly("2026Q4", rows, "2027-01-21T08:00:00-06:00", holidays)


def recipe(kind="monthly"):
    items = [
        dict(
            id=f"{kind}_{product}",
            product=product,
            cadence=kind,
            period="2026M09" if kind == "monthly" else "2026Q3",
            used=True,
            depends_on=[],
            adapter="series" if product in {"banxico", "fuel", "equities"} else "unsupported",
            workspace=f"tmp/source-updates/pragmatic-test-{kind}-{product}",
            receipt_id="a" * 32,
            candidate_as_of="2026-10-31T08:00:00-06:00",
        )
        for product in sorted(gate.REQUIRED[kind])
    ]
    return dict(
        version=1,
        round=kind,
        as_of="2026-10-31T08:00:00-06:00",
        monthly_period="2026M09",
        quarterly_period="2026Q3",
        items=items,
        releases=[],
    )


def outcomes(value):
    return {
        item["id"]: dict(
            status="checks_passed",
            source_conditions=[],
            latest_source_availability_verified=True,
            semantic_acceptance_verified=True,
        )
        for item in value["items"]
    }


@pytest.mark.parametrize("product", ["banxico", "fuel"])
def test_observed_macro_is_warning_but_source_stays_required(product):
    value = recipe()
    results = outcomes(value)
    result = results[f"monthly_{product}"]
    result.update(
        scope=gate.OBSERVED_SERIES_SCOPE,
        calendar_completeness_certified=False,
        source_conditions=["publication_calendar_completeness_not_verified"],
    )
    decision = gate.evaluate(value, results)
    assert decision["core_ready"] and decision["requested_bundle_ready"]
    assert decision["calendar_blockers"] == [
        "quarterly:aerocivil:required_calendar_prerequisite_not_verified"
    ]
    assert decision["coverage_warnings"] == [
        f"monthly_{product}:observation_calendar_completeness_not_verified"
    ]
    assert result["calendar_completeness_certified"] is False
    value["items"] = [item for item in value["items"] if item["product"] != product]
    assert not gate.evaluate(value, results)["core_ready"]


@pytest.mark.parametrize(
    "defect", ["equities", "wrong_scope", "wrong_adapter", "missing_month", "bad_physical", "not_current"]
)
def test_exemption_never_covers_different_contract_or_bad_checks(defect):
    value = recipe()
    results = outcomes(value)
    product = "equities" if defect == "equities" else "fuel"
    item = next(i for i in value["items"] if i["product"] == product)
    result = results[item["id"]]
    result.update(
        scope=gate.OBSERVED_SERIES_SCOPE, source_conditions=["publication_calendar_completeness_not_verified"]
    )
    if defect == "wrong_scope":
        result["scope"] = "complete_period"
    elif defect == "wrong_adapter":
        item["adapter"] = "unsupported"
    elif defect in {"missing_month", "bad_physical"}:
        result.update(status="blocked", reason=defect)
    elif defect == "not_current":
        result["latest_source_availability_verified"] = False
    decision = gate.evaluate(value, results)
    assert not decision["ready_for_calendar_incorporation"]
    if defect != "not_current":
        assert f"{item['id']}:observation_calendar_completeness_not_verified" in decision["calendar_blockers"]
    else:
        assert f"{item['id']}:current_source_availability_not_verified" in decision["calendar_blockers"]
    if defect in {"missing_month", "bad_physical"}:
        assert not decision["core_ready"]


def physical_release(tmp_path, entity="AEROMEXICO"):
    row = release(entity)
    product, alias, url = {
        "AEROMEXICO": ("am_financials", "aeromexico_ir", "https://ir.aeromexico.com/synthetic-report.html"),
        "VOLARIS": (
            "volaris_sec",
            "sec",
            "https://www.sec.gov/Archives/edgar/data/1520504/synthetic/report.htm",
        ),
        "VIVA_AEROBUS": ("viva_financials", "viva_ir", "https://cdn.investorcloud.net/synthetic-report.html"),
    }[entity]
    root = tmp_path / entity
    root.mkdir()
    body = f"<html><body>{entity} 2026Q3 2026-10-30 Financial report</body></html>".encode()
    source = dict(
        source_file="report.html",
        source_system=alias,
        source_url=url,
        sha256=hashlib.sha256(body).hexdigest(),
        bytes=len(body),
        downloaded_at="2026-10-30T17:00:00-06:00",
        http_status=200,
    )
    (root / "report.html").write_bytes(body)
    (root / "report.html.meta.json").write_text(json.dumps(source))
    (root / "_manifest.jsonl").write_text(json.dumps(source) + "\n")
    row.update(document_url=url, source_sha256=source["sha256"], task_id=f"quarterly_{product}")
    row["documentary_evidence"] = dict(
        bronze_root=str(root),
        source=source,
        passages={
            key: dict(value=row[key], locator=dict(html_xpath="/html/body"), excerpt=row[key])
            for key in ("entity", "period", "published_on")
        },
    )
    return row


def test_physical_review_does_not_need_or_confer_numeric_completion(tmp_path):
    value = recipe("quarterly")
    value["releases"] = [physical_release(tmp_path, entity) for entity in sorted(calendar.CENTRAL)]
    results = outcomes(value)
    for row in value["releases"]:
        proof = calendar.verify_report_evidence(row, value["as_of"])
        assert proof["published_at"] is None
        results[row["task_id"]] = dict(
            status="blocked", reason="numeric_ingestion_pending", documentary_releases=[proof]
        )
    decision = gate.evaluate(value, results)
    assert decision["quarterly_date"] == "2026-11-04"
    assert not decision["core_ready"] and not decision["ready_for_calendar_incorporation"]
    assert not any("missing_verified_central_reports" in s for s in decision["calendar_blockers"])


@pytest.mark.parametrize(
    "defect", ["issuer", "quarter", "day", "hash", "tamper", "future_capture", "http", "wrong_cik", "passage"]
)
def test_documentary_review_rejects_unbound_evidence(tmp_path, defect):
    row = physical_release(tmp_path, "VOLARIS" if defect == "wrong_cik" else "AEROMEXICO")
    evidence = row["documentary_evidence"]
    if defect == "issuer":
        row["entity"] = "VIVA_AEROBUS"
    elif defect == "quarter":
        row["period"] = "2026Q2"
    elif defect == "day":
        row["published_on"] = "2026-10-29"
    elif defect == "hash":
        row["source_sha256"] = "f" * 64
    elif defect == "tamper":
        (tmp_path / "AEROMEXICO/report.html").write_text("corrupt")
    elif defect == "future_capture":
        evidence["source"]["downloaded_at"] = "2026-11-01T00:00:00-06:00"
    elif defect == "http":
        evidence["source"]["http_status"] = 503
    elif defect == "wrong_cik":
        evidence["source"]["source_url"] = row["document_url"] = (
            "https://www.sec.gov/Archives/edgar/data/1/report.htm"
        )
    else:
        evidence["passages"]["period"]["excerpt"] = "not present"
    with pytest.raises(ValueError):
        calendar.verify_report_evidence(row, "2026-10-31T08:00:00-06:00")


def test_numeric_warning_is_visible_without_changing_numbers_or_readiness():
    value = recipe()
    results = outcomes(value)
    warning = dict(
        numeric_warnings=[{"metric": "casm", "reported": 7.97}],
        numeric_warning_count=1,
        numeric_check_status="passed_with_warning",
        numeric_policy_id="fixture_policy",
    )
    results["monthly_bts_segments"].update(warning)
    decision = gate.evaluate(value, results)
    assert decision["numeric_warnings"] == {"monthly_bts_segments": warning}
    assert decision["core_ready"]


def test_invalid_additional_review_cannot_borrow_numeric_artifact_binding(tmp_path):
    value = recipe("quarterly")
    value["releases"] = [physical_release(tmp_path, entity) for entity in sorted(calendar.CENTRAL)]
    results = outcomes(value)
    for row in value["releases"]:
        identity = dict(source_url=row["document_url"], sha256=row["source_sha256"])
        results[row["task_id"]].update(
            contributing_artifacts=[identity], financial_report_artifacts=[identity]
        )
    assert gate.evaluate(value, results)["quarterly_date"] is None


def test_documentary_flow_survives_failed_numeric_checker_and_exact_replay(
    tmp_path, monkeypatch, workflow_workspace
):
    value = recipe("quarterly")
    for item in value["items"]:
        item["adapter"] = "unsupported"
    value["releases"] = [physical_release(tmp_path, entity) for entity in sorted(calendar.CENTRAL)]
    # Workflow contract only: avoid concurrent runtime fingerprints from other agents.
    monkeypatch.setattr(gate, "fingerprints", lambda: {"fixture": "synthetic_not_source_proof"})
    workspace = workflow_workspace
    first = gate.execute(value, workspace, write=True)
    assert first["quarterly_date"] == "2026-11-04"
    assert not first["core_ready"] and first["status"] == "blocked_global_policy"
    assert all(first["results"][row["task_id"]]["documentary_releases"] for row in value["releases"])
    assert gate.execute(value, workspace, check=True)["quarterly_date"] == "2026-11-04"
    (tmp_path / "AEROMEXICO/report.html").write_text("changed")
    with pytest.raises(ValueError, match="replay differs"):
        gate.execute(value, workspace, check=True)


def test_documentary_date_is_not_limited_by_unfinished_candidate_cutoff(tmp_path):
    value = recipe("quarterly")
    value["releases"] = [physical_release(tmp_path, "AEROMEXICO")]
    for item in value["items"]:
        item["candidate_as_of"] = "2026-10-01T08:00:00-06:00"
    gate.preflight(value)
    assert (
        calendar.verify_report_evidence(value["releases"][0], value["as_of"])["published_on"] == "2026-10-30"
    )


def test_body_changed_after_initial_identity_check_is_rejected(tmp_path, monkeypatch):
    from src.source_updates import primary_review

    row = physical_release(tmp_path)
    real_original = primary_review.original

    def swapped(root, source):
        path = real_original(root, source)
        path.write_bytes(path.read_bytes().replace(b"2026Q3", b"2026Q2"))
        return path

    monkeypatch.setattr(primary_review, "original", swapped)
    with pytest.raises(ValueError, match="body changed before review"):
        calendar.verify_report_evidence(row, "2026-10-31T08:00:00-06:00")


def pdf_document(quarter):
    from io import BytesIO

    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
    )
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 12 Tf 50 700 Td (AEROMEXICO {quarter} 2026-10-30) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(stream)
    target = BytesIO()
    writer.write(target)
    return target.getvalue()


@pytest.mark.parametrize("kind", ["html", "pdf", "json"])
def test_swap_then_restore_cannot_supply_forged_passage(tmp_path, monkeypatch, kind):
    from src.source_updates import primary_review

    row = physical_release(tmp_path)
    root = tmp_path / "AEROMEXICO"
    source = row["documentary_evidence"]["source"]
    if kind == "pdf":
        body, forged = pdf_document("2026Q3"), pdf_document("2026Q2")
    elif kind == "json":
        content = dict(entity="AEROMEXICO", period="2026Q3", published_on="2026-10-30")
        body = json.dumps(content).encode()
        forged = json.dumps({**content, "period": "2026Q2"}).encode()
    else:
        body = (root / "report.html").read_bytes()
        forged = body.replace(b"2026Q3", b"2026Q2")
    source.update(sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
    row.update(source_sha256=source["sha256"], period="2026Q2")
    (root / "report.html").write_bytes(body)
    (root / "report.html.meta.json").write_text(json.dumps(source))
    (root / "_manifest.jsonl").write_text(json.dumps(source) + "\n")
    for key, passage in row["documentary_evidence"]["passages"].items():
        passage.update(value=row[key], excerpt=row[key])
        if kind == "pdf":
            passage["locator"] = dict(pdf_page_1based=1)
        elif kind == "json":
            passage["locator"] = dict(json_pointer="/" + key)
    real_verify = primary_review.verify_evidence

    def temporary_swap(passage, path, cache):
        if passage["value"] != "2026Q2":
            return real_verify(passage, path, cache)
        path.write_bytes(forged)
        try:
            return real_verify(passage, path, cache)
        finally:
            path.write_bytes(body)

    monkeypatch.setattr(primary_review, "verify_evidence", temporary_swap)
    with pytest.raises(ValueError, match="evidence .*mismatch"):
        calendar.verify_report_evidence(row, "2026-10-31T08:00:00-06:00")
    assert (root / "report.html").read_bytes() == body


@pytest.mark.parametrize("name", ["report.html.meta.json", "_manifest.jsonl"])
def test_acquisition_bytes_cannot_change_during_review(tmp_path, monkeypatch, name):
    from src.source_updates import primary_review

    row = physical_release(tmp_path)
    real_verify = primary_review.verify_evidence
    target = tmp_path / "AEROMEXICO" / name

    def changed_metadata(passage, path, cache):
        real_verify(passage, path, cache)
        if passage["value"] == "2026-10-30":
            target.write_bytes(target.read_bytes().replace(b": ", b":  "))

    monkeypatch.setattr(primary_review, "verify_evidence", changed_metadata)
    with pytest.raises(ValueError, match="metadata changed during review"):
        calendar.verify_report_evidence(row, "2026-10-31T08:00:00-06:00")
