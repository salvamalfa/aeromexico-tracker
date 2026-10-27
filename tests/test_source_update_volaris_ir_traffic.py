"""Exact authorized IR origins, separated from SEC; real extraction checked independently."""

import copy
import shutil
from uuid import uuid4

import httpx
import pytest

from src.source_updates import volaris_traffic as source
from src.source_updates.catalog import ROOT
from src.source_updates.collection import collect, selection_plan
from src.source_updates.retained import public_original


@pytest.fixture
def workspace():
    path = ROOT / "tmp/source-updates" / ("test-volaris-ir-" + uuid4().hex)
    yield path
    if path.exists():
        shutil.rmtree(path)


def test_admission_is_exact_document_and_host_for_network_and_retained_sources(workspace):
    selected = source.selection()
    plan = selection_plan(selected, workspace)
    assert plan["base_requests"] == 2 and plan["paid_requests"] == 0 and not workspace.exists()
    for url in (
        source.PDF.replace("filemanager-cdn", "other.filemanager-cdn"),
        source.PDF.replace("d13b9b6b", "a13b9b6b"),
        source.PDF + "?download=1",
        source.PDF + "#data",
        source.PDF.replace("https://", "http://"),
        source.ENTRY.replace("reportes-de-trafico/", "otra-pagina/"),
    ):
        changed = copy.deepcopy(selected)
        changed["items"][1]["url"] = url
        with pytest.raises(ValueError):
            selection_plan(changed, workspace)
        with pytest.raises(ValueError):
            public_original(dict(source_system="volaris_ir", source_url=url))
    assert not workspace.exists()


def test_redirect_to_other_document_on_admitted_host_is_rejected_before_request(workspace):
    calls = []

    class Client:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def request(self, method, url, **kwargs):
            calls.append(url)
            return httpx.Response(
                302,
                headers={"Location": source.PDF.replace("d13b9b6b", "a13b9b6b")},
                request=httpx.Request(method, url),
            )

    selected = source.selection()
    selected["items"] = selected["items"][1:]
    result = collect(selected, workspace, execute=True, client_factory=lambda *a, **k: Client())
    assert calls == [source.PDF]
    assert result["items"][0]["status"] == "access_or_payload_failed"
    assert result["status"] == "incomplete"


def test_monthly_ir_is_required_without_relabeling_it_as_sec_financials():
    from src.source_updates.catalog import bronze_aliases, product_map
    from src.source_updates.global_readiness import policy

    products = product_map()
    assert products[source.PRODUCT]["cadence"] == "monthly"
    assert products["volaris_sec"]["cadence"] == "quarterly"
    assert bronze_aliases(source.PRODUCT) == ("volaris_ir",)
    assert bronze_aliases("volaris_sec") == ("sec",)
    assert source.PRODUCT in policy()["monthly"]["required"]
    assert "volaris_sec" in policy()["quarterly"]["required"]
