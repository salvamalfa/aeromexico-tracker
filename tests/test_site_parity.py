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
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import threading
from contextlib import contextmanager
from functools import lru_cache, partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from src.analysis_agent import lifecycle as flow
from src.publish import manifest as manifest_mod
from src.publish.verify import verify_site
from src.web_export.analysis import MissingAnalysisInput
from src.web_export.executive import export_executive
from tests._site_publication_parity import (
    _published_approval_config_view,
    _with_citation_labels,
    assert_flight_data_parity,
    assert_reading_parity,
    official_map_edition,
    verify_current_publication,
)

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


@contextmanager
def _comparison_site():
    with _comparison_edition() as (site, _):
        yield site


@contextmanager
def _comparison_edition():
    from scripts.check_pages_publication import verifier_for
    from src.publish.financial_scope import verify_financial

    if verifier_for(SITE_DIR, SITE_DIR.parent) != "src.publish.fare_scope":
        yield SITE_DIR, None
        return
    with official_map_edition(SITE_DIR, SITE_DIR.parent, verify_financial) as historical:
        yield historical


@lru_cache(maxsize=1)
def _replay_published_cohorts() -> dict:
    from scripts.check_pages_publication import verifier_for

    with _comparison_edition() as (site, commit):
        result = _replay_cohorts_at(site, SITE_DIR.parent, verified_commit=commit)
        return {**result, "parity_profile": verifier_for(site, SITE_DIR.parent)}


def _replay_cohorts_at(site, repo, *, verified_commit=None) -> dict:
    """Validate every published entry using its committed verifier and full ledger."""
    from src.publish.approval_cohorts import verify_approval_cohorts

    from scripts.check_pages_publication import verifier_for

    if verifier_for(site, repo) in {
        "src.publish.quarterly_story_scope", "src.publish.afac_history_scope",
    }:
        from tests._quarterly_story_parity import replay

        return replay(site, repo)
    baseline = manifest_mod.load_manifest(site)
    paths = []
    for entry in baseline["analysis_manifest"]:
        path = repo / "analysis_runs/drafts"
        if "entity_key" in entry:
            path /= entry["entity_key"]
        paths.append(path / entry["period_id"] / f"{entry['version']}.json")
    with _published_approval_config_view(
        repo, (site / "publication_manifest.json").read_bytes(), verified_commit=verified_commit
    ) as (
        view,
        trusted,
    ):
        return verify_approval_cohorts(paths, view, trusted, baseline, flow.ROOT)


@pytest.fixture(scope="module")
def published_executive(executive_payload: dict) -> dict:
    with _comparison_site() as site:
        return _published_executive_at(site, SITE_DIR.parent, executive_payload)


def _published_executive_at(site, repo, executive_payload: dict) -> dict:
    """Replay the new primary-source edition over the pinned public baseline."""
    data_dir = site / "data/v1"
    from scripts.check_pages_publication import verifier_for
    from src.publish.financial_scope import ANCHOR as FINANCIAL_ANCHOR
    from src.publish.financial_scope import PROOF as FINANCIAL_PROOF
    from src.publish.records import _analysis_manifest_entry

    if verifier_for(site, repo) in {
        "src.publish.quarterly_story_scope", "src.publish.afac_history_scope",
    }:
        from src.publish.financial_scope import anchor as financial_anchor
        from tests._quarterly_story_parity import publication

        financial_spec = financial_anchor(repo)
        raw = subprocess.check_output(
            ["git", "show", f"{financial_spec['baseline_commit']}:site/data/v1/executive.json"],
            cwd=repo,
        )
        assert executive_payload == json.loads(raw)
        publication(site, repo)
        assert len(_replay_published_cohorts()["payloads"]) == 8
        return json.loads((data_dir / "executive.json").read_bytes())

    if (site / FINANCIAL_PROOF).exists() or (
        (repo / FINANCIAL_ANCHOR).is_file()
        and "2026Q3" in json.loads((site / "data/v1/executive.json").read_bytes())["views"]
    ):
        # The original warehouse projection is the frozen financial baseline;
        # only the explicitly reviewed producer may append this quarter.
        from src.publish.financial_scope import anchor as financial_anchor
        from src.publish.financial_sources import replay_published_projection

        financial_spec = financial_anchor(repo)
        raw = subprocess.check_output(
            ["git", "show", f"{financial_spec['baseline_commit']}:site/data/v1/executive.json"],
            cwd=repo,
        )
        assert executive_payload == json.loads(raw)
        return replay_published_projection(site, repo)

    from src.publish.editorial import PROOF, anchor, verify_editorial

    if (site / PROOF).exists():
        assert verify_editorial(site, repo) == []
        spec = anchor(repo)
        baseline = json.loads(
            subprocess.check_output(
                ["git", "show", f"{spec['baseline_commit']}:site/data/v1/executive.json"],
                cwd=repo,
            )
        )
        assert executive_payload == baseline
        return baseline

    entries = manifest_mod.load_manifest(site)["analysis_manifest"]
    quarterly = [e for e in entries if e["period_id"] == "2026Q3" and "entity_key" not in e]
    if not quarterly:
        return executive_payload
    assert len(quarterly) == 1
    published = json.loads((site / "data/v1/executive.json").read_bytes())
    has_view = "2026Q3" in published["views"]
    has_record = any(row["period_id"] == "2026Q3" for row in published["records"])
    assert has_view == has_record, "Partial financial quarter is not a publication"
    if not has_record:
        # A later UI-only release keeps the reading but not the old editorial
        # frontend receipt. Financial eligibility comes from the actual data;
        # receipt absence must never invent a new quarterly projection.
        assert verify_site(site) == []
        spec = anchor(repo)
        baseline_raw = subprocess.check_output(
            ["git", "show", f"{spec['baseline_commit']}:site/data/v1/executive.json"],
            cwd=repo,
        )
        assert (site / "data/v1/executive.json").read_bytes() == baseline_raw
        baseline = json.loads(baseline_raw)
        assert executive_payload == baseline
        return baseline
    entry = quarterly[0]
    path = repo / "analysis_runs/drafts/2026Q3" / f"{entry['version']}.json"
    record = json.loads(path.read_bytes())
    replay = _replay_published_cohorts()
    assert entry in [_analysis_manifest_entry(a) for a in replay["authorized"]]
    assert record["draft"]["source_profile"] == "quarterly_release_v1"
    package_path = repo / "analysis_runs/evidence" / f"{record['draft']['package_id']}.json"
    baseline = _baseline_json("data/v1/executive.json")
    # The quarterly operation preserves the old export rather than refreshing it.
    assert executive_payload == baseline
    cohort = next(c for c in replay["cohorts"] if entry in c["analysis_manifest"])
    return _quarterly_projection(cohort["implementation_commit"], baseline, package_path)


def _quarterly_projection(commit: str, baseline: dict, package_path: Path) -> dict:
    """Reconstruct the historical edition with its validated cohort's source code."""
    repo = SITE_DIR.parent
    archive = subprocess.check_output(
        ["git", "archive", commit, "src", "contracts", "config", "web", ".agents"], cwd=repo
    )
    with tempfile.TemporaryDirectory(prefix="parity-quarterly-cohort-") as tmp:
        base = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(base, filter="data")
        (base / "data").symlink_to(repo / "data", target_is_directory=True)
        script = """import json,sys
from pathlib import Path
from src.publish.quarterly_overlay import executive_projection
print(json.dumps(executive_projection(json.loads(sys.stdin.read()),
    json.loads(Path(sys.argv[1]).read_bytes())),ensure_ascii=False))
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", script, str(package_path)],
            cwd=base,
            input=json.dumps(baseline),
            capture_output=True,
            text=True,
            check=True,
        )
        return json.loads(result.stdout)


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
    from scripts.check_pages_publication import verifier_for

    if verifier_for(SITE_DIR, SITE_DIR.parent) == "src.publish.fare_scope":
        from src.publish.financial_scope import verify_financial

        verify_current_publication(SITE_DIR, SITE_DIR.parent, verify_financial)
        return
    problems = verify_site(SITE_DIR)
    if problems:
        _skip_or_fail(request.config, f"{SITE_DIR} fails src.publish.verify: {problems[:3]}")


def _export_approved_entry(entry: dict) -> dict:
    """Replay each exact approval through its own trusted implementation."""
    from src.publish.records import _analysis_manifest_entry

    replay = _replay_published_cohorts()
    for authorized, payload in zip(replay["authorized"], replay["payloads"]):
        if _analysis_manifest_entry(authorized) == entry:
            return payload
    raise AssertionError("The requested entry was not replayed by its pinned cohort")


def test_published_parity_survives_a_later_runtime_without_weakening_replay(
    executive_payload: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Historical approvals and projection use pinned code, including after source changes."""
    from src.analysis_agent import quarterly_release
    from src.publish import frozen_data, gate, quarterly_overlay
    from src.publish.records import _analysis_manifest_entry

    def later_runtime_refuses(*args, **kwargs):
        raise ValueError("Simulated later runtime refuses historical presentation")

    for module, name in (
        (flow, "require_current_presentation"),
        (gate, "verify_records"),
        (quarterly_release, "verify"),
        (quarterly_release, "calculate"),
        (quarterly_overlay, "executive_projection"),
    ):
        monkeypatch.setattr(module, name, later_runtime_refuses)

    replay_calls = []
    original_replay = frozen_data.verify_baseline_approvals

    def real_pinned_replay(paths, commit, ledger, **kwargs):
        replay_calls.append(commit)
        return original_replay(paths, commit, ledger, **kwargs)

    monkeypatch.setattr(frozen_data, "verify_baseline_approvals", real_pinned_replay)
    _replay_published_cohorts.cache_clear()
    try:
        replay = _replay_published_cohorts()
        entries = manifest_mod.load_manifest(SITE_DIR)["analysis_manifest"]
        historical = {(entity, "2026Q2") for entity in ("AEROMEXICO", "INDUSTRY", "VIVA_AEROBUS", "VOLARIS")}
        identities = {manifest_mod.analysis_identity(entry) for entry in entries}
        from scripts.check_pages_publication import verifier_for

        profile = replay.get("parity_profile", verifier_for(SITE_DIR, SITE_DIR.parent))
        native = profile == "src.publish.afac_history_scope"
        story = profile in {"src.publish.quarterly_story_scope", "src.publish.afac_history_scope"}
        complete_story = historical | {(entity, "2026Q3") for entity, _ in historical}
        assert identities in (
            (complete_story,) if story else (historical, historical | {("AEROMEXICO", "2026Q3")})
        )
        assert len(entries) == len(replay["authorized"]) == len(replay["payloads"]) == len(identities)
        cohort_count = 2 if ("AEROMEXICO", "2026Q3") in identities else 1
        assert [_analysis_manifest_entry(a) for a in replay["authorized"]] == entries
        expected_calls = [] if native else [
            cohort["implementation_commit"]
            for cohort in replay["cohorts"]
            if not story or all(e["period_id"] == "2026Q2" for e in cohort["analysis_manifest"])
        ]
        assert replay_calls == expected_calls
        assert len(set(replay_calls)) == (0 if native else 1 if story else cohort_count)
        if native:
            original = replay["original_parent_replay"]
            assert original["retained_q2_replayed"] == 4 and original["outputs_verified"] == 16
            assert original["producer_code_version"] == (
                "602ea2a44fec7881311af05eb5610de20ddb07219b220c50ff75f618d11960d6"
            )
        for entry, payload in zip(entries, replay["payloads"]):
            actual = json.loads((DATA_DIR / manifest_mod.analysis_relative_path(entry)).read_bytes())
            assert _export_approved_entry(entry) == payload == actual
        assert published_executive.__wrapped__(executive_payload) == json.loads(
            (DATA_DIR / "executive.json").read_bytes()
        )
        changed = {**entries[-1], "version": "f" * 64}
        with pytest.raises(AssertionError, match="not replayed"):
            _export_approved_entry(changed)

        # A refusal by the pinned verifier must still fail the helper. The
        # successful historical replay above cannot become an approval bypass.
        _replay_published_cohorts.cache_clear()
        if native:
            from src.publish import afac_history_parent

            monkeypatch.setattr(afac_history_parent, "replay_parent", later_runtime_refuses)
        else:
            monkeypatch.setattr(frozen_data, "verify_baseline_approvals", later_runtime_refuses)
        with pytest.raises(ValueError, match="Simulated later runtime"):
            _replay_published_cohorts()
    finally:
        _replay_published_cohorts.cache_clear()


def test_site_flights_and_executive_data_match_a_fresh_export(
    request: pytest.FixtureRequest, tmp_path: Path, flight_payload: dict, published_executive: dict
) -> None:
    """Reconstruct financial data; preserve the separately approved monthly map."""

    _require_site(request)
    out_dir = tmp_path / "data" / "v1"
    export_executive(published_executive, out_dir, skip_input_check=True)
    with _comparison_site() as comparison:
        assert_flight_data_parity(SITE_DIR, comparison, SITE_DIR.parent, out_dir, flight_payload, _baseline_json)
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
    """The economy tab renders the payload's exact raw values at the approved
    one-decimal card precision; the full records retain their source precision.

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
        view = views[period_id]
        kpis_by_key = {item["key"]: item for item in view["kpis"]}
        expected_values = {}
        for key in READER_KPI_KEYS:
            raw = kpis_by_key[key].get("value")
            raw = records[period_id][key] if raw is None else raw
            scale, suffix = (1e9, " mil M") if key == "ask_km" else (1, " ¢ USD")
            expected_values[key] = "No disponible" if raw is None else f"{raw / scale:,.1f}{suffix}"
        margin = records[period_id]["unit_margin_cents_per_km"]
        expected_values["unit_margin_cents_per_km"] = f"{'+' if margin >= 0 else ''}{margin:.1f} ¢ USD"
        # A delayed reading must not block the global quarter or the exact
        # numeric KPI values. Wait for all three before comparing.
        site_page.wait_for_function(
            "([label, first, last, values]) => "
            "document.getElementById('period-display').textContent.trim() === label && "
            "document.getElementById('period-prev').disabled === first && "
            "document.getElementById('period-next').disabled === last && "
            "Object.entries(values).every(([key, value]) => "
            "document.getElementById('kpi-' + key + '-value').textContent.trim() === value)",
            arg=[
                view["period_label"],
                period_id == period_ids[0],
                period_id == period_ids[-1],
                expected_values,
            ],
        )
        observed = _kpi_values(site_page)
        for key in READER_KPI_KEYS:
            assert observed[key] == expected_values[key], f"{key} mismatch at {period_id}"
        margin = records[period_id]["unit_margin_cents_per_km"]
        expected_margin = f"{'+' if margin >= 0 else ''}{margin:.1f} ¢ USD"
        assert observed["unit_margin_cents_per_km"] == expected_margin, f"margin mismatch at {period_id}"
        if period_id != period_ids[0]:
            site_page.click("#period-prev")


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

    assert_reading_parity(site_page, site_server, expected)
