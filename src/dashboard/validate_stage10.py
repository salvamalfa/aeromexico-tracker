"""Executable local acceptance gate for the Stage 10 structure page."""

from __future__ import annotations

import json
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
import pandas as pd
from streamlit.testing.v1 import AppTest

from src.config import PATHS
from src.dashboard.navigation import PAGE_SPECS
from src.dashboard.structure_html import render_structure_html
from src.dashboard.structure_metadata import build_structure_metadata
from src.dashboard.structure_metadata import (
    PUBLIC_VALIDATION_RECEIPT,
    materialize_public_validation_receipt,
    validate_public_validation_receipt_full,
)
from src.dashboard.structure_presentation import SOURCE_GROUPS
from src.dashboard.validate_stage8 import contrast
from src.ingest.stage4_common import write_parquet_atomic
from src.transform.stage6_contracts import load_contracts
from src.transform.stage9_lineage import load_source_catalog


def validate_stage10() -> dict[str, object]:
    checks: list[dict[str, object]] = []

    def add(name: str, passed: bool, observed: object, expected: object) -> None:
        checks.append(
            {
                "check_name": name,
                "passed": bool(passed),
                "observed": str(observed),
                "expected": str(expected),
            }
        )

    if (PATHS.quality / "stage9_lineage.json").is_file() and (
        PATHS.quality / "stage9_acceptance.json"
    ).is_file():
        materialize_public_validation_receipt()
    if not PUBLIC_VALIDATION_RECEIPT.is_file():
        raise FileNotFoundError("The public Stage 9 validation receipt is missing")
    validation_receipt = validate_public_validation_receipt_full()
    metadata = build_structure_metadata()
    document = render_structure_html(metadata)
    soup = BeautifulSoup(document, "html.parser")

    add(
        "public_validation_receipt",
        validation_receipt.get("validation_status") == "passed"
        and validation_receipt.get("lineage_coverage") == 1.0,
        {
            "schema": validation_receipt.get("schema_version"),
            "records": validation_receipt.get("lineage_records_declared"),
            "bridge_rows": validation_receipt.get("bridge_rows"),
        },
        "deployment-safe receipt with full local fingerprint verification",
    )

    navigation_tail = [
        (spec.title, spec.url_path) for spec in PAGE_SPECS[-3:]
    ]
    add(
        "navigation",
        len(PAGE_SPECS) == 11
        and navigation_tail
        == [
            ("Salud de datos", "salud-datos"),
            ("Estructura de datos", "estructura-datos"),
            ("Glosario", "glosario"),
        ],
        navigation_tail,
        "11 pages with the Stage 10 route between health and glossary",
    )

    catalog = load_source_catalog()
    active_public = {
        key
        for key, definition in catalog["sources"].items()
        if definition["source_kind"] == "public" and definition["is_active"]
    }
    grouped_sources = [
        key for group in SOURCE_GROUPS for key in group["source_keys"]
    ]
    add(
        "source_catalog_coverage",
        len(grouped_sources) == len(set(grouped_sources))
        and set(grouped_sources) == active_public,
        {"groups": len(SOURCE_GROUPS), "sources": sorted(grouped_sources)},
        "every active public source exactly once",
    )

    levels = soup.select("[data-testid='funnel-level']")
    connectors = soup.select("[data-testid='level-connector']")
    add(
        "five_level_funnel",
        [level.get("data-level") for level in levels]
        == ["sources", "capture", "clean", "model", "product"]
        and len(connectors) == 4,
        {"levels": len(levels), "connectors": len(connectors)},
        "five ordered levels and four permanent connectors",
    )

    forbidden_front = ("data/", "src/", ".parquet", "dim_", "fact_", "v_")
    front_violations = [
        front.get_text(" ", strip=True)
        for front in soup.select(".card-front")
        if any(token in front.get_text(" ", strip=True) for token in forbidden_front)
    ]
    add(
        "business_first_cards",
        not front_violations,
        front_violations[:3],
        "no paths, tables, or fields on card fronts",
    )

    contracts = load_contracts()["tables"]
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
    add(
        "gold_contract_relations",
        expected_edges == observed_edges
        and {table["table_name"] for table in metadata["gold"]["tables"]}
        == set(contracts),
        {"tables": len(contracts), "relations": len(observed_edges)},
        "all contract tables and exact foreign-key edges",
    )

    known_assets = set(contracts) | {view["name"] for view in metadata["gold"]["views"]}
    invalid_view_dependencies = {
        view["name"]: sorted(set(view["depends_on"]) - known_assets)
        for view in metadata["gold"]["views"]
        if set(view["depends_on"]) - known_assets
    }
    expected_page_titles = {spec.title for spec in PAGE_SPECS} - {"Estructura de datos"}
    add(
        "semantic_asset_integrity",
        not invalid_view_dependencies
        and set(metadata["gold"]["page_assets"]) == expected_page_titles,
        {
            "views": len(metadata["gold"]["views"]),
            "invalid_dependencies": invalid_view_dependencies,
            "page_assets": len(metadata["gold"]["page_assets"]),
        },
        "every view dependency is real and every pre-existing page is represented",
    )

    example_kinds = {
        item["kind"] for item in metadata["normalization_examples"]
    }
    evidence_exists = all(
        all(
            (PATHS.root / part).exists()
            for part in item["evidence"].split(" · ")
            if "/" in part
        )
        for item in metadata["normalization_examples"]
    )
    add(
        "real_normalization_examples",
        example_kinds == {"Porcentaje", "Moneda", "Periodo"}
        and evidence_exists,
        sorted(example_kinds),
        "percentage, currency, and period with repository evidence",
    )

    allowed_hosts = {
        host.lower()
        for definition in catalog["sources"].values()
        for host in definition["allowed_hosts"]
    }
    external_links = soup.select("a[target='_blank']")
    unsafe_links: list[str] = []
    for link in external_links:
        parsed = urlsplit(link.get("href", ""))
        rel = set(link.get("rel", []))
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or not any(
                parsed.hostname == host
                or parsed.hostname.endswith(f".{host}")
                for host in allowed_hosts
            )
            or not {"noopener", "noreferrer"} <= rel
        ):
            unsafe_links.append(link.get("href", ""))
    add(
        "safe_public_links",
        bool(external_links) and not unsafe_links,
        {"links": len(external_links), "unsafe": unsafe_links},
        "authorized HTTPS hosts and safe new-tab attributes",
    )

    lowered = document.lower()
    prohibited = [
        token
        for token in (
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
            "<script src",
        )
        if token in lowered
    ]
    external_resources = soup.select(
        "script[src], link[rel='stylesheet'], iframe, img[src], video[src], audio[src]"
    )
    add(
        "offline_local_component",
        not prohibited and not external_resources,
        {"prohibited": prohibited, "external_resources": len(external_resources)},
        "no runtime network primitive, remote asset, or unsafe DOM sink",
    )

    secret_or_path = bool(
        re.search(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            document,
            re.I,
        )
        or re.search(
            r"(?:(?<![A-Za-z])[A-Za-z]:[\\/]|file://|\\\\|/(?:home|Users)/)",
            document,
            re.I,
        )
        or re.search(
            r"(?:sk-|ghp_|SEC_USER_AGENT|BANXICO_TOKEN|EIA_API_KEY)",
            document,
            re.I,
        )
    )
    add(
        "no_secrets_or_absolute_paths",
        not secret_or_path,
        secret_or_path,
        False,
    )

    ids = [element["id"] for element in soup.select("[id]")]
    summaries = soup.select("summary[data-testid='detail-toggle']")
    accessibility_ok = (
        len(ids) == len(set(ids))
        and bool(summaries)
        and all(
            summary.get("aria-expanded") == "false"
            and soup.find(id=summary.get("aria-controls")) is not None
            for summary in summaries
        )
        and soup.select_one("[data-testid='gold-detail'][aria-live='polite']")
        is not None
    )
    add(
        "accessible_interaction_contract",
        accessibility_ok,
        {"ids": len(ids), "detail_toggles": len(summaries)},
        "unique ids, named controls, ARIA state, and live table detail",
    )

    css = (PATHS.root / "src/dashboard/assets/data_structure.css").read_text(
        encoding="utf-8"
    )
    script = (PATHS.root / "src/dashboard/assets/data_structure.js").read_text(
        encoding="utf-8"
    )
    dark_contrast = {
        "page_title": contrast("#78bdf2", "#0e1117"),
        "page_context": contrast("#b8c7d4", "#0e1117"),
        "eyebrow": contrast("#ff83bb", "#0e1117"),
        "component_text": contrast("#edf4fa", "#0f1720"),
        "card_heading": contrast("#78bdf2", "#17232e"),
    }
    adaptive_contract = all(
        token in css
        for token in (
            "@media (max-width: 820px)",
            "@media (max-width: 520px)",
            "@media (hover: none)",
            "@media (prefers-reduced-motion: reduce)",
            "transition-duration: 0.001ms !important",
            '.stApp[data-amx-structure-theme="dark"] .page-hero h1',
        )
    ) and "themeHost.dataset.amxStructureTheme = theme" in script
    add(
        "responsive_theme_motion_contract",
        adaptive_contract and min(dark_contrast.values()) >= 4.5,
        {
            "responsive_breakpoints": [820, 520],
            "dark_contrast": {key: round(value, 2) for key, value in dark_contrast.items()},
            "reduced_motion": "prefers-reduced-motion" in css,
        },
        "mobile/touch rules, dark palette >= 4.5:1, and reduced-motion override",
    )

    app = AppTest.from_string(
        "from src.dashboard.pages.estructura_datos import render\nrender()",
        default_timeout=30,
    ).run()
    html_elements = app.get("html")
    add(
        "streamlit_render",
        not app.exception
        and len(html_elements) == 1
        and html_elements[0].proto.unsafe_allow_javascript is True,
        {
            "exceptions": len(app.exception),
            "html_elements": len(html_elements),
            "javascript": (
                html_elements[0].proto.unsafe_allow_javascript
                if html_elements
                else None
            ),
        },
        "one JavaScript-enabled st.html component without exceptions",
    )

    rebuilt = build_structure_metadata()
    add(
        "deterministic_metadata",
        json.dumps(metadata, ensure_ascii=False, sort_keys=True)
        == json.dumps(rebuilt, ensure_ascii=False, sort_keys=True),
        metadata["summary"],
        "same serialized metadata in two builds",
    )

    frame = pd.DataFrame(checks)
    write_parquet_atomic(
        frame, PATHS.quality / "stage10_acceptance_checks.parquet"
    )
    summary = {
        "version": metadata["version"],
        "passed": int(frame["passed"].sum()),
        "total": len(frame),
        "all_passed": bool(frame["passed"].all()),
        "failed": frame.loc[~frame["passed"], "check_name"].tolist(),
        "metadata": metadata["summary"],
        "checks": checks,
    }
    (PATHS.quality / "stage10_acceptance.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not summary["all_passed"]:
        raise AssertionError(frame.loc[~frame["passed"]].to_dict("records"))
    return summary


def main() -> int:
    print(json.dumps(validate_stage10(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
