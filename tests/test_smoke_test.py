from src.smoke_test import PROBES, ProbeResult, SourceProbe, run_probes


def test_smoke_test_covers_eight_sources() -> None:
    assert len(PROBES) == 8
    assert len({probe.name for probe in PROBES}) == 8
    eia = next(probe for probe in PROBES if probe.name == "EIA API")
    assert eia.credential_env == "EIA_API_KEY"


def test_one_probe_failure_does_not_abort_matrix() -> None:
    def fake_probe(probe: SourceProbe) -> ProbeResult:
        if probe.name == PROBES[2].name:
            raise RuntimeError("synthetic failure")
        return ProbeResult(
            source=probe.name,
            url=probe.url,
            final_url=probe.url,
            http_status=200,
            accessible_with_httpx="yes",
            requires_playwright="no",
            requires_computer_use="no",
            duration_ms=1.0,
            notes="ok",
        )

    results = run_probes(fake_probe)

    assert len(results) == 8
    failed = next(result for result in results if result.source == PROBES[2].name)
    assert failed.accessible_with_httpx == "no"
    assert "synthetic failure" in failed.notes
