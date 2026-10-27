"""Public synthetic discovery/binding contracts; official historical replay is separate."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates import availability as physical
from src.source_updates import availability_afac_airports as airport
from src.source_updates.catalog import ROOT
from src.source_updates.collection import collect

XLS = "https://www.gob.mx/cms/uploads/attachment/file/1100275/producto-aeropuerto-2006-2026-jul-27082026.xlsx"
ES = "https://www.gob.mx/cms/uploads/attachment/file/1100277/producto-aeropuertos-es-jul-26-27082026.pdf"
EN = "https://www.gob.mx/cms/uploads/attachment/file/1100276/producto-aeropuertos-en-jul-26-27082026.pdf"
CUTOFF = "2026-10-27T12:30:00+00:00"


def index_html():
    return (
        f"<html><h1>Estadísticas</h1><table><tr><td><p>{airport.HEADING}</p><ul>"
        f'<li><a href="{XLS}">(Excel File) Estadística Operativa de Aeropuertos / '
        "Statistics by Airport 2006-2026</a></li>"
        f'<li><a href="{ES}">(PDF Español) Estadística Operacional de Aeropuertos - Julio 2026</a></li>'
        f'<li><a href="{EN}">(PDF English) Airports Operational Statistics - July 2026</a></li>'
        "</ul></td></tr></table></html>"
    )


@pytest.mark.parametrize(
    "defect",
    [
        None,
        "base",
        "wrong_identity",
        "other_topic",
        "pdf_month",
        "workbook_year",
        "different_edition",
        "extra_workbook",
        "opaque_newer",
        "opaque_statistics",
        "opaque_report",
        "unknown_format",
        "missing_pdf",
        "duplicate_pdf",
        "outside_host",
        "query",
        "wrong_heading",
        "wrong_row",
    ],
)
def test_discovery_selects_one_concordant_airport_edition(tmp_path, defect):
    body = index_html()
    if defect == "base":
        body += '<base href="https://other.invalid/">'
    elif defect == "wrong_identity":
        body = body.replace("<h1>Estadísticas</h1>", "<h1>Other institution</h1>")
    elif defect == "other_topic":
        body = body.replace("Statistics by Airport 2006-2026", "Traffic Statistics by City Pairs")
    elif defect == "pdf_month":
        body = body.replace("July 2026", "August 2026")
    elif defect == "workbook_year":
        body = body.replace("2006-2026-jul", "2006-2025-jul")
    elif defect == "different_edition":
        body = body.replace("es-jul-26-27082026", "es-jul-26-28082026")
    elif defect == "extra_workbook":
        body += f'<a href="{XLS}">Statistics by Airport</a>'
    elif defect == "opaque_newer":
        body += '<a href="/download?id=September">Airports Operational Statistics September 2026</a>'
    elif defect in {"opaque_statistics", "opaque_report"}:
        title = "Airport Statistics" if defect == "opaque_statistics" else "Airport Operational Report"
        body += f'<a href="/cms/uploads/attachment/file/9999999/new.xlsx">{title} - September 2026</a>'
    elif defect == "unknown_format":
        body = body.replace(".xlsx", ".zip")
    elif defect == "missing_pdf":
        body = body.replace(
            f'<li><a href="{EN}">(PDF English) Airports Operational Statistics - July 2026</a></li>', ""
        )
    elif defect == "duplicate_pdf":
        body = body.replace(EN, ES)
    elif defect == "outside_host":
        body = body.replace("https://www.gob.mx/", "https://outside.invalid/")
    elif defect == "query":
        body = body.replace(XLS, XLS + "?edition=2")
    elif defect == "wrong_heading":
        body = body.replace(airport.HEADING, "Traffic Statistics by Airline")
    elif defect == "wrong_row":
        body = body.replace('<li><a href="' + EN, '</ul></td></tr><tr><td><ul><li><a href="' + EN)
    path = tmp_path / "index.html"
    path.write_text(body, encoding="utf-8")
    if defect:
        with pytest.raises(ValueError):
            airport.latest(path)
    else:
        assert airport.latest(path) == ("2026M07", XLS)
        selection = airport.select(path)
        plan = collect(selection, ROOT / "tmp/source-updates/afac-airports-never-executed-contract")
        assert plan["base_requests"] == 2 and plan["paid_requests"] == 0
        assert len(selection["items"]) == 2 and {i["mode"] for i in selection["items"]} == {"get"}
        assert plan["activation"] == "none"


@pytest.fixture
def source_contract(monkeypatch):
    root = ROOT / "tmp/source-updates" / ("test-afac-airports-availability-" + uuid4().hex)
    candidate, collection = root / "candidate", root / "collection"
    bronze = collection / "data/bronze"
    rows = []
    for i, (role, alias, body, url, ext) in enumerate(
        [
            ("index", "route_research", index_html().encode(), airport.ENTRY, "html"),
            ("workbook", "afac", b"synthetic workbook, extraction is stubbed explicitly", XLS, "xlsx"),
        ]
    ):
        path = save_bronze(
            body,
            alias,
            role,
            "current" if role == "index" else "2026M07",
            ext,
            url,
            "httpx",
            bronze_root=bronze,
            downloaded_at=datetime(2026, 10, 27, 12, i, tzinfo=UTC),
            http_status=200,
        )
        rows.append(
            dict(
                id=role,
                product="afac_airports",
                status="collected_catalog" if role == "index" else "collected_unvalidated",
                requested_period="current" if role == "index" else "2026M07",
                source_file=path.relative_to(bronze).as_posix(),
                sha256=physical.sha(path),
                bytes=len(body),
                http_status=200,
                source_url=url,
                response_url=url,
            )
        )
    rid = "a" * 32
    receipt = dict(
        run_id=rid,
        mode="collection",
        status="collected_unvalidated",
        activation="none",
        publication="not_authorized",
        started_at="2026-10-27T11:59:59+00:00",
        finished_at="2026-10-27T12:01:01+00:00",
        items=rows,
    )
    receipt_path = collection / "receipts" / f"collection-{rid}.json"
    receipt_path.parent.mkdir()
    receipt_path.write_text(json.dumps(receipt))
    frame = pd.DataFrame(
        dict(
            period_id=["2026M06", "2026M07"],
            source_file=[rows[1]["source_file"]] * 2,
            source_hash=[rows[1]["sha256"]] * 2,
            source_system=["afac"] * 2,
            value=[10.0, 20.0],
        )
    )
    details = dict(months_validated=["2026M06", "2026M07"], visible_crosschecks=173)
    monkeypatch.setattr(
        airport.afac_airports, "parse", lambda body, period, record: (frame.copy(), details.copy())
    )
    native = candidate / "data" / airport.TABLE
    native.parent.mkdir(parents=True)
    frame.to_parquet(native)
    item = dict(
        product="afac_airports",
        adapter="retained",
        period="2026M07",
        workspace=str(candidate),
        availability=dict(
            workspace=str(collection), run_id=rid, catalog_item="index", artifact_item="workbook"
        ),
    )
    result = dict(status="checks_passed", report_period="2026M07", rows=2, **details)
    yield dict(
        root=root,
        item=item,
        result=result,
        frame=frame,
        native=native,
        rows=rows,
        receipt=receipt,
        receipt_path=receipt_path,
        bronze=bronze,
    )
    shutil.rmtree(root)


@pytest.mark.parametrize(
    "defect",
    [
        None,
        "wrong_product",
        "wrong_adapter",
        "same_id",
        "extra_item",
        "missing_role",
        "wrong_role",
        "swapped_alias",
        "http",
        "old_index",
        "old_workbook",
        "future_capture",
        "reversed",
        "wrong_url",
        "wrong_period",
        "native_subset",
        "native_value",
        "native_hash",
        "numeric_failed",
        "missing_month",
        "crosschecks",
        "sidecar",
        "writer",
        "body_after_validation",
    ],
)
def test_current_physical_binding_replays_native_and_never_promotes_old_captures(
    source_contract, defect, monkeypatch
):
    s = source_contract
    rows = s["rows"]
    manifest = s["bronze"] / "_manifest.jsonl"
    records = [json.loads(line) for line in manifest.read_text().splitlines()]
    if defect == "wrong_product":
        s["item"]["product"] = "afac_carriers"
    elif defect == "wrong_adapter":
        s["item"]["adapter"] = "government"
    elif defect == "same_id":
        s["item"]["availability"]["artifact_item"] = "index"
    elif defect == "extra_item":
        s["receipt"]["items"].append(dict(rows[1], id="unclassified"))
    elif defect == "missing_role":
        s["receipt"]["items"].pop()
    elif defect == "wrong_role":
        rows[1]["product"] = "afac_carriers"
    elif defect == "swapped_alias":
        records[1]["source_system"] = "route_research"
    elif defect == "http":
        records[1]["http_status"] = 403
    elif defect in {"old_index", "old_workbook", "future_capture", "reversed"}:
        i = 0 if defect == "old_index" else 1
        records[i]["downloaded_at"] = {
            "old_index": "2026-09-08T18:24:49+00:00",
            "old_workbook": "2026-09-13T00:47:55+00:00",
            "future_capture": "2026-10-27T12:31:00+00:00",
            "reversed": "2026-10-27T11:59:59+00:00",
        }[defect]
    elif defect == "wrong_url":
        rows[0]["response_url"] = "https://www.gob.mx/afac/other-index"
    elif defect == "wrong_period":
        s["item"]["period"] = "2026M09"
    elif defect and defect.startswith("native_"):
        frame = s["frame"].copy()
        if defect == "native_subset":
            frame = frame.iloc[:1]
        elif defect == "native_value":
            frame.loc[0, "value"] = 99.0
        else:
            frame["source_hash"] = "f" * 64
        frame.to_parquet(s["native"])
    elif defect == "numeric_failed":
        s["result"]["status"] = "blocked"
    elif defect == "missing_month":
        s["result"]["months_validated"] = ["2026M07"]
    elif defect == "crosschecks":
        s["result"]["visible_crosschecks"] = 172
    elif defect == "writer":
        (s["root"] / "collection/.source-update.lock").touch()
    elif defect == "body_after_validation":
        real = physical.artifact

        def changed(*args):
            path, record = real(*args)
            if record["source_system"] == "route_research":
                path.write_bytes(b"not the verified index")
            return path, record

        monkeypatch.setattr(physical, "artifact", changed)
    for record in records:
        Path(str(s["bronze"] / record["source_file"]) + ".meta.json").write_text(json.dumps(record))
    manifest.write_text("".join(json.dumps(record) + "\n" for record in records))
    if defect == "sidecar":
        Path(str(s["bronze"] / rows[1]["source_file"]) + ".meta.json").write_text("{}")
    s["receipt_path"].write_text(json.dumps(s["receipt"]))
    if defect:
        with pytest.raises(ValueError):
            physical.verify(s["item"], s["result"], CUTOFF)
    else:
        proof = physical.verify(s["item"], s["result"], CUTOFF)
        assert proof["latest_available_period"] == "2026M07"
        assert proof["reported_workbook_verified"] is True
        assert proof["complete_observational_census_claimed"] is False
        assert proof["first_publication_date"] is None and proof["release_lag_days"] is None


def test_same_day_check_rejects_separate_retained_capture_dates_without_invented_receipt():
    index = dict(downloaded_at="2026-09-08T18:24:49.732054+00:00")
    workbook = dict(downloaded_at="2026-09-13T00:47:55.040152+00:00")
    with pytest.raises(ValueError, match="actual captures on the round date"):
        airport.current_chronology(index, workbook, CUTOFF)


@pytest.mark.parametrize("period", [None, "latest", "2026M07", "2026M09"])
def test_existing_recipe_cli_exposes_actual_airport_discovery_without_network(tmp_path, capsys, period):
    from src.source_updates.__main__ import main

    args = ["recipe", "--product", "afac_airports", "--output", "selection"]
    if period:
        path = tmp_path / "index.html"
        path.write_text(index_html(), encoding="utf-8")
        args += ["--catalog-file", str(path), "--period", period]
    status = main(args)
    output = json.loads(capsys.readouterr().out)
    if period == "2026M09":
        assert status == 1 and "not the observed official workbook" in output["reason"]
    else:
        assert status == 0
        assert output["items"][0]["url"] == airport.ENTRY
        assert len(output["items"]) == (2 if period else 1)
        if period:
            assert output["items"][1]["period"] == "2026M07" and output["items"][1]["url"] == XLS
