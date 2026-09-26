from __future__ import annotations

import copy
import hashlib
import json
from bs4 import BeautifulSoup
import duckdb
import pytest

from src.analysis_agent.stage12 import (
    GROUPS, HTML_OUTPUT, OUTPUT, build_diagnosis, coverage, file_hash,
    quarter_months, render_html, verify_artifact, write_outputs,
)
from src.config import PATHS


@pytest.fixture(scope="module")
def diagnosis():
    return build_diagnosis()


@pytest.mark.local_data
def test_coverage_reconciles_independent_source_query(diagnosis):
    rows = diagnosis["rows"]
    assert [r["period_id"] for r in rows] == [
        f"{y}Q{q}" for y in range(2021, 2027) for q in range(1, 5)
        if f"{y}Q{q}" <= "2026Q2"
    ]
    with duckdb.connect(str(PATHS.warehouse), read_only=True) as c:
        for group, metrics in GROUPS.items():
            counts = dict(c.execute("""SELECT period_id, count(*) FROM v_carrier_default
                WHERE carrier_key='AEROMEXICO' AND period_type='quarter' AND segment='total'
                AND metric_key IN (SELECT unnest(?)) AND value IS NOT NULL AND isfinite(value)
                GROUP BY period_id""", [list(metrics)]).fetchall())
            assert all(r["groups"][group]["count"] == counts.get(r["period_id"], 0) for r in rows)
    assert diagnosis["summary"]["complete_financial"] == 8
    assert diagnosis["summary"]["complete_operating"] == 22


def test_duplicate_metric_is_rejected_and_null_is_not_zero():
    with pytest.raises(ValueError, match="Duplicate"):
        coverage([{"metric_key": "x", "value": 1}, {"metric_key": "x", "value": 2}], ("x",))
    result = coverage([{"metric_key": "x", "value": None}, {"metric_key": "y", "value": 0},
                       {"metric_key": "z", "value": float("nan")}], ("x", "y", "z"))
    assert result["available"] == ["y"]
    assert result["missing"] == ["x", "z"]


@pytest.mark.local_data
def test_calendar_and_month_counts_do_not_mix_aggregations(diagnosis):
    assert quarter_months("2021Q4") == ["2021M10", "2021M11", "2021M12"]
    with pytest.raises(ValueError):
        quarter_months("2021Q5")
    for row in diagnosis["rows"]:
        for key, values in row["context"].items():
            if isinstance(values, list):
                assert len(values) <= 3
                assert len(values) == len(set(values))
                assert set(values) <= set(quarter_months(row["period_id"]))
    assert diagnosis["rows"][-1]["context"]["fx_months"] == ["2026M04", "2026M05", "2026M06"]


@pytest.mark.local_data
def test_later_comparatives_are_flagged_without_certifying_cutoffs(diagnosis):
    later = [r["period_id"] for r in diagnosis["rows"]
             if "financial_values_from_later_comparative" in r["gaps"]]
    assert later == ["2024Q3", "2024Q4", "2025Q1", "2025Q2"]
    assert all(r["cutoff_date"] is None and r["temporal_status"] == "not_verified"
               and r["analysis_status"] == "not_started" for r in diagnosis["rows"])
    for row in diagnosis["rows"]:
        for candidate in row["sec_candidates"]:
            assert candidate["filing_date"] is not None
        assert all(a["publication_date"] is None for a in row["artifacts"])


def test_artifact_hash_missing_file_and_path_escape(tmp_path):
    file = tmp_path / "release.pdf"
    file.write_bytes(b"test artifact")
    artifact = {"source_file": "release.pdf", "artifact_id": "example",
                "artifact_sha256": file_hash(file), "source_url": "https://ir.aeromexico.com/release"}
    assert verify_artifact(artifact, tmp_path)["integrity_status"] == "verified_hash"
    file.write_bytes(b"modified")
    assert verify_artifact(artifact, tmp_path)["integrity_status"] == "hash_mismatch"
    file.unlink()
    assert verify_artifact(artifact, tmp_path)["integrity_status"] == "missing_local_file"
    with pytest.raises(ValueError, match="leaves Bronze"):
        verify_artifact(artifact | {"source_file": "../outside.pdf"}, tmp_path)


@pytest.mark.local_data
def test_rendering_escapes_content_and_rejects_untrusted_links(diagnosis):
    altered = copy.deepcopy(diagnosis)
    altered["rows"][0]["label"] = "</script><script id='injected'>alert(1)</script>"
    soup = BeautifulSoup(render_html(altered), "html.parser")
    assert soup.select_one("#injected") is None
    assert json.loads(soup.select_one("#stage12-data").string)["rows"][0]["label"] == altered["rows"][0]["label"]
    altered["rows"][0]["artifacts"][0]["source_url"] = "javascript:alert(1)"
    with pytest.raises(ValueError, match="Non-official"):
        render_html(altered)


@pytest.mark.local_data
def test_mock_has_explicit_illustration_and_no_remote_or_approval_runtime(diagnosis):
    document = render_html(diagnosis)
    soup = BeautifulSoup(document, "html.parser")
    assert "Maqueta ilustrativa" in soup.get_text()
    assert "no hay análisis generado, auditado ni aprobado" in soup.get_text()
    assert not soup.select("script[src], link[href], iframe, img[src]")
    assert len(soup.select('[role="tab"]')) == 2
    assert len(soup.select("#scenario option")) == 3
    runtime = soup.find_all("script")[-1].string.lower()
    for primitive in ("fetch(", "xmlhttprequest", "websocket", "localstorage", "sessionstorage", "innerhtml"):
        assert primitive not in runtime
    assert "approve(" not in runtime
    assert "C:\\Users" not in document and "file://" not in document


@pytest.mark.local_data
def test_outputs_match_snapshot_and_are_reproducible(diagnosis, tmp_path):
    tracked = [PATHS.warehouse, PATHS.root / "prototypes/etapa-11/resumen_ejecutivo.html",
               *sorted(PATHS.gold.glob("*"))]
    before = {str(p): file_hash(p) for p in tracked if p.is_file()}
    fresh = build_diagnosis()
    assert fresh == diagnosis
    write_outputs(fresh, tmp_path / "diagnosis", tmp_path / "review.html")
    generated = (tmp_path / "review.html").read_bytes()
    expected = HTML_OUTPUT.read_bytes()
    if generated != expected:
        offset = next(
            (i for i, (a, b) in enumerate(zip(generated, expected)) if a != b),
            min(len(generated), len(expected)),
        )
        start = max(0, offset - 200)
        raise AssertionError(
            "Regenerated diagnosis review does not match the checked-in HTML "
            f"(generated sha256={hashlib.sha256(generated).hexdigest()}, "
            f"expected sha256={hashlib.sha256(expected).hexdigest()}, "
            f"first differing offset={offset}).\n"
            f"generated[{start}:{offset + 200}]={generated[start:offset + 200]!r}\n"
            f"expected[{start}:{offset + 200}]={expected[start:offset + 200]!r}"
        )
    assert (tmp_path / "diagnosis/diagnostico.json").read_bytes() == (OUTPUT / "diagnostico.json").read_bytes()
    assert (tmp_path / "diagnosis/cobertura.csv").read_bytes() == (OUTPUT / "cobertura.csv").read_bytes()
    assert before == {str(p): file_hash(p) for p in tracked if p.is_file()}
