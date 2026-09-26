"""Shared fixtures and marker configuration for the test suite.

See ``docs/arquitectura/auditoria-arquitectura-20260926.md`` §2.5 and §5
("Fase 0") for the audit that motivated this file.

Markers
-------
``local_data``
    The test needs locally-restored data that is gitignored and absent in a
    public clone: ``data/warehouse.duckdb``, ``data/silver``,
    ``data/bronze`` raw captures beyond the provenance manifests, private
    Gold cubes, or ``analysis_runs/``. Such tests are skipped with an
    explicit reason when that data is absent, unless ``--require-local-data``
    is passed, in which case the missing data turns the skip into a failure
    (for local use before publishing, when the data is expected to exist).
``slow``
    The test takes more than roughly 5 seconds on its own.
``browser``
    The test drives a real browser through Playwright.

Fixtures
--------
``flight_payload`` / ``executive_payload``
    Session-scoped: ``src.dashboard.flights.build_flight_payload()`` and
    ``src.dashboard.executive_summary.build_executive_payload()`` are each
    expensive (see the audit) and are rebuilt from the same warehouse state
    by many tests. They are built once per test session and reused. Tests
    must not mutate the returned dict in place; a test that needs to modify
    it should ``copy.deepcopy`` it first.
"""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

import pytest

from src.config import PATHS

WEB_ROOT = PATHS.root / "web"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--require-local-data",
        action="store_true",
        default=False,
        help=(
            "Turn a missing-local-data skip (marker 'local_data') into a "
            "failure instead. Use locally, with data/warehouse.duckdb, "
            "data/silver, data/bronze and analysis_runs/ restored, before "
            "publishing, so an absent restore is caught instead of silently "
            "skipped."
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "local_data: needs locally-restored data that is gitignored and "
        "absent in a public clone (data/warehouse.duckdb, data/silver, "
        "data/bronze raw captures, private Gold cubes, analysis_runs/); "
        "skipped with a reason when absent unless --require-local-data is "
        "passed.",
    )
    config.addinivalue_line("markers", "slow: takes more than about 5 seconds to run.")
    config.addinivalue_line("markers", "browser: drives a real browser through Playwright.")


@lru_cache(maxsize=1)
def _missing_local_data_reason() -> str | None:
    """Return why local data looks absent, or ``None`` when it looks present.

    Cached for the process: the filesystem state this checks does not change
    within a test run, and the check would otherwise run for every
    ``local_data``-marked item.
    """
    if not PATHS.warehouse.exists():
        return (
            f"local_data: {PATHS.warehouse} is absent. It is gitignored and "
            "local-only; restore it (see AGENTS.md) before running this test, "
            "or pass --require-local-data to turn this skip into a failure."
        )
    if not PATHS.silver.exists() or not any(PATHS.silver.iterdir()):
        return (
            f"local_data: {PATHS.silver} is absent or empty. Silver "
            "normalization is gitignored and local-only."
        )
    if not (PATHS.root / "analysis_runs").exists():
        return (
            "local_data: analysis_runs/ is absent. The Analysis Agent's "
            "draft/approval/publication ledger is gitignored and local-only."
        )
    return None


def pytest_runtest_setup(item: pytest.Item) -> None:
    if item.get_closest_marker("local_data") is None:
        return
    reason = _missing_local_data_reason()
    if reason is None:
        return
    if item.config.getoption("--require-local-data"):
        pytest.fail(reason, pytrace=False)
    pytest.skip(reason)


@pytest.fixture(scope="session")
def flight_payload() -> dict[str, Any]:
    """The Vuelos payload, built once per session from the local warehouse.

    Do not mutate this dict: tests that need to change it should
    ``copy.deepcopy(flight_payload)`` first.
    """
    from src.dashboard.flights import build_flight_payload

    return build_flight_payload()


@pytest.fixture(scope="session")
def executive_payload() -> dict[str, Any]:
    """The executive summary payload, built once per session.

    Do not mutate this dict: tests that need to change it should
    ``copy.deepcopy(executive_payload)`` first.
    """
    from src.dashboard.executive_summary import build_executive_payload

    return build_executive_payload()


@pytest.fixture(scope="session")
def web_dist_dir() -> Path:
    """Build web/ once per session with Vite and return web/dist/.

    P5 (see docs/arquitectura/auditoria-arquitectura-20260926.md Fase 4):
    the smoke/parity tests below serve the BUILT site, not raw src/, so
    they exercise the same bundling the published GitHub Pages build will
    use. Skips (not fails) with a clear reason when node/npm are missing
    or `npm ci` has not been run, since this checkout might not have
    Node installed at all; `npm run build` itself is deterministic (two
    consecutive runs produce byte-identical dist/), so building once per
    session and reusing dist/ for every test in it is safe.
    """
    npm = shutil.which("npm")
    if npm is None:
        pytest.skip("web_dist_dir: npm is not on PATH; install Node 22 + npm 10 to run the web/ browser tests.")
    if not (WEB_ROOT / "node_modules").exists():
        result = subprocess.run([npm, "ci"], cwd=WEB_ROOT, capture_output=True, text=True)
        if result.returncode != 0:
            pytest.skip(f"web_dist_dir: `npm ci` failed in {WEB_ROOT}:\n{result.stdout}\n{result.stderr}")
    result = subprocess.run([npm, "run", "build"], cwd=WEB_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        pytest.fail(f"web_dist_dir: `npm run build` failed in {WEB_ROOT}:\n{result.stdout}\n{result.stderr}", pytrace=False)
    dist = WEB_ROOT / "dist"
    assert (dist / "index.html").exists(), f"web_dist_dir: {dist}/index.html missing after a successful build"
    return dist
