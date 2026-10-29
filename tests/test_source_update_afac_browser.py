"""Manual-handoff contracts use synthetic bytes; real workbook replay is separate."""

import hashlib
import json
import os
import shutil
from uuid import uuid4
from zipfile import ZipFile

import pytest

from src.source_updates import availability_afac_manual as subject
from src.source_updates.catalog import ROOT


@pytest.fixture
def packet():
    root = ROOT / "tmp/source-updates" / ("pytest-afac-browser-" + uuid4().hex)
    root.mkdir()
    path = root / "packet.zip"
    name = "producto-aeropuertos-2006-2026-sep-27102026.xlsx"
    url = "https://www.gob.mx/cms/uploads/attachment/file/1112825/" + name
    body = b"synthetic bytes, deliberately not an XLSX and never passed off as source extraction"
    manifest = dict(
        name=name,
        download_url=url,
        index_url=subject.ENTRY,
        bytes=len(body),
        sha256=hashlib.sha256(body).hexdigest(),
        download_completed_utc="2026-10-28T23:38:21Z",
    )
    index = (
        'heading "Estadísticas" [level=1]\nEstadística Operacional de Aeropuertos. Statistics by Airport\n'
        "/url: " + url + "\n/url: https://www.gob.mx/cms/uploads/attachment/file/1112827/"
        "producto-aeropuertos-es-sep-26-27102026.pdf\n"
        "/url: https://www.gob.mx/cms/uploads/attachment/file/1112826/"
        "producto-aeropuertos-en-sep-26-27102026.pdf\n"
    )

    def write(*, changes=None, snapshot=index, data=body):
        with ZipFile(path, "w") as z:
            z.writestr(name, data)
            z.writestr("acquisition-manifest.json", json.dumps({**manifest, **(changes or {})}))
            z.writestr("afac-statistics-index.txt", snapshot)
        os.setxattr(path, "user.library-file-id", ("libfile_" + "a" * 32).encode())

    write()
    yield path, write, manifest, index
    shutil.rmtree(root)


def test_packet_keeps_real_observation_and_distinguishes_index_text_from_original_HTML(packet):
    path, _, manifest, _ = packet
    _, received, proof = subject.packet(path, "2026-10-28T23:59:00Z")
    assert received == manifest and proof["period"] == "2026M09"
    assert proof["source_observed_at"] == "2026-10-28T23:38:21Z"
    assert proof["source_http_status_observed"] is None
    assert proof["index_representation"] == "browser_accessibility_snapshot_text_not_original_HTML"
    assert proof["source_capture_method"] == "native_browser_download"


def test_wrong_native_download_identity_period_link_hash_and_chronology_cannot_renew_source(packet):
    path, write, manifest, index = packet
    for changes in (
        {"sha256": "0" * 64},
        {"bytes": 1},
        {"index_url": subject.ENTRY + "?other=1"},
        {"download_url": manifest["download_url"].replace("gob.mx", "gob.mx.evil.invalid")},
        {"download_completed_utc": "2026-10-29T23:38:21Z"},
    ):
        write(changes=changes)
        with pytest.raises(ValueError):
            subject.packet(path, "2026-10-28T23:59:00Z")
    for snapshot in (
        index.replace("sep-26", "ago-26"),
        index.replace('heading "Estadísticas"', "wrong"),
        index + "/url: " + manifest["download_url"] + "\n",
    ):
        write(snapshot=snapshot)
        with pytest.raises(ValueError):
            subject.packet(path, "2026-10-28T23:59:00Z")
    write(data=b"changed")
    with pytest.raises(ValueError):
        subject.packet(path, "2026-10-28T23:59:00Z")
    write()
    with pytest.raises(ValueError):
        subject.packet(path, "2026-10-29T23:59:00Z")


def test_manual_binding_cannot_overlap_candidate_or_escape_imports(packet):
    path, _, _, _ = packet
    binding = dict(
        source_scope=subject.SCOPE,
        workspace=str(path.parent),
        run_id="a" * 32,
        artifact_item="airports",
        browser_packet="imports/packet.zip",
    )
    with pytest.raises(ValueError, match="disjoint"):
        subject.preflight(binding, str(path.parent / "candidate"))
    for relative in ("../packet.zip", "/tmp/packet.zip", "imports/a/packet.zip"):
        with pytest.raises(ValueError):
            subject.preflight({**binding, "browser_packet": relative}, str(path.parent.parent / "another"))
