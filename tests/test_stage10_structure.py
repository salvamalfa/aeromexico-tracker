from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.config import PATHS
from src.dashboard.navigation import PAGE_SPECS
from src.dashboard.structure_html import render_structure_html
from src.dashboard.structure_metadata import (
    build_structure_metadata,
    validate_public_url,
)
import src.dashboard.structure_metadata as structure_metadata_module
from src.dashboard.structure_presentation import SOURCE_GROUPS
from src.transform.stage6_contracts import load_contracts
from src.transform.stage9_lineage import load_source_catalog


@pytest.fixture(scope="module")
def metadata() -> dict[str, object]:
    return build_structure_metadata()


@pytest.fixture(scope="module")
def document(metadata: dict[str, object]) -> str:
    return render_structure_html(metadata)


@pytest.fixture(scope="module")
def soup(document: str) -> BeautifulSoup:
    return BeautifulSoup(document, "html.parser")


def test_metadata_covers_active_public_sources_exactly_once(metadata: dict[str, object]) -> None:
    catalog = load_source_catalog()
    expected = {
        key
        for key, definition in catalog["sources"].items()
        if definition["source_kind"] == "public" and definition["is_active"]
    }
    grouped = [key for group in SOURCE_GROUPS for key in group["source_keys"]]
    assert len(grouped) == len(set(grouped))
    assert set(grouped) == expected
    assert metadata["summary"]["active_public_sources"] == len(expected)


def test_source_links_obey_catalog_and_explicit_artifact_policy(metadata: dict[str, object]) -> None:
    catalog = load_source_catalog()["sources"]
    artifacts = pd.read_parquet(PATHS.gold / "dim_source_artifact.parquet")
    source_cards = metadata["levels"][0]["cards"]
    for card in source_cards:
        for source in card["sources"]:
            definition = catalog[source["source_key"]]
            assert source["official_url"] == definition["official_page_url"]
            assert validate_public_url(source["official_url"], definition["allowed_hosts"])
            featured = source["featured_artifact"]
            if definition["artifact_link_policy"] == "landing_page_only":
                assert featured is None
            if featured is None:
                continue
            assert validate_public_url(featured["url"], definition["allowed_hosts"])
            matching = artifacts[
                artifacts["source_key"].eq(source["source_key"])
                & artifacts["source_url"].eq(featured["url"])
                & artifacts["is_direct_public_artifact"].fillna(False)
            ]
            assert len(matching) == 1
            assert featured["artifact_sha256"] == matching.iloc[0]["artifact_sha256"]


def test_gold_relationships_and_grains_match_contracts(metadata: dict[str, object]) -> None:
    contracts = load_contracts()["tables"]
    displayed = {table["table_name"]: table for table in metadata["gold"]["tables"]}
    assert set(displayed) == set(contracts)
    for name, definition in contracts.items():
        assert displayed[name]["grain"] == definition["grain"]
        assert displayed[name]["primary_key"] == definition.get("primary_key", [])

    expected_edges = {
        (
            foreign_key["references"]["table"],
            child,
            tuple(foreign_key["references"]["columns"]),
            tuple(foreign_key["columns"]),
        )
        for child, definition in contracts.items()
        for foreign_key in definition.get("foreign_keys", [])
    }
    observed_edges = {
        (
            edge["parent"],
            edge["child"],
            tuple(edge["parent_columns"]),
            tuple(edge["child_columns"]),
        )
        for edge in metadata["gold"]["fk_edges"]
    }
    assert observed_edges == expected_edges


def test_view_and_page_consumers_reference_real_assets(metadata: dict[str, object]) -> None:
    views = {view["name"] for view in metadata["gold"]["views"]}
    page_titles = {spec.title for spec in PAGE_SPECS}
    table_names = {table["table_name"] for table in metadata["gold"]["tables"]}
    assert len(views) == 21
    assert set(metadata["gold"]["page_assets"]) == page_titles - {"Estructura de datos"}
    for table in metadata["gold"]["tables"]:
        definition = load_contracts()["tables"][table["table_name"]]
        expected_inputs = {
            foreign_key["references"]["table"]
            for foreign_key in definition.get("foreign_keys", [])
        }
        assert set(table["consumer_pages"]) <= page_titles
        assert set(table["inputs"]) == expected_inputs
        assert set(table["outputs"]) <= table_names | views
    for view in metadata["gold"]["views"]:
        assert set(view["depends_on"]) <= table_names | views
    for page, assets in metadata["gold"]["page_assets"].items():
        assert page in page_titles
        assert set(assets) <= table_names | views


def test_normalization_examples_have_real_evidence(metadata: dict[str, object]) -> None:
    examples = {item["kind"]: item for item in metadata["normalization_examples"]}
    assert set(examples) == {"Porcentaje", "Moneda", "Periodo"}
    assert examples["Porcentaje"]["before"] == "84.4 %"
    assert examples["Porcentaje"]["after"] == "0.844"
    assert examples["Moneda"]["after"] == "1,479,000,000 USD"
    assert examples["Periodo"]["before"] == "1Q26"
    for item in examples.values():
        evidence_paths = [
            part for part in item["evidence"].split(" · ") if "/" in part
        ]
        assert evidence_paths
        assert all((PATHS.root / path).exists() for path in evidence_paths)
    assert "84.4" in (PATHS.root / "tests/fixtures/sec/earnings_2026Q1.htm").read_text(encoding="utf-8")
    assert "1,479" in (PATHS.root / "tests/fixtures/sec/earnings_2026Q2.htm").read_text(encoding="utf-8")


def test_metadata_is_deterministic_and_does_not_load_lineage_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    real_read_parquet = pd.read_parquet
    calls: list[str] = []

    def tracked(path: str | Path, *args: object, **kwargs: object) -> pd.DataFrame:
        calls.append(Path(path).name)
        return real_read_parquet(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", tracked)
    first = build_structure_metadata()
    second = build_structure_metadata()
    assert calls == ["dim_source_artifact.parquet", "dim_source_artifact.parquet"]
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(
        second, ensure_ascii=False, sort_keys=True
    )


def test_metadata_build_is_deployment_safe_without_local_quality_receipts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_read_json = structure_metadata_module._read_json

    def guarded(path: Path) -> dict[str, object]:
        if PATHS.quality in path.parents:
            raise AssertionError("runtime attempted to read ignored data/quality metadata")
        return real_read_json(path)

    monkeypatch.setattr(structure_metadata_module, "_read_json", guarded)
    assert build_structure_metadata()["summary"]["lineage_coverage"] == 1.0


@pytest.mark.parametrize(
    "field,value",
    [
        ("artifact_count", 751),
        ("lineage_coverage", 0.5),
        ("bridge_sha256", "not-a-sha256"),
        ("silver_contract_sha256", "0" * 64),
    ],
)
def test_stale_or_tampered_public_receipt_fails_closed(
    field: str,
    value: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    receipt = json.loads(
        structure_metadata_module.PUBLIC_VALIDATION_RECEIPT.read_text(encoding="utf-8")
    )
    receipt[field] = value
    target = tmp_path / "receipt.json"
    target.write_text(json.dumps(receipt), encoding="utf-8")
    monkeypatch.setattr(structure_metadata_module, "PUBLIC_VALIDATION_RECEIPT", target)
    with pytest.raises(ValueError):
        build_structure_metadata()


def test_runtime_rejects_tampered_lineage_bridge_fingerprint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_sha256 = structure_metadata_module._sha256_file

    def tampered_sha256(path: Path) -> str:
        if path.name == "bridge_record_lineage.parquet":
            return "f" * 64
        return real_sha256(path)

    monkeypatch.setattr(structure_metadata_module, "_sha256_file", tampered_sha256)
    with pytest.raises(ValueError, match="lineage bridge"):
        build_structure_metadata()


def test_public_receipt_is_compact_deterministic_and_fingerprinted() -> None:
    path = structure_metadata_module.PUBLIC_VALIDATION_RECEIPT
    receipt = json.loads(path.read_text(encoding="utf-8"))
    assert path.stat().st_size < 10_000
    assert "generated_at" not in receipt
    assert receipt["validation_status"] == "passed"
    assert receipt["lineage_records_declared"] == receipt["lineage_records_expected"]
    assert receipt["lineage_coverage"] == 1.0
    for field in (
        "source_catalog_sha256",
        "silver_contract_sha256",
        "gold_contract_sha256",
        "pipeline_registry_sha256",
        "artifact_catalog_sha256",
        "quality_ledger_sha256",
        "bridge_sha256",
    ):
        assert re.fullmatch(r"[0-9a-f]{64}", receipt[field])


def test_funnel_has_five_ordered_levels_and_four_connectors(soup: BeautifulSoup) -> None:
    levels = soup.select("[data-testid='funnel-level']")
    assert [level["data-level"] for level in levels] == [
        "sources",
        "capture",
        "clean",
        "model",
        "product",
    ]
    assert len(soup.select("[data-testid='level-connector']")) == 4


def test_card_fronts_are_business_first_and_details_hold_technical_names(soup: BeautifulSoup) -> None:
    forbidden = ("data/", "src/", ".parquet", "dim_", "fact_", "v_")
    for front in soup.select(".card-front"):
        text = front.get_text(" ", strip=True)
        assert not any(token in text for token in forbidden), text
    detail_text = " ".join(panel.get_text(" ", strip=True) for panel in soup.select("[data-testid='detail-panel']"))
    assert "config/source_catalog.yaml" in detail_text
    assert "data/bronze/" in detail_text
    for option in soup.select("#table-selector option[value]"):
        assert option.get_text(strip=True) == option["data-business-label"]
        assert option["data-technical-name"] == option["value"]


def test_html_has_accessible_controls_and_unique_ids(soup: BeautifulSoup) -> None:
    ids = [element["id"] for element in soup.select("[id]")]
    assert len(ids) == len(set(ids))
    summaries = soup.select("summary[data-testid='detail-toggle']")
    assert summaries
    for summary in summaries:
        assert summary.get("aria-expanded") == "false"
        target = summary.get("aria-controls")
        assert target and soup.find(id=target)
    assert soup.select_one("[data-testid='gold-detail'][aria-live='polite']")
    assert not soup.select(".gold-map > svg")
    assert not soup.select("[tabindex]:not([tabindex='0']):not([tabindex='-1'])")


def test_html_is_local_only_and_avoids_unsafe_dom_sinks(soup: BeautifulSoup, document: str) -> None:
    assert len(soup.find_all("script")) == 1
    assert not soup.select("script[src], link[rel='stylesheet'], iframe, img[src], video[src], audio[src]")
    lowered = document.lower()
    style_text = " ".join(style.get_text() for style in soup.find_all("style")).lower()
    assert "@import" not in style_text
    assert "url(http://" not in style_text
    assert "url(https://" not in style_text
    for primitive in (
        "fetch(",
        "xmlhttprequest",
        "websocket",
        "eventsource",
        "sendbeacon",
        "import(",
        "innerhtml",
        "outerhtml",
        "insertadjacenthtml",
        "document.write",
        "eval(",
        "new function",
    ):
        assert primitive not in lowered


def test_html_contains_no_secret_email_or_absolute_path(document: str) -> None:
    assert not re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", document, re.I)
    assert not re.search(
        r"(?:(?<![A-Za-z])[A-Za-z]:[\\/]|file://|\\\\|/(?:home|Users)/)",
        document,
        re.I,
    )
    assert not re.search(r"(?:sk-|ghp_|SEC_USER_AGENT|BANXICO_TOKEN|EIA_API_KEY)", document, re.I)


def test_adversarial_metadata_is_escaped(metadata: dict[str, object]) -> None:
    hostile = copy.deepcopy(metadata)
    hostile["levels"][0]["cards"][0]["title"] = "</script><script id='pwn'>alert(1)</script>"
    hostile["levels"][0]["cards"][0]["summary"] = "<img src=x onerror=alert(1)>"
    rendered = render_structure_html(hostile)
    parsed = BeautifulSoup(rendered, "html.parser")
    assert len(parsed.find_all("script")) == 1
    assert parsed.find(id="pwn") is None
    assert parsed.find("img") is None
    assert "&lt;/script&gt;" in rendered


def test_gold_summary_value_is_escaped(metadata: dict[str, object]) -> None:
    hostile = copy.deepcopy(metadata)
    hostile["summary"]["gold_tables"] = '<img id="summary-pwn" onerror="alert(1)">'
    rendered = render_structure_html(hostile)
    parsed = BeautifulSoup(rendered, "html.parser")
    assert parsed.find(id="summary-pwn") is None
    assert "&lt;img" in rendered


@pytest.mark.parametrize(
    "target",
    [
        "source_display_name",
        "source_limitation",
        "process_technical",
        "gold_purpose",
        "gold_table_name",
        "foreign_key_columns",
    ],
)
def test_nested_text_and_attribute_contexts_remain_escaped(
    metadata: dict[str, object], target: str
) -> None:
    hostile = copy.deepcopy(metadata)
    payload = '\" onmouseover=\"alert(1)\"></template><script id="nested-pwn">x</script><img onerror="alert(2)">'
    if target == "source_display_name":
        hostile["levels"][0]["cards"][0]["sources"][0]["display_name"] = payload
    elif target == "source_limitation":
        hostile["levels"][0]["cards"][0]["sources"][0]["limitations"] = payload
    elif target == "process_technical":
        hostile["levels"][1]["cards"][0]["technical"]["Registro"] = payload
    elif target == "gold_purpose":
        hostile["gold"]["tables"][0]["purpose"] = payload
    elif target == "gold_table_name":
        hostile["gold"]["tables"][0]["table_name"] = payload
    else:
        hostile["gold"]["fk_edges"][0]["child_columns"] = [payload]
    rendered = render_structure_html(hostile)
    parsed = BeautifulSoup(rendered, "html.parser")
    assert len(parsed.find_all("script")) == 1
    assert parsed.find(id="nested-pwn") is None
    assert parsed.find("img") is None
    assert not parsed.select("[onmouseover], [onerror]")


def test_gold_consumers_are_emitted_from_selected_table_metadata(
    metadata: dict[str, object], soup: BeautifulSoup
) -> None:
    views = {view["name"] for view in metadata["gold"]["views"]}
    roles = {table["table_name"]: table["role"] for table in metadata["gold"]["tables"]}
    records = {
        record["data-table"]: record
        for record in soup.select(".gold-consumer-record")
    }
    assert set(records) == {table["table_name"] for table in metadata["gold"]["tables"]}
    for table in metadata["gold"]["tables"]:
        record = records[table["table_name"]]
        expected_views = " | ".join(value for value in table["outputs"] if value in views)
        expected_analytics = " | ".join(
            value for value in table["outputs"] if roles.get(value) == "analysis"
        )
        assert record["data-views"] == expected_views
        assert record["data-analytics"] == expected_analytics
        assert record["data-pages"] == " | ".join(table["consumer_pages"])


def test_structure_cache_fingerprint_is_a_real_cache_key() -> None:
    from src.dashboard.pages.estructura_datos import _structure_document

    parameters = inspect.signature(_structure_document.__wrapped__).parameters
    assert "fingerprint" in parameters
    assert not any(name.startswith("_") for name in parameters)


@pytest.mark.parametrize(
    "url,hosts",
    [
        ("javascript:alert(1)", ["sec.gov"]),
        ("data:text/html,pwn", ["sec.gov"]),
        ("http://www.sec.gov/", ["sec.gov"]),
        ("https://user:password@www.sec.gov/", ["sec.gov"]),
        ("https://localhost/source", ["localhost"]),
        ("https://127.0.0.1/source", ["127.0.0.1"]),
        ("https://www.sec.gov:8443/source", ["sec.gov"]),
        ("https://evil.example/source", ["sec.gov"]),
        ("https://www.sec.gov/\njavascript:alert(1)", ["sec.gov"]),
        ("https://www.sec.gov/\rmalicious", ["sec.gov"]),
        ("https://www.sec.gov/\tmalicious", ["sec.gov"]),
        ("https://www.sec.gov/\x00malicious", ["sec.gov"]),
    ],
)
def test_unsafe_urls_are_rejected(url: str, hosts: list[str]) -> None:
    with pytest.raises(ValueError):
        validate_public_url(url, hosts)


def test_external_links_open_safely(soup: BeautifulSoup) -> None:
    catalog = load_source_catalog()["sources"]
    allowed_hosts = {
        host.lower()
        for definition in catalog.values()
        for host in definition["allowed_hosts"]
    }
    for link in soup.select("a[target='_blank']"):
        assert set(link.get("rel", [])) >= {"noopener", "noreferrer"}
        parsed = urlsplit(link["href"])
        assert parsed.scheme == "https"
        assert any(
            parsed.hostname == host or parsed.hostname.endswith(f".{host}")
            for host in allowed_hosts
        )

    metadata = build_structure_metadata()
    expected_featured = {
        source["featured_artifact"]["url"]
        for card in metadata["levels"][0]["cards"]
        for source in card["sources"]
        if source["featured_artifact"] is not None
    }
    rendered_featured = {
        link["href"]
        for link in soup.select(
            "a[data-link-kind='artifact'], a[data-featured-artifact='true']"
        )
    }
    assert len(expected_featured) == 6
    assert rendered_featured == expected_featured
    for detail in soup.select(".source-detail"):
        hrefs = [link["href"] for link in detail.select("a[href]")]
        assert len(hrefs) == len(set(hrefs))


def test_structure_page_renders_one_javascript_enabled_html_component() -> None:
    source = "from src.dashboard.pages.estructura_datos import render\nrender()"
    app = AppTest.from_string(source, default_timeout=30).run()
    assert not app.exception
    elements = app.get("html")
    assert len(elements) == 1
    assert elements[0].proto.unsafe_allow_javascript is True
    assert "data-testid='structure-root'" in elements[0].proto.body


def test_responsive_dark_theme_and_reduced_motion_contracts_are_local() -> None:
    css = (PATHS.root / "src/dashboard/assets/data_structure.css").read_text(
        encoding="utf-8"
    )
    script = (PATHS.root / "src/dashboard/assets/data_structure.js").read_text(
        encoding="utf-8"
    )
    assert "@media (max-width: 820px)" in css
    assert "@media (max-width: 520px)" in css
    assert "@media (hover: none)" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "transition-duration: 0.001ms !important" in css
    assert "transform: none" in css
    assert '.stApp[data-amx-structure-theme="dark"] .page-hero h1' in css
    assert "themeHost.dataset.amxStructureTheme = theme" in script
