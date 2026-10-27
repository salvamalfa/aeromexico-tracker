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


def pages():
    # Contract fixture; independent real Poppler/PDF comparisons are retained separately.
    text = (
        "Volaris reporta resultados de tráfico de septiembre de 2026: "
        "Ciudad de México, México, 6 de octubre de 2026 – "
        "Controladora Vuela Compañía de Aviación, S.A.B. de C.V. reporta sus "
        "resultados preliminares de tráfico de septiembre de 2026. "
        "Septiembre 2026 Septiembre 2025 Variación Acumulado a septiembre 2026 "
        "Acumulado a septiembre 2025 Variación "
    )
    rows = (
        "Doméstico 1,366 1,420 (3.8%) 14,097 13,853 1.8% "
        "Internacional 1,010 884 14.2% 9,813 8,581 14.4% Total 2,375 2,304 3.1% 23,910 22,434 6.6%",
        "Doméstico 1,548 1,599 (3.2%) 15,910 15,621 1.9% "
        "Internacional 1,266 1,163 8.8% 12,160 11,069 9.9% Total 2,814 2,762 1.9% 28,071 26,689 5.2%",
        "Doméstico 88.2% 88.8% (0.6) pp 88.6% 88.7% (0.1) pp "
        "Internacional 79.8% 76.0% 3.8 pp 80.7% 77.5% 3.2 pp Total 84.4% 83.4% 1.0 pp 85.2% 84.1% 1.1 pp",
        "Doméstico 1,786 1,762 1.4% 18,071 16,889 7.0% "
        "Internacional 689 614 12.2% 6,720 5,916 13.6% Total 2,475 2,376 4.2% 24,791 22,804 8.7%",
    )
    for (heading, *_), row in zip(source.METRICS, rows, strict=True):
        text += heading + " " + row + " "
    text += (
        "La información incluida en este reporte no ha sido auditada "
        "Las cifras están redondeadas para efectos prácticos."
    )
    glossary = (
        "Glosario Revenue passenger miles (RPMs): Número de asientos vendidos a pasajeros multiplicado "
        "por el número de millas voladas. Available seat miles (ASMs): Asientos disponibles "
        "multiplicados por el número de millas voladas. Factor de ocupación: Los RPMs divididos "
        "entre los ASMs y expresado en porcentaje. Pasajeros: Número total de pasajeros que han "
        "reservado en todos los segmentos de vuelo."
    )
    return [text, glossary]


def original():
    return dict(
        source_system="volaris_ir",
        source_url=source.PDF,
        source_file="volaris.pdf",
        sha256="a" * 64,
        downloaded_at="2026-10-27T18:07:43Z",
    )


def test_full_month_ytd_and_variations_preserve_native_rounding_and_bookings():
    frame, result = source.texts(pages(), "2026M09", original())
    assert len(frame) == 48 and result["reported_variations"] == frame.reported_change.notna().sum() == 24
    assert set(frame.period_type) == {"month", "year_to_date"}
    assert set(frame.period_id) == {"2026M09", "2025M09", "2026YTD09", "2025YTD09"}
    assert frame.is_preliminary.all() and frame.is_unaudited.all()
    assert frame.passenger_definition.eq("booked_flight_segments_not_observed_flown_passengers").all()
    assert frame.loc[frame.metric_key.eq("load_factor"), "reported_change_unit"].eq("percentage_points").all()
    assert frame.loc[frame.metric_key.ne("load_factor"), "reported_change_unit"].eq("relative_percent").all()
    assert [v["difference_native_units"] for v in result["rounding_reconciliation_deltas"]] == [-1, 1, -1, -1]
    assert result["source_report_date_as_reported"] == "2026-10-06"
    assert result["first_publication_date"] is result["release_lag_days"] is None


def test_material_period_units_definitions_grid_and_dates_fail_closed():
    for old, new in (
        ("Septiembre 2026 Septiembre 2025", "Septiembre 2025 Septiembre 2026"),
        ("RPMs (millones, itinerado", "RPKs (millones, itinerado"),
        ("han reservado", "han volado"),
        ("millas voladas.", "kilómetros volados."),
        ("preliminares de tráfico", "finales de tráfico"),
        ("1,366", "2,000"),
        ("84.4%", "94.4%"),
        ("3.8 pp", "3.8%"),
        ("Doméstico 1,786 1,762 1.4% 18,071 16,889 7.0%", ""),
        ("6 de octubre de 2026", "31 de octubre de 2026"),
    ):
        changed = pages()
        assert any(old in page for page in changed)
        with pytest.raises(ValueError):
            source.texts([page.replace(old, new) for page in changed], "2026M09", original())
    for row, period in (
        ({**original(), "source_system": "sec"}, "2026M09"),
        ({**original(), "source_url": source.PDF + "?other=1"}, "2026M09"),
        (original(), "2026Q3"),
    ):
        with pytest.raises(ValueError):
            source.texts(pages(), period, row)
