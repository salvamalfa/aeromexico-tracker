"""Preparation-only boundaries; no synthetic specimen proves real extraction."""

from copy import deepcopy
from decimal import Decimal

import pytest

from src.source_updates import volaris_q3_reconstructed as q3
from src.source_updates.carrier_source_candidate import period_check


def test_filing_context_preserves_separate_dates_and_exact_upstream_roles():
    context = dict(q3.FILING, source_urls=dict(q3.URLS))
    assert q3.validate_filing_context(context) == context
    context["acceptance_at"] = "2026-10-26T15:31:25-06:00"
    assert q3.validate_filing_context(context)["acceptance_at"] == "2026-10-26T21:31:25Z"
    changes = [
        ("cik", "0001561861"),
        ("accession_number", "0001292814-26-003836"),
        ("report_date", "2026-06-30"),
        ("filing_date", "2026-10-26"),
        ("acceptance_at", "2026-10-27T21:31:25Z"),
        ("acceptance_at", "2026-10-26T21:31:25"),
        ("primary_document", "ex99-1.htm"),
    ]
    for key, value in changes:
        bad = deepcopy(context)
        bad[key] = value
        with pytest.raises(ValueError):
            q3.validate_filing_context(bad)
    for role in q3.URLS:
        bad = deepcopy(context)
        bad["source_urls"][role] += "?substitute=true"
        with pytest.raises(ValueError):
            q3.validate_filing_context(bad)


def test_contexts_keep_quarter_ytd_and_balance_distinct():
    assert q3.reporting_context("quarter", 2026) == ("quarter", "2026Q3", "2026-07-01", "2026-09-30")
    assert q3.reporting_context("year_to_date", 2025) == (
        "year_to_date",
        "2025YTD09",
        "2025-01-01",
        "2025-09-30",
    )
    assert q3.reporting_context("instant", 2025, quarter=4) == ("instant", "2025-12-31", None, "2025-12-31")
    assert q3.reporting_context("instant", 2026, quarter=2) == ("instant", "2026-06-30", None, "2026-06-30")
    for kind, year, quarter in [
        ("quarter", 2026, 2),
        ("half_year", 2026, 3),
        ("year_to_date", 2026, 4),
        ("year", 2026, 3),
        ("quarter", 2027, 3),
        ("instant", 2026, 4),
        ("instant", True, 3),
        ("quarter", 2026.0, 3),
        ("quarter", Decimal("2026"), 3),
        ("quarter", 2026, 3.0),
    ]:
        with pytest.raises(ValueError):
            q3.reporting_context(kind, year, quarter=quarter)


def test_transcription_is_exact_even_when_reconciliation_tolerance_is_five_percent():
    # Contract examples only, not report figures or verified source observations.
    assert q3.native_value("(1,234)", -1234, unit="usd", scale=1_000_000) == -1234
    assert q3.native_value("(0.0%)", -0.0, unit="percent", scale=0.01) == Decimal("-0.0")
    assert q3.native_value("-", None, unit="usd", scale=1_000_000) is None
    for raw, value, unit, scale in [
        ("-", 0, "usd", 1_000_000),
        ("100", 104, "usd", 1_000_000),
        ("100", 100, "usd", 1_000),
        ("80%", 80, "percent", 1),
        ("80", 80, "percent", 0.01),
        ("8.0%", 8, "usd_cents_per_seat_mile", 1),
        ("3.5", 3.5, "aircraft", 1),
        ("(3)", -3, "shares", 1),
        ("1", True, "aircraft", 1),
        ("1", 1, "aircraft", True),
        ("1", "1", "aircraft", 1),
        ("1", 1, "aircraft", "1"),
        ("1", 1, "available_seat_kilometers", 1_000_000),
    ]:
        with pytest.raises(ValueError):
            q3.native_value(raw, value, unit=unit, scale=scale)


def test_preparation_cannot_close_q3_readiness_or_relabel_asur_as_sec_originals():
    planned = q3.preparation()
    assert planned["status"] == "prepared_waiting_verified_Library_derivatives"
    assert planned["native_rows_certified"] == planned["network_requests"] == 0
    assert not planned["ready_for_calendar_incorporation"]
    assert not planned["latest_source_availability_verified"]
    assert planned["source_original_sha256"] is planned["artifact_derivative_sha256"] is None
    assert planned["source_observed_at"] is planned["source_http_status"] is None
    assert planned["activation"] == "none" and planned["publication"] == "not_authorized"
    # Q3 now has a separate explicit derivative path, never the old four SEC roles.
    period_check("volaris_sec", "2026Q3")
    from src.source_updates.volaris_sec_source import read

    with pytest.raises(ValueError, match="reconstruction ZIP"):
        read({role: (b"unverified", {}) for role in ("html", "primary", "index", "submissions")}, "2026Q3")


def test_reconstructed_packet_record_never_acquires_original_http_or_early_capture(monkeypatch):
    import hashlib

    from src.source_updates import volaris_q3_inputs as inputs

    # Synthetic identity for a metadata contract test, not an imported source.
    identity = "libfile_" + "a" * 32
    monkeypatch.setattr(inputs, "LIBRARY_SHA", hashlib.sha256(identity.encode()).hexdigest())
    row = dict(
        source_system=q3.ALIAS,
        source_url=q3.URLS["exhibit"],
        sha256=inputs.SHA,
        bytes=inputs.SIZE,
        representation_role=inputs.ROLE,
        representation_kind="authorized_visible_reconstruction",
        download_method="authorized_visible_reconstruction_import",
        http_status=0,
        source_http_status=None,
        source_original_sha256=None,
        source_original_bytes_acquired=False,
        source_observed_at=inputs.VERIFIED_AT,
        downloaded_at="2026-10-28T13:20:00Z",
        timestamp_semantics="local_import_not_SEC_HTTP_capture",
        source_url_role="upstream_visible_reference_not_artifact_download_URL",
        content_type="application/zip",
        library_file_id=identity,
    )
    inputs.validate_record(row)
    for key, value in [
        ("downloaded_at", "2026-10-28T12:00:00Z"),
        ("downloaded_at", "2026-10-28T14:00:00"),
        ("http_status", 200),
        ("http_status", False),
        ("source_http_status", 200),
        ("source_original_sha256", "a" * 64),
        ("source_original_bytes_acquired", True),
        ("source_system", "sec"),
        ("source_observed_at", "2026-10-29T13:16:03Z"),
        ("library_file_id", "libfile_" + "b" * 32),
    ]:
        with pytest.raises(ValueError):
            inputs.validate_record(dict(row, **{key: value}))


def test_reconstructed_packet_and_original_roles_remain_disjoint():
    from src.source_updates.availability_volaris_q3_reconstructed import SCOPE, preflight
    from src.source_updates.carrier_source_contract import retention_specs
    from src.source_updates.catalog import ROOT
    from src.source_updates.volaris_q3_inputs import decode

    spec = retention_specs()["volaris_sec"]
    assert {frozenset(v) for v in spec["role_sets"]} == {
        frozenset({"html", "primary", "index", "submissions"}),
        frozenset({"reconstruction_zip"}),
    }
    with pytest.raises(ValueError, match="not an SEC original"):
        decode(b"not the actual Library derivative")
    with pytest.raises(ValueError, match="disjoint"):
        source = ROOT / "tmp/source-updates/volaris-q3-contract-test-import"
        preflight(
            {"source_scope": SCOPE, "workspace": str(source), "run_id": "a" * 32}, str(source / "candidate")
        )
