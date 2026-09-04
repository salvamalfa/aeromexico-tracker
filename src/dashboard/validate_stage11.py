"""Acceptance checks for the Stage 11 executive HTML prototype."""

from __future__ import annotations

from bs4 import BeautifulSoup

from src.dashboard.executive_summary import build_executive_payload
from src.dashboard.executive_summary_html import DEFAULT_OUTPUT


def main() -> None:
    payload = build_executive_payload()
    document = DEFAULT_OUTPUT.read_text(encoding="utf-8")
    soup = BeautifulSoup(document, "html.parser")
    checks = {
        "single_view": len(soup.select("main[data-testid='executive-summary-root']")) == 1,
        "no_other_pages": not soup.select("nav, [role='tablist'], [role='tab']"),
        "five_kpis": len(soup.select(".kpi-card")) == 5,
        "three_charts": len(soup.select(".chart[id]")) == 3,
        "all_backend_quarters": len(payload["records"])
        == payload["metadata"]["quarter_count"],
        "coverage": payload["metadata"]["first_period"] == "2021Q1"
        and payload["metadata"]["last_period"] == "2026Q2",
        "default_latest": payload["metadata"]["default_period"] == "2026Q2",
        "one_disclosure": len(soup.select("details.disclosure")) == 1,
        "period_stepper": soup.select_one("#period-prev") is not None
        and soup.select_one("#period-next") is not None,
        "merged_reading": soup.select_one("#narrative-copy") is not None
        and soup.select_one("#insight-list") is None,
        "offline": not soup.select("script[src], link[href], iframe, img[src]"),
        "source_named": payload["metadata"]["source_view"]
        in soup.get_text(" ", strip=True),
        "official_history": payload["metadata"]["quarter_count"] == 22,
        "artifact_bounded": DEFAULT_OUTPUT.stat().st_size < 6_000_000,
    }
    failed = [name for name, passed in checks.items() if not passed]
    for name, passed in checks.items():
        print(f"{'PASS' if passed else 'FAIL'} — {name}")
    if failed:
        raise SystemExit(f"Stage 11 validation failed: {', '.join(failed)}")
    print(f"Stage 11 validation passed: {len(checks)}/{len(checks)}")


if __name__ == "__main__":
    main()
