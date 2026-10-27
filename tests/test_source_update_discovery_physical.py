"""Physical index contracts; actual official extractions are recorded separately."""

import pytest

from src.source_updates.availability_airports import latest as airport
from src.source_updates.availability_viva import latest as viva


@pytest.mark.parametrize("product", ["aicm_traffic", "oma_traffic"])
@pytest.mark.parametrize(
    "attack", [None, "newer_unknown", "new_title", "latest_ambiguous", "old_alias", "unclassified"]
)
def test_airport_latest_selection_is_explicit_and_fail_closed(tmp_path, product, attack):
    aicm = product == "aicm_traffic"
    url = (
        "https://www.aicm.com.mx/Estadisticas/September.pdf"
        if aicm
        else "https://ir.oma.aero/traffic/September.pdf"
    )
    title = (
        "Estadísticas del AICM a Septiembre de 2026"
        if aicm
        else "OMA's September 2026 Total Passenger Traffic"
    )
    text = f'<a href="{url}">{title}</a><a href="{url}"></a>'
    if attack == "newer_unknown":
        unknown_title = title.replace("Septiembre", "Octulbre").replace("September", "Octember")
        text += f'<a href="{url.replace("September", "October")}">{unknown_title}</a>'
    elif attack == "latest_ambiguous":
        text += f'<a href="{url}?edition=2">{title}</a>'
    elif attack == "old_alias":
        text += f'<a href="{url}">{title.replace("2026", "2025")}</a>'
    elif attack == "unclassified":
        text += f'<a href="{url.replace("September", "October")}"></a>'
    elif attack == "new_title":
        title = "Estadísticas del AICM — Octubre de 2026" if aicm else "OMA's October 2026 Traffic Report"
        host = "www.aicm.com.mx" if aicm else "ir.oma.aero"
        text += f'<a href="https://{host}/download/opaque.pdf">{title}</a>'
    path = tmp_path / "index.html"
    path.write_text(text)
    if attack:
        with pytest.raises(ValueError):
            airport(path, product)
    else:
        assert airport(path, product) == ("2026M09", url)


def bmv_row(title, url="/docs-pub/eventemi/eventemi_1594478_1.pdf"):
    return (
        f'<tr><td>09-10-2026 15:14</td><td>{title}</td><td><a href="{url}">PDF</a>'
        '<a href="/visor/visorXbrl.html?docins=../eventemi/a.zip">XBRL</a></td></tr>'
    )


@pytest.mark.parametrize(
    "attack", [None, "identity", "profile", "layout", "title", "zip_only", "ambiguous", "unknown_month"]
)
def test_bmv_viva_traffic_uses_issuer_month_and_pdf_never_xbrl(tmp_path, attack):
    title = "VIVA REPORTA RESULTADOS DE TRÁFICO MENSUAL DE SEPTIEMBRE 2026"
    profile = '<div class="info-profile"><span class="key">GVIVA</span>'
    profile += "<h3>GRUPO VIVA AEROBUS SA DE CV</h3></div>"
    text = profile + "<table>" + bmv_row(title) + "</table>"
    if attack == "identity":
        text = text.replace("GRUPO VIVA", "OTHER")
    elif attack == "title":
        text = text.replace("SEPTIEMBRE 2026", "SEPTIEMBRE 2026 forecast")
    elif attack == "zip_only":
        text = text.replace("eventemi_1594478_1.pdf", "eventemi_1594478_1.zip")
    elif attack == "ambiguous":
        text += bmv_row(title, "/docs-pub/eventemi/eventemi_1594478_2.pdf")
    elif attack == "unknown_month":
        text += bmv_row(title.replace("SEPTIEMBRE", "OCTUBREZ"))
    elif attack == "profile":
        text = text.replace("GVIVA", "OTHER").replace("GRUPO VIVA AEROBUS SA DE CV", "OTHER ISSUER")
        text += "<aside>GRUPO VIVA AEROBUS SA DE CV</aside>"
    elif attack == "layout":
        text += f'<table><tr><td colspan="3">{title}</td></tr></table>'
    path = tmp_path / "index.html"
    path.write_text(text)
    if attack:
        with pytest.raises(ValueError):
            viva(path)
    else:
        assert viva(path) == ("2026M09", "https://www.bmv.com.mx/docs-pub/eventemi/eventemi_1594478_1.pdf")
        from src.source_updates.discovery import select_documents

        selected = select_documents("viva_traffic", path, "latest")
        assert selected["items"][0]["url"] == viva(path)[1]
        assert selected["items"][0]["period"] == "2026M09"
