"""Lightweight connectivity matrix for the eight Stage 0 source families."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
import json
import os
import time
from typing import Callable, Literal

import httpx

from src.config import MissingSecUserAgentError, SOURCE_URLS, get_sec_user_agent


ProbeState = Literal["yes", "no", "unknown", "not_tested"]


@dataclass(frozen=True, slots=True)
class SourceProbe:
    name: str
    url: str
    sec_identity_required: bool = False
    credential_env: str | None = None


@dataclass(frozen=True, slots=True)
class ProbeResult:
    source: str
    url: str
    final_url: str | None
    http_status: int | None
    accessible_with_httpx: ProbeState
    requires_playwright: ProbeState
    requires_computer_use: ProbeState
    duration_ms: float
    notes: str


PROBES: tuple[SourceProbe, ...] = (
    SourceProbe("SEC submissions", SOURCE_URLS["sec_submissions"], True),
    SourceProbe("SEC companyfacts", SOURCE_URLS["sec_companyfacts"], True),
    SourceProbe("Aeromexico IR", SOURCE_URLS["aeromexico_ir"]),
    SourceProbe("BMV XBRL", SOURCE_URLS["bmv_xbrl"]),
    SourceProbe("AFAC statistics", SOURCE_URLS["afac_statistics"]),
    SourceProbe("BTS TranStats", SOURCE_URLS["bts_transtats"]),
    SourceProbe("Banxico SIE", "https://www.banxico.org.mx/SieAPIRest/service/v1/token"),
    SourceProbe("EIA API", SOURCE_URLS["eia_api"], credential_env="EIA_API_KEY"),
)


def probe_url(probe: SourceProbe, *, timeout_seconds: float = 20.0) -> ProbeResult:
    """Read at most the first small response chunk and classify direct access."""

    headers = {
        "Accept": "*/*",
        "Range": "bytes=0-2047",
        "User-Agent": "Aeromexico-Tracker/0.1",
    }
    if probe.sec_identity_required:
        try:
            headers["User-Agent"] = get_sec_user_agent()
        except MissingSecUserAgentError as exc:
            return ProbeResult(
                source=probe.name,
                url=probe.url,
                final_url=None,
                http_status=None,
                accessible_with_httpx="not_tested",
                requires_playwright="unknown",
                requires_computer_use="unknown",
                duration_ms=0.0,
                notes=str(exc),
            )

    started = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
            with client.stream("GET", probe.url, headers=headers) as response:
                for _ in response.iter_bytes(chunk_size=2048):
                    break
                status = response.status_code
                final_url = str(response.url)
    except httpx.HTTPError as exc:
        return ProbeResult(
            source=probe.name,
            url=probe.url,
            final_url=None,
            http_status=None,
            accessible_with_httpx="no",
            requires_playwright="unknown",
            requires_computer_use="unknown",
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            notes=f"{type(exc).__name__}: {exc}",
        )

    duration_ms = round((time.perf_counter() - started) * 1000, 3)
    if 200 <= status < 400:
        return ProbeResult(
            source=probe.name,
            url=probe.url,
            final_url=final_url,
            http_status=status,
            accessible_with_httpx="yes",
            requires_playwright="no",
            requires_computer_use="no",
            duration_ms=duration_ms,
            notes="Direct HTTP access succeeded.",
        )
    if status in {401, 407} or (
        status == 403 and probe.credential_env and not os.getenv(probe.credential_env, "").strip()
    ):
        return ProbeResult(
            source=probe.name,
            url=probe.url,
            final_url=final_url,
            http_status=status,
            accessible_with_httpx="yes",
            requires_playwright="no",
            requires_computer_use="no",
            duration_ms=duration_ms,
            notes=(
                f"Endpoint is reachable but requires {probe.credential_env}."
                if probe.credential_env
                else "Endpoint is reachable but requires credentials."
            ),
        )
    if status in {403, 429}:
        return ProbeResult(
            source=probe.name,
            url=probe.url,
            final_url=final_url,
            http_status=status,
            accessible_with_httpx="no",
            requires_playwright="unknown",
            requires_computer_use="unknown",
            duration_ms=duration_ms,
            notes="Direct HTTP was blocked; browser verification is required.",
        )
    return ProbeResult(
        source=probe.name,
        url=probe.url,
        final_url=final_url,
        http_status=status,
        accessible_with_httpx="no",
        requires_playwright="unknown",
        requires_computer_use="unknown",
        duration_ms=duration_ms,
        notes=f"Endpoint returned HTTP {status}; verify URL and access method.",
    )


def run_probes(
    probe_function: Callable[[SourceProbe], ProbeResult] = probe_url,
) -> list[ProbeResult]:
    """Probe every configured source without allowing one failure to stop the matrix."""

    results: list[ProbeResult] = []
    for probe in PROBES:
        try:
            results.append(probe_function(probe))
        except Exception as exc:  # Defensive boundary for a diagnostic command.
            results.append(
                ProbeResult(
                    source=probe.name,
                    url=probe.url,
                    final_url=None,
                    http_status=None,
                    accessible_with_httpx="no",
                    requires_playwright="unknown",
                    requires_computer_use="unknown",
                    duration_ms=0.0,
                    notes=f"Unexpected {type(exc).__name__}: {exc}",
                )
            )
    return results


def run_playwright_fallbacks(
    results: list[ProbeResult],
    *,
    timeout_ms: int = 45_000,
) -> list[ProbeResult]:
    """Try headless Chromium only for direct-HTTP failures that need classification."""

    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright

    updated = list(results)
    candidate_indexes = [
        index
        for index, result in enumerate(updated)
        if result.accessible_with_httpx == "no" and result.requires_playwright == "unknown"
    ]
    if not candidate_indexes:
        return updated

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent="Aeromexico-Tracker/0.1 connectivity-check",
                locale="en-US",
            )
            for index in candidate_indexes:
                original = updated[index]
                page = context.new_page()
                started = time.perf_counter()
                try:
                    response = page.goto(
                        original.url,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    )
                    status = response.status if response else None
                    title = page.title().strip()
                    duration_ms = round((time.perf_counter() - started) * 1000, 3)
                    if status is not None and 200 <= status < 400:
                        updated[index] = replace(
                            original,
                            final_url=page.url,
                            http_status=status,
                            requires_playwright="yes",
                            requires_computer_use="no",
                            duration_ms=duration_ms,
                            notes=(
                                "Headless Chromium succeeded"
                                + (f"; page title: {title}" if title else "")
                                + "."
                            ),
                        )
                    else:
                        updated[index] = replace(
                            original,
                            final_url=page.url,
                            http_status=status,
                            requires_playwright="no",
                            requires_computer_use="unknown",
                            duration_ms=duration_ms,
                            notes=f"Headless Chromium returned HTTP {status or 'unknown'}.",
                        )
                except (PlaywrightTimeoutError, PlaywrightError) as exc:
                    updated[index] = replace(
                        original,
                        final_url=page.url or None,
                        requires_playwright="no",
                        requires_computer_use="unknown",
                        duration_ms=round((time.perf_counter() - started) * 1000, 3),
                        notes=f"Headless Chromium failed: {type(exc).__name__}: {exc}",
                    )
                finally:
                    page.close()
            context.close()
        finally:
            browser.close()
    return updated


def _print_table(results: list[ProbeResult]) -> None:
    headers = ("Source", "HTTP", "Status", "Playwright", "Computer use", "Notes")
    rows = [
        (
            result.source,
            result.accessible_with_httpx,
            str(result.http_status or "-"),
            result.requires_playwright,
            result.requires_computer_use,
            result.notes,
        )
        for result in results
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in rows))
        for index in range(len(headers))
    ]
    print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    parser.add_argument(
        "--with-playwright",
        action="store_true",
        help="Use headless Chromium only for direct-HTTP failures.",
    )
    args = parser.parse_args()
    results = run_probes()
    if args.with_playwright:
        results = run_playwright_fallbacks(results)
    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2, ensure_ascii=False))
    else:
        _print_table(results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
