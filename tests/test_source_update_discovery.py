import pytest

from src.source_updates.discovery import select_documents


def test_afac_selection_comes_from_present_links_not_filename_templates(tmp_path):
    path = tmp_path / "catalog.html"
    path.write_text('<a href="/Documentoscompartidos/afac/AFAC_2026_08.pdf">Agosto</a>')
    selected = select_documents("afac_carriers", path, "2026M08")
    item = selected["items"][0]
    assert item["url"] == "https://datatur.sectur.gob.mx/Documentoscompartidos/afac/AFAC_2026_08.pdf"
    assert item["relative_dir"] == "afac/2026/08"
    assert item["source_system"] == "afac"
    with pytest.raises(ValueError, match="absent"):
        select_documents("afac_carriers", path, "2026M09")


def test_unsupported_catalogue_product_requires_its_actual_procedure(tmp_path):
    with pytest.raises(ValueError, match="manual procedure"):
        select_documents("viva_financials", tmp_path / "missing", "2026M09")


def test_viva_recipe_routes_only_actual_permitted_links(tmp_path):
    path = tmp_path / "catalog.html"
    url = "https://cdn.investorcloud.net/VivaAerobus/InformacionFinanciera/SalaPrensa/2021-12-07-Trafico-noviembre-2021.pdf"
    path.write_text(f'<a href="{url}">November report</a>')
    assert select_documents("viva_traffic", path, "2021M11")["items"][0]["url"] == url
    with pytest.raises(ValueError, match="absent"):
        select_documents("viva_traffic", path, "2026M09")


def test_viva_explicit_bmv_selection_cli_does_not_read_or_download(capsys):
    import json

    from src.source_updates.__main__ import main

    url = "https://www.bmv.com.mx/docs-pub/eventemi/eventemi_1594478_1.pdf"
    args = ["recipe", "--product", "viva_traffic", "--output", "selection", "--period", "2026M09"]
    assert main([*args, "--source-url", url]) == 0
    item = json.loads(capsys.readouterr().out)["items"][0]
    assert item["url"] == url and item["product"] == "viva_traffic" and item["period"] == "2026M09"
    assert main([*args, "--source-url", url, "--catalog-file", "missing.html"]) == 1
    assert "without catalog-file" in capsys.readouterr().out
    assert main([*args, "--source-url", url.replace("www.bmv.com.mx", "unapproved.example")]) == 1
    assert "catalogue hosts" in capsys.readouterr().out


def test_airport_latest_is_from_label_and_missing_month_is_not_invented(tmp_path):
    path = tmp_path / "catalog.html"
    path.write_text(
        '<a href="https://ir.oma.aero/actual.pdf">OMA September 2026 Total Passenger Traffic</a>'
        '<a href="https://ir.oma.aero/old.pdf">OMA August 2026 Total Passenger Traffic</a>'
    )
    chosen = select_documents("oma_traffic", path, "latest")
    assert chosen["items"][0]["url"] == "https://ir.oma.aero/actual.pdf"
    assert chosen["discovery"]["linked_period"] == "2026M09"
    with pytest.raises(ValueError, match="absent"):
        select_documents("oma_traffic", path, "2026M10")


def test_aifa_cumulative_label_selects_end_month_and_keeps_host_guard(tmp_path):
    path = tmp_path / "catalog.html"
    path.write_text(
        '<a href="https://aifa-repositorio.s3.us-east-1.amazonaws.com/actual.xlsx">'
        'Numeralia Aeroportuaria de Enero a Julio 2026 - Formato XLSX</a>'
    )
    assert select_documents("aifa_traffic", path, "latest")["items"][0]["period"] == "2026M07"
    with pytest.raises(ValueError, match="absent"):
        select_documents("aifa_traffic", path, "2026M01")
    path.write_text(path.read_text().replace("aifa-repositorio.s3.us-east-1.amazonaws.com", "evil.example"))
    with pytest.raises(ValueError, match="catalogue hosts"):
        select_documents("aifa_traffic", path, "latest")
