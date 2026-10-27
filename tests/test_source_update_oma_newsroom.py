"""Newsroom binding contracts; actual official PDF replay is tested separately."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates import availability
from src.source_updates import availability_oma_newsroom as source
from src.source_updates.catalog import ROOT

NEWS = "https://news.oma.aero/news/oma-september-2026-traffic.html"
PDF = "https://news.oma.aero/assets/oma-september-2026-traffic.html?dl=1"
CUTOFF = "2026-10-27T17:20:00Z"
BODY = (
    '<h1 class="section-title">OMA reports a 4.8% decrease in September 2026 passenger traffic</h1>'
    '<span class="section-subtitle-date">07 October 2026</span>'
    f'<a href="{PDF}">Download PDF</a><a href="{PDF}">Download PDF </a>'
)


def test_discovery_deduplicates_literal_download_and_never_guesses_a_url(tmp_path):
    path = tmp_path / "index.html"
    path.write_text(BODY)
    assert source.discover(path, NEWS) == ("2026M09", PDF, "2026-10-07")
    assert len(source.selection(NEWS)["items"]) == 1
    selected = source.selection(NEWS, "2026M09", path)
    assert [i["url"] for i in selected["items"]] == [NEWS, PDF]
    for body in (
        BODY.replace("September", "UnknownMonth"),
        BODY + f'<a href="{PDF.replace("traffic.html", "other.html")}">Download PDF</a>',
        BODY.replace("Download PDF", "See report"),
        BODY + '<base href="https://example.com/">',
        BODY.replace("07 October 2026", "32 October 2026"),
        BODY + '<h1 class="section-title">another report</h1>',
    ):
        path.write_text(body)
        with pytest.raises(ValueError):
            source.discover(path, NEWS)
    path.write_text(BODY)
    with pytest.raises(ValueError, match="requested month"):
        source.selection(NEWS, "2026M08", path)
    for url in (NEWS.replace("news.oma.aero", "other.news.oma.aero"), NEWS + "?redirect=x", NEWS + "#x"):
        with pytest.raises(ValueError, match="exact official hostname"):
            source.selection(url)


def test_month_boundary_uses_mexico_and_cli_selection_is_offline(tmp_path, capsys):
    from src.source_updates.__main__ import main

    assert source.latest_closed_month("2026-11-01T05:59:59Z") == "2026M09"
    assert source.latest_closed_month("2026-11-01T06:00:00Z") == "2026M10"
    path = tmp_path / "index.html"
    path.write_text(BODY)
    assert (
        main(
            [
                "recipe",
                "--product",
                "oma_traffic",
                "--output",
                "selection",
                "--source-url",
                NEWS,
                "--catalog-file",
                str(path),
                "--period",
                "2026M09",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["items"][1]["url"] == PDF
    assert main(["recipe", "--product", "oma_traffic", "--source-url", NEWS]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"


@pytest.fixture
def physical(monkeypatch):
    root = ROOT / "tmp/source-updates" / ("test-oma-newsroom-" + uuid4().hex)
    collection, candidate = root / "collection", root / "candidate"
    bronze, rows = collection / "data/bronze", []
    records = []
    for name, body, url, ext in (
        ("index", BODY.encode(), NEWS, "html"),
        ("pdf", b"%PDF-contract", PDF, "pdf"),
    ):
        path = save_bronze(
            body,
            "oma_ir",
            name,
            "2026M09",
            ext,
            url,
            "httpx",
            bronze_root=bronze,
            downloaded_at=datetime(2026, 10, 27, 17, 8, 0 if name == "index" else 1, tzinfo=UTC),
            http_status=200,
        )
        records.append(json.loads(Path(str(path) + ".meta.json").read_text()))
        rows.append(
            dict(
                id=name,
                product="oma_traffic",
                status="collected_catalog" if name == "index" else "collected_unvalidated",
                requested_period="current" if name == "index" else "2026M09",
                source_file=path.relative_to(bronze).as_posix(),
                sha256=availability.sha(path),
                bytes=len(body),
                http_status=200,
                source_url=url,
                response_url=url,
            )
        )
    run_id = "a" * 32
    receipt = dict(
        run_id=run_id,
        mode="collection",
        status="collected_unvalidated",
        activation="none",
        publication="not_authorized",
        started_at="2026-10-27T17:07:59Z",
        finished_at="2026-10-27T17:08:02Z",
        items=rows,
    )
    receipt_path = collection / "receipts" / f"collection-{run_id}.json"
    receipt_path.parent.mkdir()
    receipt_path.write_text(json.dumps(receipt))
    frame = pd.DataFrame(dict(value=[1, 2], source_file=[rows[1]["source_file"]] * 2))
    native = candidate / "data/silver/source_products/oma_traffic.parquet"
    native.parent.mkdir(parents=True)
    frame.to_parquet(native)

    def replay(inputs, period):
        assert inputs["pdf"][0] == b"%PDF-contract" and period == "2026M09"
        assert inputs["pdf"][1] == records[1]
        return frame.copy(), dict(source_report_date_as_reported="2026-10-07")

    monkeypatch.setattr(source, "parse", replay)
    item = dict(
        product="oma_traffic",
        adapter="retained",
        period="2026M09",
        workspace=str(candidate),
        availability=dict(
            source_scope=source.SCOPE,
            workspace=str(collection),
            run_id=run_id,
            catalog_item="index",
            artifact_item="pdf",
        ),
    )
    yield dict(
        item=item,
        native=native,
        rows=rows,
        receipt=receipt,
        receipt_path=receipt_path,
        bronze=bronze,
        frame=frame,
    )
    shutil.rmtree(root)


def test_complete_physical_binding_and_full_native_value_replay(physical):
    state = physical
    details = dict(complete_month_certified=True, source_report_date_as_reported="2026-10-07")
    checked = availability.verify(state["item"], details, CUTOFF)
    assert checked["latest_available_period"] == "2026M09"
    assert checked["all_sites_latest_revision_census"] is False
    assert checked["first_publication_date"] is checked["publication_time"] is None
    # Same physical hash cannot conceal a changed native value or a missing row.
    for frame in (state["frame"].assign(value=[1, 3]), state["frame"].iloc[:1]):
        frame.to_parquet(state["native"])
        with pytest.raises(ValueError, match="exact PDF replay"):
            availability.verify(state["item"], details, CUTOFF)


def test_wrong_period_product_date_and_partial_month_never_gain_availability(physical):
    state, details = (
        physical,
        dict(complete_month_certified=True, source_report_date_as_reported="2026-10-07"),
    )
    for key, value in (("product", "aicm_traffic"), ("adapter", "government"), ("period", "2026M08")):
        changed = {**state["item"], key: value}
        with pytest.raises(ValueError):
            availability.verify(changed, details, CUTOFF)
    for cutoff in ("2026-10-28T17:20:00Z", "2026-11-01T05:59:59Z", "2026-11-01T06:00:00Z"):
        with pytest.raises(ValueError):
            availability.verify(state["item"], details, cutoff)
    with pytest.raises(ValueError, match="report date"):
        availability.verify(
            state["item"], {**details, "source_report_date_as_reported": "2026-10-08"}, CUTOFF
        )


def test_manifest_receipt_http_and_raw_bytes_must_agree(physical):
    state = physical
    details = dict(complete_month_certified=True, source_report_date_as_reported="2026-10-07")
    for key, value in (("status", "incomplete"), ("publication", "authorized")):
        old = state["receipt"][key]
        state["receipt"][key] = value
        state["receipt_path"].write_text(json.dumps(state["receipt"]))
        with pytest.raises(ValueError, match="complete two-original"):
            availability.verify(state["item"], details, CUTOFF)
        state["receipt"][key] = old
    state["receipt_path"].write_text(json.dumps(state["receipt"]))
    path = state["bronze"] / state["rows"][1]["source_file"]
    path.write_bytes(b"%PDF-tampered")
    with pytest.raises(ValueError, match="differs from a successful"):
        availability.verify(state["item"], details, CUTOFF)
