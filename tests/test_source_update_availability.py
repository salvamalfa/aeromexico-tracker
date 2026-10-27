"""Synthetic physical discovery contracts; these do not certify source extraction."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.source_updates import availability
from src.source_updates.catalog import ROOT

CUTOFF = "2026-10-27T03:00:00+00:00"
URL = "https://aifa-repositorio.s3.us-east-1.amazonaws.com/PyE/Numeralia-Aeroportuaria-Sep-2026.xlsx"


@pytest.fixture
def physical():
    root = ROOT / "tmp/source-updates" / ("test-availability-" + uuid4().hex)
    collection, candidate = root / "collection", root / "candidate"
    candidate.mkdir(parents=True)
    bronze = collection / "data/bronze"
    rows = []
    for name, body, url, ext in [
        (
            "index",
            (
                f'<a href="{URL}">Numeralia Aeroportuaria de Enero a Septiembre 2026 - Formato XLSX (PDF)</a>'
                '<a href="https://aifa-website.s3.us-east-1.amazonaws.com/contenido/RJPyE/'
                'Numeralia%20Aeroportuaria%20Ene.%20a%20Dic.%202023.xlsx">'
                "Numeralia Aeroportuaria de Enero a Diciembre 2023 - Formato XLSX (PDF)</a>"
            ).encode(),
            availability.AIFA_INDEX,
            "html",
        ),
        ("workbook", b"synthetic workbook bytes", URL, "xlsx"),
    ]:
        path = save_bronze(
            body,
            "aifa",
            name,
            "2026M09",
            ext,
            url,
            "httpx",
            bronze_root=bronze,
            downloaded_at=datetime(2026, 10, 27, 2, 55, 0 if name == "index" else 1, tzinfo=UTC),
            http_status=200,
        )
        rows.append(
            dict(
                id=name,
                product="aifa_traffic",
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
        started_at="2026-10-27T02:54:59+00:00",
        finished_at="2026-10-27T02:55:02+00:00",
        items=rows,
    )
    receipt_path = collection / "receipts" / f"collection-{run_id}.json"
    receipt_path.parent.mkdir()
    item = dict(
        product="aifa_traffic",
        adapter="government",
        period="2026M09",
        workspace=str(candidate),
        availability=dict(
            workspace=str(collection), run_id=run_id, catalog_item="index", artifact_item="workbook"
        ),
    )
    native = candidate / "data/silver/government_native.parquet"
    native.parent.mkdir(parents=True)
    pd.DataFrame(
        {
            "source_file": [rows[1]["source_file"]],
            "source_hash": [rows[1]["sha256"]],
            "source_system": ["aifa"],
        }
    ).to_parquet(native)
    state = dict(item=item, receipt=receipt, receipt_path=receipt_path, bronze=bronze, native=native)
    yield state
    shutil.rmtree(root)


def persist(state):
    state["receipt_path"].write_text(json.dumps(state["receipt"]))


@pytest.mark.parametrize(
    "attack",
    [
        None,
        "bytes",
        "newer_link",
        "unknown_newer_layout",
        "case_variation",
        "newer_pdf",
        "period",
        "http",
        "manual",
        "old_capture",
        "future_cutoff",
        "future_capture",
        "discovery_after_data",
        "unused",
        "outside_host",
        "incomplete",
        "forged_recapture",
        "forged_sidecars",
        "sidecar_race",
    ],
)
def test_latest_availability_requires_physical_official_discovery_and_used_capture(
    physical, attack, monkeypatch
):
    s = physical
    rows = s["receipt"]["items"]
    manifest = s["bronze"] / "_manifest.jsonl"
    records = [json.loads(x) for x in manifest.read_text().splitlines()]
    cutoff = CUTOFF
    if attack == "bytes":
        (s["bronze"] / rows[1]["source_file"]).write_bytes(b"tampered")
    elif attack in {"newer_link", "unknown_newer_layout", "case_variation", "newer_pdf"}:
        p = s["bronze"] / rows[0]["source_file"]
        url = URL.replace("Sep", "Oct")
        if attack == "unknown_newer_layout":
            url = url.replace("PyE/", "new-layout/")
        elif attack == "case_variation":
            url = url.replace("Numeralia", "NUMERALIA").replace("xlsx", "XLSX")
        elif attack == "newer_pdf":
            url = url.replace("xlsx", "pdf")
        extension = "PDF" if attack == "newer_pdf" else "XLSX"
        p.write_text(
            p.read_text() + f'<a href="{url}">Numeralia Aeroportuaria de Enero a Octubre 2026 '
            f"- Formato {extension} (PDF)</a>"
        )
        rows[0].update(sha256=availability.sha(p), bytes=p.stat().st_size)
        records[0]["sha256"] = rows[0]["sha256"]
    elif attack == "period":
        s["item"]["period"] = "2026M08"
    elif attack == "http":
        records[1]["http_status"] = 503
    elif attack == "manual":
        records[1]["download_method"] = "manual"
    elif attack == "old_capture":
        records[0]["downloaded_at"] = "2026-10-25T02:55:00+00:00"
    elif attack == "future_cutoff":
        cutoff = "2026-11-17T03:00:00+00:00"
    elif attack == "future_capture":
        records[1]["downloaded_at"] = "2026-10-27T03:01:00+00:00"
    elif attack == "discovery_after_data":
        records[0]["downloaded_at"] = "2026-10-27T02:56:00+00:00"
    elif attack == "unused":
        pd.DataFrame({"source_file": ["other.xlsx"], "source_hash": ["b" * 64]}).to_parquet(s["native"])
    elif attack == "outside_host":
        rows[0]["response_url"] = "https://example.com/index.html"
    elif attack == "incomplete":
        s["receipt"]["status"] = "incomplete"
    elif attack in {"forged_recapture", "forged_sidecars"}:
        cutoff = "2026-11-17T03:00:00+00:00"
        for record in records:
            record["downloaded_at"] = record["downloaded_at"].replace("2026-10-27", "2026-11-17")
            if attack == "forged_sidecars":
                Path(str(s["bronze"] / record["source_file"]) + ".meta.json").write_text(json.dumps(record))
    elif attack == "sidecar_race":
        original = availability.latest_aifa

        def race(path):
            result = original(path)
            Path(str(s["bronze"] / rows[1]["source_file"]) + ".meta.json").write_text("{}")
            return result

        monkeypatch.setattr(availability, "latest_aifa", race)
    manifest.write_text("".join(json.dumps(r) + "\n" for r in records))
    persist(s)
    inventory = {
        str(p.relative_to(s["bronze"].parents[1])): availability.sha(p)
        for p in s["bronze"].parents[1].rglob("*")
        if p.is_file()
    }
    if attack:
        with pytest.raises(ValueError):
            availability.verify(s["item"], {"complete_month_certified": True}, cutoff)
    else:
        result = availability.verify(s["item"], {"complete_month_certified": True}, cutoff)
        assert result["latest_available_period"] == "2026M09"
        assert result["source_artifact_sha256"] == rows[1]["sha256"]
        assert result["source_availability_observed_at"] == records[1]["downloaded_at"]
    assert attack == "sidecar_race" or inventory == {
        str(p.relative_to(s["bronze"].parents[1])): availability.sha(p)
        for p in s["bronze"].parents[1].rglob("*")
        if p.is_file()
    }


def test_latest_availability_cannot_be_a_boolean_or_unsupported_family(physical):
    s = physical
    persist(s)
    with pytest.raises(ValueError):
        availability.preflight(True, Path(s["item"]["workspace"]))
    s["item"]["product"] = "gdelt"
    with pytest.raises(ValueError, match="not yet implemented"):
        availability.verify(s["item"], {}, CUTOFF)


def test_source_plain_format_label_does_not_hide_an_older_current_index(physical):
    # Both forms were observed in official captures; month/year/extension stay exact.
    state = physical
    index = state["bronze"] / state["receipt"]["items"][0]["source_file"]
    body = index.read_text().replace(" (PDF)", "")
    index.write_text(body)
    assert availability.latest_aifa(index) == ("2026M09", URL)
    index.write_text(body.replace("Sep-2026", "Jul-2026").replace("Septiembre 2026", "Julio 2026"))
    assert availability.latest_aifa(index) == ("2026M07", URL.replace("Sep-2026", "Jul-2026"))
