from io import BytesIO
from pathlib import Path
import shutil
from uuid import uuid4
import zipfile

import pytest

from src.common import storage
from src.common.storage import save_bronze
from src.config import ProjectPaths, SOURCE_URLS
from src.pipeline.offline import block_network
from src.source_updates import bmv
from src.source_updates.catalog import ROOT
from src.parse.bmv import xbrl


CATALOG = b"""<table><tr><td>AERO</td><td>Aeromexico</td><td>13/07/2026</td><td><a href="/docs-pub/visor/visorXbrl.html?docins=../ifrsxbrl/ifrsxbrl_1573911_2026-02_1.zip">Trimestre 2 2026</a></td></tr><tr><td>VOLAR</td><td>Volaris</td><td>13/07/2026</td><td><a href="/docs-pub/visor/visorXbrl.html?docins=../ifrsxbrl/ifrsxbrl_1234567_2026-02_1.zip">Trimestre 2 2026</a></td></tr></table>"""
ZIP_URL = "https://www.bmv.com.mx/docs-pub/ifrsxbrl/ifrsxbrl_1573911_2026-02_1.zip"


@pytest.fixture
def candidate(monkeypatch):
    root = ROOT / "tmp/source-updates" / ("bmv-test-" + uuid4().hex)
    paths = ProjectPaths(root=root)
    for module in (bmv, storage, xbrl):
        monkeypatch.setattr(module, "PATHS", paths)
    save_bronze(
        CATALOG,
        "bmv",
        "portal_catalog",
        "current",
        "html",
        SOURCE_URLS["bmv_xbrl"],
        "manual",
        bronze_root=paths.bronze,
    )
    yield paths
    shutil.rmtree(root)


def preserve_zip(paths, content):
    return save_bronze(
        content, "bmv", "AERO_xbrl_package", "2026Q2", "zip", ZIP_URL, "manual", bronze_root=paths.bronze
    )


def test_real_selected_bmv_member_is_registered_without_fetching_other_catalog_rows(candidate):
    fixture = Path(__file__).parent / "fixtures/bmv/AERO_2026Q2.zip"
    preserve_zip(candidate, fixture.read_bytes())
    with block_network():
        selected = bmv.register_members()
        packages = xbrl.rebuild_package_index_from_bronze(zip_urls=selected)
    assert selected == (ZIP_URL,)
    assert packages["ticker"].to_list() == ["AERO"]
    assert packages["member_source_url"][0].startswith(ZIP_URL + "#member=")
    assert (candidate.bronze / packages["member_source_file"][0]).is_file()


@pytest.mark.parametrize(
    "members", [[("../escape.json", "{}")], [("a.json", "{}"), ("b.json", "{}")], [("a.json", "[]")]]
)
def test_invalid_bmv_archives_do_not_register_members(candidate, members):
    content = BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        for name, body in members:
            archive.writestr(name, body)
    preserve_zip(candidate, content.getvalue())
    manifest = candidate.bronze / "_manifest.jsonl"
    before = manifest.read_bytes()
    with pytest.raises(ValueError):
        bmv.register_members()
    assert manifest.read_bytes() == before


def test_bmv_selection_uses_only_actual_catalog_period_and_requested_issuer(tmp_path):
    path = tmp_path / "catalog.html"
    path.write_bytes(CATALOG)
    chosen = bmv.selection(path, "2026Q2", ("AERO",))
    assert [i["url"] for i in chosen["items"]] == [ZIP_URL]
    with pytest.raises(ValueError, match="absent"):
        bmv.selection(path, "2026Q3", ("AERO",))


def test_new_catalogue_cannot_discard_retained_published_packages(candidate):
    preserve_zip(candidate, (Path(__file__).parent / "fixtures/bmv/AERO_2026Q2.zip").read_bytes())
    newer = b"<table>" + CATALOG[CATALOG.index(b"<tr><td>VOLAR") :]
    save_bronze(
        newer,
        "bmv",
        "portal_catalog",
        "current",
        "html",
        SOURCE_URLS["bmv_xbrl"],
        "manual",
        bronze_root=candidate.bronze,
    )
    reports = bmv.preserved_reports(bmv.verify_bronze(candidate.root))
    assert ZIP_URL in {r.zip_url for r in reports}
    with block_network():
        selected = bmv.register_members()
        result = xbrl.rebuild_package_index_from_bronze(zip_urls=selected, reports=reports)
    assert result["ticker"].to_list() == ["AERO"]
