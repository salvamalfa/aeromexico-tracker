"""Checks that the already-assembled, gate-signed ``site/`` still
matches its own sources of truth (its inputs, not a second rendered page):

- ``test_site_flights_and_executive_data_match_a_fresh_export`` (no
  browser): the Vuelos/executive data already committed under
  ``site/data/v1/`` equals its authorized source projection. A quarterly-only
  publication reconstructs financial data from primary evidence and preserves
  the approved monthly projection exactly against its pinned baseline.
- The Playwright tests below render ``site/`` alone and check what it shows
  against the real payloads directly (``executive_payload``/the local
  ledger's approved analysis), not against a second render.

Requires ``site/`` to already exist and pass ``src.publish.verify`` (skips
with a clear reason otherwise -- run
``python -m src.publish --record ... --out site/`` first, an
owner-authorized step, see ``src/publish/README.md``).
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from src.analysis_agent import lifecycle as flow
from src.publish import manifest as manifest_mod
from src.publish.verify import verify_site
from src.web_export.analysis import MissingAnalysisInput, export_period
from src.web_export.executive import export_executive
from src.web_export.flights import export_flights, recombine_flights

pytestmark = pytest.mark.local_data

SITE_DIR = Path(__file__).resolve().parent.parent / "site"
DATA_DIR = SITE_DIR / "data" / "v1"
READER_KPI_KEYS = ("rask_cents_per_km", "cask_cents_per_km", "ask_km")
QUARTERLY_BASELINE_COMMIT = "cec09e625a2f49869bffb470e4eeda7d26c255de"


def _baseline_json(relative: str) -> dict:
    """Read the independently pinned publication before the quarterly addition."""
    return json.loads(
        subprocess.check_output(
            ["git", "show", f"{QUARTERLY_BASELINE_COMMIT}:site/{relative}"], cwd=SITE_DIR.parent
        )
    )


@pytest.fixture(scope="module")
def published_executive(executive_payload: dict) -> dict:
    """Replay the new primary-source edition over the pinned public baseline."""
    from src.publish.gate import verify_records
    from src.publish.quarterly_overlay import executive_projection

    entries = manifest_mod.load_manifest(SITE_DIR)["analysis_manifest"]
    quarterly = [e for e in entries if e["period_id"] == "2026Q3" and "entity_key" not in e]
    if not quarterly:
        return executive_payload
    assert len(quarterly) == 1
    entry = quarterly[0]
    path = SITE_DIR.parent / "analysis_runs/drafts/2026Q3" / f"{entry['version']}.json"
    record = json.loads(path.read_bytes())
    verified = verify_records([record])[0]
    assert manifest_mod.analysis_identity(verified[1]) == manifest_mod.analysis_identity(entry)
    assert verified[1]["version"] == entry["version"]
    assert record["draft"]["source_profile"] == "quarterly_release_v1"
    baseline = _baseline_json("data/v1/executive.json")
    # The quarterly operation preserves the old export rather than refreshing it.
    assert executive_payload == baseline
    return executive_projection(baseline, verified[2])


def _skip_or_fail(config: pytest.Config, message: str) -> None:
    """A missing/invalid site/ is a skip normally, but a failure under
    --require-local-data (tests/conftest.py) -- that flag means "this
    checkout is expected to have local data and an approved, gate-signed
    site/ ready to verify against it; do not silently let that go missing".
    """

    if config.getoption("--require-local-data"):
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


def _require_site(request: pytest.FixtureRequest) -> None:
    if not SITE_DIR.is_dir():
        _skip_or_fail(
            request.config,
            f"{SITE_DIR} does not exist; run `python -m src.publish --record ... --out site/` first",
        )
    problems = verify_site(SITE_DIR)
    if problems:
        _skip_or_fail(request.config, f"{SITE_DIR} fails src.publish.verify: {problems[:3]}")


def _export_approved_entry(entry: dict) -> dict:
    """Replay each exact approval through its own trusted implementation."""
    baseline = _baseline_json("publication_manifest.json")
    if entry in baseline["analysis_manifest"]:
        from src.publish.approval_anchor import approval_implementation
        from src.publish.frozen_data import verify_baseline_approvals
        from src.publish.gate import _analysis_manifest_entry

        repo = SITE_DIR.parent
        code = approval_implementation(repo, QUARTERLY_BASELINE_COMMIT, baseline)
        relative = Path("analysis_runs/drafts")
        if "entity_key" in entry:
            relative /= entry["entity_key"]
        path = repo / relative / entry["period_id"] / f"{entry['version']}.json"
        result = verify_baseline_approvals([path], code, flow.ROOT, include_public_payloads=True)
        assert [_analysis_manifest_entry(a) for a in result["authorized"]] == [entry]
        return result["payloads"][0]
    entity_args = {"entity_key": entry["entity_key"]} if "entity_key" in entry else {}
    return export_period(entry["period_id"], entry["version"], root=flow.ROOT, **entity_args)


def test_site_flights_and_executive_data_match_a_fresh_export(
    request: pytest.FixtureRequest, tmp_path: Path, flight_payload: dict, published_executive: dict
) -> None:
    """Reconstruct financial data; preserve the separately approved monthly map."""

    _require_site(request)
    out_dir = tmp_path / "data" / "v1"
    export_executive(published_executive, out_dir, skip_input_check=True)
    manifest = manifest_mod.load_manifest(SITE_DIR)
    if any(e["period_id"] == "2026Q3" and "entity_key" not in e for e in manifest["analysis_manifest"]):
        prefix = "data/v1/flights/"
        expected = {
            r["path"]: r
            for r in _baseline_json("publication_manifest.json")["files"]
            if r["path"].startswith(prefix)
        }
        actual = {r["path"]: r for r in manifest["files"] if r["path"].startswith(prefix)}
        assert actual == expected
        assert {
            p.relative_to(SITE_DIR).as_posix() for p in (DATA_DIR / "flights").rglob("*") if p.is_file()
        } == set(expected)
        for name, row in expected.items():
            raw = (SITE_DIR / name).read_bytes()
            assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
    else:
        export_flights(flight_payload, out_dir, skip_input_check=True)
        assert recombine_flights(out_dir) == recombine_flights(DATA_DIR)
    fresh_executive = json.loads((out_dir / "executive.json").read_text(encoding="utf-8"))
    site_executive = json.loads((DATA_DIR / "executive.json").read_text(encoding="utf-8"))
    assert fresh_executive == site_executive

    expected_entries = {
        manifest_mod.analysis_identity(entry): entry
        for entry in manifest_mod.load_manifest(SITE_DIR)["analysis_manifest"]
    }
    checked = set()
    for analysis_path in sorted((DATA_DIR / "analysis").rglob("*.json")):
        site_analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        identity = manifest_mod.analysis_identity(site_analysis)
        entry = expected_entries[identity]
        assert analysis_path.relative_to(DATA_DIR) == manifest_mod.analysis_relative_path(entry)
        try:
            fresh_analysis = _export_approved_entry(entry)
        except MissingAnalysisInput as error:
            # _skip_or_fail always raises (Skipped or Failed), so this loop
            # iteration never reaches the assert below in that case.
            _skip_or_fail(
                request.config, f"{identity}/{site_analysis['version']} no longer approved locally: {error}"
            )
            continue
        assert fresh_analysis == site_analysis
        checked.add(identity)
    assert checked == set(expected_entries), f"never checked {set(expected_entries) - checked}"


# ---------------------------------------------------------------------------
# Browser checks against site/ alone
# ---------------------------------------------------------------------------

playwright_sync_api = pytest.importorskip("playwright.sync_api")
sync_playwright = playwright_sync_api.sync_playwright

browser_test = pytest.mark.browser


def _chromium_executable() -> str | None:
    candidate = Path("/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    return str(candidate) if candidate.exists() else None


@pytest.fixture(scope="module")
def site_server(request: pytest.FixtureRequest):
    _require_site(request)
    handler = partial(SimpleHTTPRequestHandler, directory=str(SITE_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        thread.join()


@pytest.fixture(scope="module")
def site_page(site_server):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium_executable())
        page = browser.new_page()
        page.route("**/favicon.ico", lambda route: route.fulfill(status=204, body=""))
        page.goto(site_server)
        page.wait_for_function("document.getElementById('period-display').textContent !== '—'")
        yield page
        browser.close()


def _text(page, selector: str) -> str | None:
    return page.evaluate(
        "(selector) => { const el = document.querySelector(selector); "
        "return el ? el.innerText.replace(/\\s+/g, ' ').trim() : null; }",
        selector,
    )


def _kpi_values(page) -> dict[str, str]:
    return {key: page.inner_text(f"#kpi-{key}-value") for key in READER_KPI_KEYS} | {
        "unit_margin_cents_per_km": page.inner_text("#kpi-unit_margin_cents_per_km-value")
    }


def _period_ids(executive_payload: dict) -> list[str]:
    return [record["period_id"] for record in executive_payload["records"]]


@browser_test
def test_reader_tabs_switch_panels_on_the_site(site_page) -> None:
    for tab_id, panel_id in (
        ("tab-economy", "panel-economy"),
        ("tab-flights", "panel-flights"),
        ("tab-reading", "panel-reading"),
    ):
        site_page.click(f"#{tab_id}")
        assert site_page.is_visible(f"#{panel_id}")
        assert site_page.get_attribute(f"#{tab_id}", "aria-selected") == "true"


@browser_test
def test_economy_tab_kpis_match_the_underlying_payload_for_every_quarter(
    site_page, site_server, published_executive: dict
) -> None:
    """The economy tab's KPI cards show exactly the payload's own display
    values -- rask/cask/ask are pre-formatted server-side
    (``executive_summary.py``'s ``_display_value``); the margin card is the
    one KPI computed client-side, from the same record's raw field.

    ``records``/``views`` are Grupo Aeroméxico's, while the Dashboard v2 KPI
    cards open on Industria, so the page is loaded with Aeroméxico selected
    (``?sel_kpis=AEROMEXICO``) and restored afterwards for the other tests."""

    site_page.goto(f"{site_server}?sel_kpis=AEROMEXICO")
    site_page.wait_for_function("document.getElementById('period-display').textContent !== '—'")
    try:
        _check_economy_kpis(site_page, published_executive)
    finally:
        site_page.goto(site_server)
        site_page.wait_for_function("document.getElementById('period-display').textContent !== '—'")


def _check_economy_kpis(site_page, executive_payload: dict) -> None:
    site_page.click("#tab-economy")
    while site_page.is_enabled("#period-next"):
        site_page.click("#period-next")
    views = executive_payload["views"]
    records = {record["period_id"]: record for record in executive_payload["records"]}
    period_ids = _period_ids(executive_payload)
    for period_id in reversed(period_ids):
        site_page.wait_for_function(
            "(id) => document.getElementById('narrative-copy').dataset.period === id", arg=period_id
        )
        view = views[period_id]
        kpis_by_key = {item["key"]: item for item in view["kpis"]}
        observed = _kpi_values(site_page)
        for key in READER_KPI_KEYS:
            assert observed[key] == kpis_by_key[key]["display_value"], f"{key} mismatch at {period_id}"
        margin = records[period_id]["unit_margin_cents_per_km"]
        expected_margin = f"{'+' if margin >= 0 else ''}{margin:.2f} ¢ USD"
        assert observed["unit_margin_cents_per_km"] == expected_margin, f"margin mismatch at {period_id}"
        if site_page.is_enabled("#period-prev"):
            site_page.click("#period-prev")


def _with_citation_labels(text: str, citations: list[dict]) -> str:
    """Port of narrative.ts::applyCitations' text-splicing, in plain text:
    each citation's label is inserted right after the first (in reading
    order) occurrence of its ``value`` -- the same substring the DOM ends
    up with once the <sup><a> citation marker is spliced in."""

    # Sources for a shared value append to its first marker group in input
    # order. Citation labels are never searched as narrative text.
    segments: list[str | tuple[str, str]] = [text]
    for citation in citations:
        marker_position = next(
            (
                i
                for i, segment in enumerate(segments)
                if isinstance(segment, tuple) and segment[0] == citation["value"]
            ),
            None,
        )
        if marker_position is not None:
            previous = segments[marker_position]
            segments[marker_position] = (citation["value"], previous[1] + citation["label"])
            continue
        for position, segment in enumerate(segments):
            if not isinstance(segment, str):
                continue
            index = segment.find(citation["value"])
            if index == -1:
                continue
            end = index + len(citation["value"])
            segments[position : position + 1] = [
                segment[:end],
                (citation["value"], citation["label"]),
                segment[end:],
            ]
            break
    return "".join(segment if isinstance(segment, str) else segment[1] for segment in segments)


def test_citation_labels_preserve_multiple_sources_for_the_same_value() -> None:
    citations = [{"value": "42", "label": "1"}, {"value": "42", "label": "2"}]
    assert _with_citation_labels("Valor 42 y texto.", citations) == "Valor 4212 y texto."


@browser_test
def test_reading_tab_narrative_matches_the_approved_analysis(
    request: pytest.FixtureRequest, site_page, site_server
) -> None:
    """For every entity/period the published manifest selects,
    the reading tab's narrative text contains that exact approved thesis
    and every summary item, citation markers included -- read straight from
    the ledger, not from a second render."""

    manifest = manifest_mod.load_manifest(SITE_DIR)["analysis_manifest"]
    if not manifest:
        _skip_or_fail(request.config, "The published site has no selected analysis identities")
    expected = {}
    for entry in manifest:
        try:
            expected[manifest_mod.analysis_identity(entry)] = _export_approved_entry(entry)
        except MissingAnalysisInput as error:
            # The site pins an exact record, including its entity namespace.
            # Each exact selected identity must pass its own pinned verifier.
            _skip_or_fail(request.config, f"{entry}: {error}")

    checked = set()
    for (entity, period_id), analysis in expected.items():
        site_page.goto(f"{site_server}?entity={entity}&period={period_id}")
        site_page.wait_for_function(
            "([entity, period, thesis]) => { const copy = document.getElementById('narrative-copy'); "
            "return copy.dataset.entity === entity && copy.dataset.period === period && "
            "copy.querySelector('h3')?.textContent === thesis; }",
            arg=[entity, period_id, analysis["thesis"]],
        )
        site_page.click("#tab-reading")
        citations_by_claim = {claim["claim_id"]: claim["citations"] for claim in analysis["claims"]}
        text = _text(site_page, "#narrative-copy")
        assert analysis["thesis"] in text, (entity, period_id)
        for item in analysis["summary_items"]:
            expected_text = _with_citation_labels(item["text"], citations_by_claim.get(item["claim_id"], []))
            assert expected_text in text, (entity, period_id, item["claim_id"])
        checked.add((entity, period_id))
    assert checked == set(expected), f"never reached {set(expected) - checked}"
