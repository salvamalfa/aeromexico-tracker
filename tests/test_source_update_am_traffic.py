"""IR traffic monthly-column, service-basis, completeness and candidate regressions."""

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
import json
import re
import shutil
from uuid import uuid4

import httpx
import pandas as pd
import pytest

from src.source_updates import am_traffic, am_traffic_candidate as candidate
from src.source_updates.catalog import ROOT
from src.source_updates.collection import collect
from src.source_updates.discovery import select_documents


TEXT = """Aeroméxico September 2026 Traffic Results
Mexico City, Mexico, October 6, 2026 – Grupo Aeroméxico S.A.B. de C.V.
2026 2025 Var. 2026 2025 Var.
Passengers Domestic 1,226 1,276 -3.9% 11,662 12,134 -3.9%
International 627 617 1.8% 6,304 6,285 0.3%
Total 1,853 1,892 -2.1% 17,966 18,419 -2.5%
ASMs Domestic 802 830 -3.4% 7,797 8,041 -3.0%
International 2,090 1,966 6.3% 19,451 19,013 2.3%
Total 2,892 2,796 3.4% 27,248 27,054 0.7%
RPMs Domestic 689 715 -3.7% 6,598 6,851 -3.7%
International 1,830 1,716 6.6% 16,804 16,267 3.3%
Total 2,518 2,431 3.6% 23,403 23,119 1.2%
Load Factor Domestic 85.9% 86.1% -0.3 p.p. 84.6% 85.2% -0.6 p.p.
International 87.6% 87.3% 0.2 p.p. 86.4% 85.6% 0.9 p.p.
Total 87.1% 87.0% 0.1 p.p. 85.9% 85.5% 0.5 p.p.
(itinerary + charter, thousands)
(itinerary + charter, millions)
(itinerary + charter, millions)
(itinerary, %)
September Cumulative to September
Figures may not sum to total due to rounding.
\f
The information included within this report has not been audited.
"""
ORIGINAL = {"source_file": "report.pdf", "sha256": "a" * 64, "downloaded_at": "2026-10-19T10:00:00Z"}
PDF = b"%PDF-1.7\nsynthetic fixture bytes, extraction mocked explicitly\n%%EOF"


def test_monthly_columns_units_comparatives_and_service_basis():
    frame, details = am_traffic.parse(TEXT, "2026M09", ORIGINAL)
    assert len(frame) == 24 and details["release_lag_days"] == 6
    assert details["cumulative_rows_imported"] == 0
    assert frame.source_page.eq(1).all()
    current = frame.loc[frame.period_id.eq("2026M09") & frame.segment.eq("total")].set_index("metric_key")
    assert current.loc["passengers", "value_normalized"] == 1_853_000
    assert current.loc["asm_total", "value_normalized"] == 2_892_000_000
    assert current.loc["rpm_total", "value_normalized"] == 2_518_000_000
    assert current.loc["load_factor_total", "value_normalized"] == 0.871
    assert current.loc["load_factor_total", "service_scope"] == "itinerary_only"
    assert current.loc["rpm_total", "service_scope"] == "itinerary_and_charter"
    assert frame.is_yoy_comparison.sum() == 12
    assert frame.reporting_status.eq("unaudited").all() and not frame.is_preliminary.any()
    assert set(frame.source_system) == {"aeromexico_ir"}


def test_source_page_follows_formfeed_without_inventing_table_location():
    text = TEXT.replace("2026 2025 Var.", "\f\n2026 2025 Var.", 1)
    assert am_traffic.parse(text, "2026M09", ORIGINAL)[0].source_page.eq(2).all()


def test_narrative_outside_table_is_not_an_unclassified_traffic_row():
    text = TEXT.replace(
        "2026 2025 Var.", "International demand continued across our network.\n2026 2025 Var.", 1
    )
    assert len(am_traffic.parse(text, "2026M09", ORIGINAL)[0]) == 24


def test_verified_standalone_metric_headings_and_pp_column_units():
    text = TEXT
    units = {
        "Passengers": "itinerary + charter, thousands",
        "ASMs": "itinerary + charter, millions",
        "RPMs": "itinerary + charter, millions",
        "Load Factor": "itinerary, %",
    }
    for heading, unit in units.items():
        suffix = " p.p. p.p." if heading == "Load Factor" else ""
        text = text.replace(heading + " Domestic", heading + " (" + unit + ")" + suffix + "\nDomestic")
    text = re.sub(r"([+-]?\d+(?:\.\d+)?) p\.p\.", r"\1", text)
    assert (
        am_traffic.parse(text, "2026M09", ORIGINAL)[0].value_normalized.tolist()
        == am_traffic.parse(TEXT, "2026M09", ORIGINAL)[0].value_normalized.tolist()
    )
    with pytest.raises(ValueError):
        am_traffic.parse(text.replace(" p.p. p.p.", ""), "2026M09", ORIGINAL)


@pytest.mark.parametrize(
    "before,after",
    [
        ("2026 2025 Var. 2026 2025 Var.", "2025 2026 Var. 2025 2026 Var."),
        ("Cumulative to September", "Monthly to September"),
        ("itinerary + charter, thousands", "itinerary + charter, millions"),
        ("itinerary, %", "itinerary + charter, %"),
        ("not been audited", "been audited"),
        ("October 6, 2026", "September 20, 2026"),
        ("1,226 1,276", "ND 1,276"),
        ("1,226 1,276", "1.226 1,276"),
        ("Total 1,853 1,892", "Total 9,853 1,892"),
        ("Total 87.1% 87.0%", "Total 101.1% 87.0%"),
        ("Total 87.1% 87.0%", "Total 10.1% 87.0%"),
        ("September 2026 Traffic Results", "August 2026 Traffic Results"),
        ("Passengers Domestic 1,226 1,276 -3.9% 11,662 12,134 -3.9%", ""),
        ("RPMs Domestic 689 715 -3.7% 6,598 6,851 -3.7%", ""),
    ],
)
def test_ambiguous_incomplete_or_wrong_basis_source_blocks(before, after):
    with pytest.raises(ValueError):
        am_traffic.parse(TEXT.replace(before, after), "2026M09", ORIGINAL)


def test_duplicate_row_is_rejected_even_when_equal():
    with pytest.raises(ValueError, match="Duplicate"):
        am_traffic.parse(
            TEXT.replace("ASMs Domestic", "Total 1,853 1,892 -2.1% 17,966 18,419 -2.5%\nASMs Domestic"),
            "2026M09",
            ORIGINAL,
        )


def test_reversed_monthly_and_cumulative_blocks_cannot_be_labelled_monthly():
    changed = TEXT.replace("September Cumulative to September", "Cumulative to September September")
    lines = []
    for line in changed.split("\n"):
        match = re.match(r"(.*?(?:Domestic|International|Total))\s+(.+)$", line)
        if match:
            cells = re.findall(r"[+-]?[\d,.]+(?:%| p\.p\.)?", match[2])
            assert len(cells) == 6
            line = match[1] + " " + " ".join(cells[3:] + cells[:3])
        lines.append(line)
    with pytest.raises(ValueError, match="Monthly and year-to-date"):
        am_traffic.parse("\n".join(lines), "2026M09", ORIGINAL)


def test_wrong_company_is_not_aeromexico_even_with_matching_grid():
    with pytest.raises(ValueError, match="identity"):
        am_traffic.parse(TEXT.replace("Aeroméxico", "Another Airline"), "2026M09", ORIGINAL)


def test_selector_only_uses_actual_unique_permitted_link(tmp_path):
    path = tmp_path / "catalog.html"
    anchor = '<a href="/static-files/real-uuid">Aeroméxico September 2026 Traffic Results</a>'
    path.write_text(anchor * 2)
    selection = select_documents("am_traffic_ir", path, "2026M09")
    assert selection["items"][0]["url"] == "https://ir.aeromexico.com/static-files/real-uuid"
    assert selection["items"][0]["extension"] == "pdf"
    with pytest.raises(ValueError, match="absent or ambiguous"):
        select_documents("am_traffic_ir", path, "2026M08")
    path.write_text(anchor + anchor.replace("real-uuid", "revision-uuid"))
    with pytest.raises(ValueError, match="ambiguous"):
        select_documents("am_traffic_ir", path, "2026M09")
    path.write_text(anchor.replace("/static-files/real-uuid", "https://external.example/report.pdf"))
    with pytest.raises(ValueError, match="catalogue hosts"):
        select_documents("am_traffic_ir", path, "2026M09")


@pytest.fixture
def workspace():
    path = ROOT / "tmp/source-updates" / ("am-traffic-test-" + uuid4().hex)
    yield path
    if path.exists():
        shutil.rmtree(path)


def cutoff():
    return (datetime.now(UTC) + timedelta(minutes=1)).isoformat()


def capture(workspace):
    class Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, url, **kwargs):
            return httpx.Response(200, content=PDF, request=httpx.Request(method, url))

    selection = {
        "version": 1,
        "items": [
            {
                "id": "am-traffic-2026M09",
                "product": "am_traffic_ir",
                "source_system": "aeromexico_ir",
                "entity": "am_traffic_ir",
                "period": "2026M09",
                "purpose": "data",
                "url": "https://ir.aeromexico.com/static-files/test",
                "extension": "pdf",
                "mode": "get",
            }
        ],
    }
    return collect(selection, workspace, execute=True, client_factory=Client)["run_id"]


def test_default_preview_has_no_network_or_writes(workspace):
    result = candidate.run(workspace, "2026M09", cutoff(), "a" * 32)
    assert result["network_requests"] == 0 and not workspace.exists()


def test_candidate_reconstructs_monthly_only_gold_without_network(workspace, monkeypatch):
    receipt = capture(workspace)
    monkeypatch.setattr(candidate, "pdf_text", lambda _: TEXT)
    result = candidate.run(workspace, "2026M09", cutoff(), receipt, execute=True)
    assert result["status"] == "checks_passed" and result["lineage"]["records_expected"] == 24
    gold = pd.read_parquet(workspace / "data/gold/fact_carrier_metrics.parquet")
    assert set(gold.period_type) == {"month"} and not gold.is_derived.any()
    assert set(gold.source_system) == {"aeromexico_ir"}
    metadata = pd.read_parquet(workspace / "data/gold/dim_metric.parquet")
    assert "not derived" in metadata.set_index("metric_key").loc["load_factor_total", "formula"]
    assert gold.loc[gold.metric_key.eq("asm_total"), "value_metric"].notna().all()
    before = {
        p.relative_to(workspace).as_posix(): p.read_bytes() for p in workspace.rglob("*") if p.is_file()
    }
    checked = candidate.run(workspace, "2026M09", cutoff(), receipt, check=True)
    assert checked["output_sha256"] == result["output_sha256"]
    assert before == {
        p.relative_to(workspace).as_posix(): p.read_bytes() for p in workspace.rglob("*") if p.is_file()
    }
    with pytest.raises(ValueError, match="immutable"):
        candidate.run(workspace, "2026M09", cutoff(), receipt, execute=True)


def test_candidate_receipt_tamper_to_allowed_url_blocks_check(workspace, monkeypatch):
    receipt = capture(workspace)
    monkeypatch.setattr(candidate, "pdf_text", lambda _: TEXT)
    candidate.run(workspace, "2026M09", cutoff(), receipt, execute=True)
    path = workspace / "receipts" / f"collection-{receipt}.json"
    altered = json.loads(path.read_text())
    altered["items"][0]["response_url"] = am_traffic.ENTRY
    path.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="collection receipt changed"):
        candidate.run(workspace, "2026M09", cutoff(), receipt, check=True)


def test_invalid_report_leaves_no_silver_or_gold(workspace, monkeypatch):
    receipt = capture(workspace)
    monkeypatch.setattr(candidate, "pdf_text", lambda _: TEXT.replace("ASMs Domestic", "Missing Domestic"))
    with pytest.raises(ValueError):
        candidate.run(workspace, "2026M09", cutoff(), receipt, execute=True)
    assert not (workspace / "data/gold").exists() and not (workspace / "data/silver").exists()


def test_foreign_outputs_are_preserved(workspace):
    path = workspace / "data/gold/fact_carrier_metrics.parquet"
    path.parent.mkdir(parents=True)
    pd.DataFrame({"source_system": ["sec_edgar"]}).to_parquet(path)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="Existing output"):
        candidate.run(workspace, "2026M09", cutoff(), "a" * 32, execute=True)
    assert path.read_bytes() == before


def test_acceptance_created_between_preflight_and_writer_is_preserved(workspace, monkeypatch):
    receipt = capture(workspace)
    monkeypatch.setattr(candidate, "pdf_text", lambda _: TEXT)
    real_writer = candidate.writer
    path = workspace / "receipts/am-traffic-2026M09.json"

    @contextmanager
    def competing_writer(root):
        with real_writer(root):
            path.write_text("accepted by competing invocation")
            yield

    monkeypatch.setattr(candidate, "writer", competing_writer)
    with pytest.raises(ValueError, match="immutable"):
        candidate.run(workspace, "2026M09", cutoff(), receipt, execute=True)
    assert path.read_text() == "accepted by competing invocation"
    assert not (workspace / "data/gold").exists()


def test_pdf_text_uses_plain_mode_and_preserves_page_boundaries(monkeypatch):
    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self):
            return self.text

    class Reader:
        is_encrypted = False
        pages = [Page("header"), Page("table")]

    monkeypatch.setattr(am_traffic, "PdfReader", lambda _: Reader())
    assert am_traffic.pdf_text(PDF) == "header\n\f\ntable"
    with pytest.raises(ValueError, match="bounded original"):
        am_traffic.pdf_text(b"not a PDF")


def test_original_hash_and_cutoff_reject_before_parsing(workspace):
    receipt = capture(workspace)
    with pytest.raises(ValueError, match="after the requested cutoff"):
        candidate.run(workspace, "2026M09", "2026-10-02T00:00:00Z", receipt, execute=True)
    path = next((workspace / "data/bronze").rglob("*.pdf"))
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        candidate.run(workspace, "2026M09", cutoff(), receipt, execute=True)
