from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import re

from bs4 import BeautifulSoup
import pytest

from src.config import PATHS
from src.dashboard.executive_summary import (
    EXECUTIVE_QUERY,
    build_executive_payload,
    load_executive_history,
)
from src.dashboard.executive_summary_html import (
    DEFAULT_OUTPUT,
    render_executive_html,
)


def _payload_from_html(document: str) -> dict[str, object]:
    soup = BeautifulSoup(document, "html.parser")
    node = soup.select_one("#dashboard-data")
    assert node is not None
    return json.loads(node.string)


def test_payload_uses_every_complete_comparable_backend_quarter() -> None:
    history = load_executive_history()
    payload = build_executive_payload()
    assert payload["metadata"]["quarter_count"] == len(history) == 22
    assert payload["metadata"]["first_period"] == "2021Q1"
    assert payload["metadata"]["last_period"] == "2026Q2"
    assert [record["period_id"] for record in payload["records"]] == history[
        "period_id"
    ].tolist()
    assert "v_aeromexico_quarterly" in EXECUTIVE_QUERY


def test_payload_reconciles_latest_anchor_and_margin_formula() -> None:
    payload = build_executive_payload()
    latest = payload["records"][-1]
    assert latest["period_id"] == "2026Q2"
    assert latest["passengers"] == 6_014_000.0
    assert math.isclose(latest["ask_km"], 14_896_088_064.000002)
    assert math.isclose(latest["load_factor_reported"], 0.849)
    assert math.isclose(latest["rask_cents_per_km"], 9.941939075797343)
    assert math.isclose(latest["cask_cents_per_km"], 9.50697924123121)
    assert math.isclose(
        latest["unit_margin_cents_per_km"],
        latest["rask_cents_per_km"] - latest["cask_cents_per_km"],
        abs_tol=1e-12,
    )


def test_qoq_yoy_and_typed_deltas_are_correct() -> None:
    payload = build_executive_payload()
    latest = payload["views"]["2026Q2"]
    kpis = {item["key"]: item for item in latest["kpis"]}
    assert math.isclose(
        kpis["passengers"]["qoq"]["raw"], 6_014_000 / 5_791_000 - 1
    )
    assert math.isclose(
        kpis["passengers"]["yoy"]["raw"], 6_014_000 / 6_180_000 - 1
    )
    assert kpis["load_factor_reported"]["qoq"]["display"] == "+0.5 pp"
    assert kpis["load_factor_reported"]["yoy"]["display"] == "-0.8 pp"
    assert latest["margin_qoq"]["display"] == "-0.68 ¢ USD"
    assert latest["margin_yoy"]["display"] == "-1.18 ¢ USD"


def test_missing_comparables_are_explicit_not_zero() -> None:
    payload = build_executive_payload()
    first = payload["views"]["2021Q1"]
    for kpi in first["kpis"]:
        assert kpi["qoq"] == {
            "available": False,
            "raw": None,
            "display": "No disponible",
            "direction": "na",
        }
        assert kpi["yoy"] == {
            "available": False,
            "raw": None,
            "display": "No disponible",
            "direction": "na",
        }


def test_html_contains_only_one_executive_view_and_five_kpis() -> None:
    document = render_executive_html(build_executive_payload())
    soup = BeautifulSoup(document, "html.parser")
    assert len(soup.select("main[data-testid='executive-summary-root']")) == 1
    assert len(soup.select(".kpi-card")) == 5
    assert len(soup.select("nav, [role='tablist'], [role='tab']")) == 0
    assert "Aeroméxico Tracker" in soup.get_text(" ", strip=True)
    assert "Estructura de datos" not in soup.get_text(" ", strip=True)


def test_html_embeds_all_quarters_and_uses_accessible_period_stepper() -> None:
    document = render_executive_html(build_executive_payload())
    soup = BeautifulSoup(document, "html.parser")
    assert soup.select_one("#period-selector") is None
    assert soup.select_one("#period-prev")["aria-label"] == "Ir al trimestre anterior"
    assert soup.select_one("#period-next")["aria-label"] == "Ir al trimestre siguiente"
    assert soup.select_one("#period-display") is not None
    embedded = _payload_from_html(document)
    assert embedded == build_executive_payload()
    assert len(embedded["records"]) == 22


def test_html_has_expected_charts_narrative_and_disclosures() -> None:
    document = render_executive_html(build_executive_payload())
    soup = BeautifulSoup(document, "html.parser")
    assert {node["id"] for node in soup.select(".chart[id]")} == {
        "unit-chart",
        "volume-chart",
        "load-chart",
    }
    assert len(soup.select("details.disclosure")) == 1
    assert len(soup.select(".history-item")) == 0
    assert len(soup.select("tbody tr")) == 22
    assert "RASK vs. CASK + Margen unitario" in soup.get_text(" ", strip=True)
    assert "Precio vs. Volumen de pasajeros" in soup.get_text(" ", strip=True)


def test_annotated_copy_order_and_delta_coloring_are_implemented() -> None:
    document = render_executive_html(build_executive_payload())
    soup = BeautifulSoup(document, "html.parser")
    text = soup.get_text(" ", strip=True)
    assert "AERO · NYSE / BMV" not in text
    assert "trimestres comparables" not in text
    assert "Fuente: v_aeromexico_quarterly Grupo Aeroméxico" not in text
    assert "Precio vs. Volumen de pasajeros" in text
    assert "Factor de ocupación vs. RASK" in text
    assert "Correlación positiva clara" not in text
    assert "Mayor ocupación tiende a coincidir con mayor RASK." in text
    assert "Las barras muestran el margen unitario en ¢ USD por ASK-km para cada trimestre." in text
    assert "En 1T21–3T22" not in soup.select_one(".table-wrap").get_text(" ", strip=True)
    assert len(soup.select("tbody tr.year-separator")) == 5
    assert "Vs. trimestre" not in text
    assert "vs. trimestre anterior" in text
    assert "Conclusiones clave" not in text
    assert "Ver análisis de trimestres anteriores" not in text
    assert "¢ USD" in text
    sections = [node for node in soup.select_one("main.page-shell").find_all(recursive=False)]
    assert sections.index(soup.select_one(".kpi-grid")) < sections.index(
        soup.select_one(".narrative-card")
    ) < sections.index(soup.select_one("#unit-heading").find_parent("section"))
    assert soup.select_one("#narrative-headline") is None
    assert soup.select_one("#insight-list") is None
    assert soup.select_one("#executive-reading-title").get_text(" ", strip=True) == "Lectura ejecutiva · —"
    assert soup.select_one("#narrative-copy").name == "p"
    assert soup.select_one("#narrative-copy").get_text(strip=True) == (
        "Contenido por definir. Aquí irá el output del agente de análisis por trimestre."
    )
    assert soup.select_one("#unit-range option[selected]").get_text(strip=True) == "Historia completa"
    assert len(soup.select(".table-metric small")) == 22 * 6
    app_script = soup.select_one("script[data-runtime='executive-prototype']").string
    assert "delta-${comparison.direction}" in app_script
    assert "yearColors" in app_script
    assert 'showlegend: false' in app_script
    assert 'tickangle: 0' in app_script
    assert "signedTwoDecimals" in app_script
    assert "Margen %{customdata[1]}" in app_script
    assert "zorder: 10" in app_script
    assert "zorder: 0" in app_script
    assert 'textposition: "none"' in app_script

    css = (PATHS.root / "src/dashboard/assets/executive_summary.css").read_text(encoding="utf-8")
    assert "background: var(--brand-blue-dark);" in css
    assert ".analysis-placeholder" in css
    assert "border-top: 2px solid var(--ink) !important;" in css


def test_html_is_self_contained_and_has_no_remote_runtime() -> None:
    document = render_executive_html(build_executive_payload())
    soup = BeautifulSoup(document, "html.parser")
    assert not soup.select(
        "script[src], link[href], iframe, img[src], video[src], audio[src], source[src]"
    )
    assert len(soup.select("script[data-runtime='plotly-local']")) == 1
    app_script = soup.select_one("script[data-runtime='executive-prototype']").string.lower()
    for primitive in (
        "fetch(",
        "xmlhttprequest",
        "websocket",
        "eventsource",
        "sendbeacon",
        "document.write",
        "window.open",
    ):
        assert primitive not in app_script


def test_html_contains_no_secret_email_or_absolute_machine_path() -> None:
    document = render_executive_html(build_executive_payload())
    soup = BeautifulSoup(document, "html.parser")
    # Vendored Plotly preserves third-party license notices, including author
    # contacts. Project data and application code must remain free of contact
    # details, credentials, and machine-local paths.
    soup.select_one("script[data-runtime='plotly-local']").extract()
    project_document = str(soup)
    assert not re.search(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", project_document, re.I
    )
    assert not re.search(
        r"(?:(?<![A-Za-z])[A-Za-z]:[\\/]|file://|\\\\|/(?:home|Users)/)",
        project_document,
        re.I,
    )
    assert not re.search(
        r"(?:SEC_USER_AGENT|BANXICO_TOKEN|EIA_API_KEY|ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,})",
        project_document,
        re.I,
    )


def test_adversarial_payload_is_escaped_in_html_and_json() -> None:
    payload = copy.deepcopy(build_executive_payload())
    payload["metadata"]["title"] = "</title><script id='pwn'>alert(1)</script>"
    payload["metadata"]["coverage_label"] = "<img src=x onerror=alert(1)>"
    payload["views"]["2026Q2"]["conclusions"][0] = "</script><script id='json-pwn'>x</script>"
    document = render_executive_html(payload)
    soup = BeautifulSoup(document, "html.parser")
    assert soup.find(id="pwn") is None
    assert soup.find(id="json-pwn") is None
    assert soup.find("img") is None
    assert "\\u003c/script" in soup.select_one("#dashboard-data").string


def test_responsive_and_reduced_motion_rules_are_present() -> None:
    css = (PATHS.root / "src/dashboard/assets/executive_summary.css").read_text(
        encoding="utf-8"
    )
    assert "@media (max-width: 900px)" in css
    assert "@media (max-width: 700px)" in css
    assert "@media (max-width: 420px)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "grid-template-columns: repeat(5" in css


def test_generated_artifact_matches_current_renderer() -> None:
    assert DEFAULT_OUTPUT.exists()
    existing=DEFAULT_OUTPUT.read_text(encoding='utf-8')
    manifest=BeautifulSoup(existing,'html.parser').find(id='analysis-manifest')
    if manifest:
        from src.analysis_agent import lifecycle as flow
        from src.analysis_agent.stage18 import consumer_html
        from src.config import PATHS
        entries=[]
        for item in json.loads(manifest.string):
            record_path=PATHS.root/'analysis_runs/drafts'/item['period_id']/(item['version']+'.json')
            if not record_path.exists():
                pytest.skip(
                    'Exact integrated-artifact regeneration requires the private '
                    'authorized analysis ledger.'
                )
            record=json.loads(record_path.read_bytes())
            authorized=flow.consumer_payload(record)
            package,calculations,checks=flow.verified_inputs(record)
            entries.append((record,authorized,package,calculations,checks))
        expected=consumer_html(build_executive_payload(),entries)
    else:
        expected = render_executive_html(build_executive_payload())
    assert DEFAULT_OUTPUT.read_text(encoding="utf-8") == expected
    # International routes include a pinned local topology instead of CDN calls.
    assert DEFAULT_OUTPUT.stat().st_size < 6_500_000
