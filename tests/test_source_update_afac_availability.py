"""Synthetic binding contracts; real AFAC dossier replay is separate evidence."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from src.common.storage import save_bronze
from src.ingest.afac.download import DATATUR_CATALOG_URL, DATATUR_DATABASE_URL
from src.source_updates import availability, availability_afac
from src.source_updates.catalog import ROOT

PDF = "https://datatur.sectur.gob.mx/Documentoscompartidos/afac/AFAC_2026_08.pdf"
CUTOFF = "2026-10-27T07:00:00+00:00"


@pytest.fixture
def dossier():
    root = ROOT / "tmp/source-updates" / ("test-afac-availability-" + uuid4().hex)
    collection, candidate = root / "collection", root / "candidate"
    bronze = collection / "data/bronze"
    body = f'<a href="{PDF}"></a><a href="{DATATUR_DATABASE_URL}">Base de datos</a>'.encode()
    rows = []
    for i, (role, content, url, ext) in enumerate(
        [
            ("catalog", body, DATATUR_CATALOG_URL, "html"),
            ("pdf", b"synthetic PDF", PDF, "pdf"),
            ("database", b"synthetic ZIP", DATATUR_DATABASE_URL, "zip"),
        ]
    ):
        path = save_bronze(
            content,
            "afac",
            role,
            "2026M08",
            ext,
            url,
            "httpx",
            bronze_root=bronze,
            downloaded_at=datetime(2026, 10, 27, 6, 45, i, tzinfo=UTC),
            http_status=200,
        )
        rows.append(
            dict(
                id=role,
                product="afac_carriers",
                requested_period="2026M08",
                status="collected_catalog" if role == "catalog" else "collected_unvalidated",
                source_file=path.relative_to(bronze).as_posix(),
                sha256=availability.sha(path),
                source_url=url,
                response_url=url,
                bytes=len(content),
                http_status=200,
            )
        )
    rid = "b" * 32
    receipt = dict(
        run_id=rid,
        mode="collection",
        status="collected_unvalidated",
        activation="none",
        publication="not_authorized",
        started_at="2026-10-27T06:44:59+00:00",
        finished_at="2026-10-27T06:45:03+00:00",
        items=rows,
    )
    receipt_path = collection / "receipts" / f"collection-{rid}.json"
    receipt_path.parent.mkdir()
    receipt_path.write_text(json.dumps(receipt))
    native = candidate / "data/silver/afac_carriers_source_native.parquet"
    native.parent.mkdir(parents=True)
    pd.DataFrame(
        [dict(source_file=r["source_file"], source_hash=r["sha256"], source_system="afac") for r in rows[1:]]
    ).to_parquet(native)
    item = dict(
        product="afac_carriers",
        adapter="carrier_source",
        period="2026M08",
        workspace=str(candidate),
        availability=dict(
            workspace=str(collection),
            run_id=rid,
            catalog_item="catalog",
            artifact_items={"pdf": "pdf", "database": "database"},
        ),
    )
    yield dict(item=item, native=native, rows=rows, bronze=bronze, receipt_path=receipt_path)
    shutil.rmtree(root)


@pytest.mark.parametrize(
    "attack",
    [None, "single", "missing_role", "same_id", "unused", "swapped", "month", "coverage", "caveat", "writer"],
)
def test_reported_dossier_needs_both_used_current_originals_and_preserves_partial_scope(dossier, attack):
    s = dossier
    result = dict(
        monthly_coverage_verified=True,
        complete_month_certified=False,
        source_declares_incomplete_international_reporting=True,
    )
    binding = s["item"]["availability"]
    if attack == "single":
        binding.pop("artifact_items")
        binding["artifact_item"] = "pdf"
    elif attack == "missing_role":
        binding["artifact_items"].pop("database")
    elif attack == "same_id":
        binding["artifact_items"]["database"] = "pdf"
    elif attack in {"unused", "swapped"}:
        frame = pd.read_parquet(s["native"])
        if attack == "unused":
            frame = frame.iloc[:1]
        else:
            frame["source_hash"] = frame.source_hash.iloc[::-1].to_numpy()
        frame.to_parquet(s["native"])
    elif attack == "month":
        result["complete_month_certified"] = True
    elif attack == "coverage":
        result["monthly_coverage_verified"] = False
    elif attack == "caveat":
        result.pop("source_declares_incomplete_international_reporting")
    elif attack == "writer":
        (Path(binding["workspace"]) / ".source-update.lock").touch()
    if attack:
        with pytest.raises(ValueError):
            availability.verify(s["item"], result, CUTOFF)
    else:
        proof = availability.verify(s["item"], result, CUTOFF)
        assert proof["latest_available_period"] == "2026M08"
        assert set(proof["source_artifacts"]) == {"pdf", "database"}
        assert proof["reported_dossier_verified"] is True
        assert proof["complete_month_certified"] is False
        assert proof["source_declares_incomplete_international_reporting"] is True


@pytest.mark.parametrize(
    "attack",
    [None, "new_pdf", "opaque", "new_format", "new_database", "missing_database", "ambiguous", "base"],
)
def test_actual_url_grammar_never_invents_blank_afac_anchor_labels(tmp_path, attack):
    text = f'<a href="{PDF}"></a><a href="{DATATUR_DATABASE_URL}">Base de datos</a>'
    if attack == "new_pdf":
        text += '<a href="/download/opaque.pdf">AFAC septiembre 2026</a>'
    elif attack == "opaque":
        text += '<a href="/download?id=September">AFAC Septiembre 2026 PDF</a>'
    elif attack == "new_format":
        text += '<a href="/Documentoscompartidos/afac/AFAC_2026_09.docx">AFAC Septiembre 2026</a>'
    elif attack == "new_database":
        text += '<a href="/Documentoscompartidos/afac/DB_AFAC_2026.zip">Base de datos</a>'
    elif attack == "missing_database":
        text = f'<a href="{PDF}"></a>'
    elif attack == "ambiguous":
        text += f'<a href="{PDF}?edition=2"></a>'
    elif attack == "base":
        text += '<base href="https://other.example/">'
    path = tmp_path / "index.html"
    path.write_text(text)
    if attack:
        with pytest.raises(ValueError):
            availability_afac.latest(path)
    else:
        assert availability_afac.latest(path) == ("2026M08", {"pdf": PDF, "database": DATATUR_DATABASE_URL})
