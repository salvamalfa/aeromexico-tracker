from __future__ import annotations

import copy
import json
import math
from pathlib import Path
import re

from bs4 import BeautifulSoup

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
    assert payload["metadata"]["quarter_count"] == len(history) == 8
    assert payload["metadata"]["first_period"] == "2024Q3"
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
    assert latest["margin_qoq"]["display"] == "-0.68 ¢"
    assert latest["margin_yoy"]["display"] == "-1.18 ¢"


def test_missing_comparables_are_explicit_not_zero() -> None:
    payload = build_executive_payload()
    first = payload["views"]["2024Q3"]
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
    assert "Vista ejecutiva trimestral" in soup.get_text(" ", strip=True)
    assert "Estructura de datos" not in soup.get_text(" ", strip=True)


def test_html_embeds_all_quarters_and_default_selection() -> None:
    document = render_executive_html(build_executive_payload())
    soup = BeautifulSoup(document, "html.parser")
    options = soup.select("#period-selector option")
    assert len(options) == 8
    assert [option["value"] for option in options] == [
        "2026Q2",
        "2026Q1",
        "2025Q4",
        "2025Q3",
        "2025Q2",
        "2025Q1",
        "2024Q4",
        "2024Q3",
    ]
    assert soup.select_one("#period-selector option[selected]")["value"] == "2026Q2"
    embedded = _payload_from_html(document)
    assert embedded == build_executive_payload()


def test_html_has_expected_charts_narrative_and_disclosures() -> None:
    document = render_executive_html(build_executive_payload())
    soup = BeautifulSoup(document, "html.parser")
    assert {node["id"] for node in soup.select(".chart[id]")} == {
        "unit-chart",
        "volume-chart",
        "load-chart",
    }
    assert len(soup.select("details.disclosure")) == 2
    assert len(soup.select(".history-item")) == 8
    assert len(soup.select("tbody tr")) == 8
    assert "RASK vs CASK" in soup.get_text(" ", strip=True)
    assert "¿Volumen o monetización?" in soup.get_text(" ", strip=True)


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
    expected = render_executive_html(build_executive_payload())
    assert DEFAULT_OUTPUT.read_text(encoding="utf-8") == expected
    assert DEFAULT_OUTPUT.stat().st_size < 6_000_000
