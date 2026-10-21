"""Contract tests only: live availability is reported separately, never mocked as ready."""

import json
import shutil
from datetime import datetime
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest

from src.source_updates import gdelt
from src.source_updates.catalog import ROOT
from src.source_updates.collection import collect

AS_OF = "2026-10-21T12:00:00-06:00"
SOURCE = dict(downloaded_at="2026-10-20T12:00:00Z", source_file="news/gdelt/test.json", sha256="a" * 64)
ARTICLE = dict(
    url="https://publisher.test/article?utm_source=x",
    title="Metadata title",
    seendate="20260901T060000Z",
    domain="publisher.test",
    language="Spanish",
)


def test_month_boundary_uses_mexico_zone_including_historical_dst():
    from urllib.parse import parse_qs, urlsplit

    q = parse_qs(urlsplit(gdelt.recipe("2021M07", AS_OF)["items"][0]["url"]).query)
    assert q["startdatetime"] == ["20210701050000"]
    assert q["enddatetime"] == ["20210801045959"]
    q = parse_qs(urlsplit(gdelt.recipe("2026M09", AS_OF)["items"][0]["url"]).query)
    assert q["startdatetime"] == ["20260901060000"]
    assert q["enddatetime"] == ["20261001055959"]


def test_observation_metadata_keeps_all_contributors_without_publication_invention():
    second = dict(ARTICLE, title="Revised title", url="https://publisher.test/article")
    output, details = gdelt.normalize({"articles": [ARTICLE, second]}, "2026M09", SOURCE, AS_OF)
    assert details["rows"] == 1 and details["duplicate_contributions"] == 1
    row = output["rows"][0]
    assert row["published_at"] is None and row["event_date"] is None
    assert row["agent_eligible"] is False
    assert [r["source_locator"] for r in row["contributors"]] == ["/articles/0", "/articles/1"]
    assert row["contributors"][0]["metadata"]["tone"] is None
    assert output["complete_month_certified"] is False


@pytest.mark.parametrize(
    "payload",
    [
        {"error": "unavailable"},
        {"articles": None},
        {"articles": [{}]},
        {"articles": [dict(ARTICLE, seendate="20260831T235959Z")]},
        {"articles": [dict(ARTICLE, url="https://user:password@publisher.test/a")]},
        {"articles": [dict(ARTICLE, seendate="20260901")]},
        {"articles": [ARTICLE] * 251},
    ],
)
def test_invalid_payload_or_outside_query_fails_closed(payload):
    with pytest.raises(ValueError):
        gdelt.normalize(payload, "2026M09", SOURCE, AS_OF)


def test_empty_result_never_certifies_absence_or_complete_month():
    output, details = gdelt.normalize({"articles": []}, "2026M09", SOURCE, AS_OF)
    assert output["rows"] == [] and details["empty_result_is_not_absence_of_news"]
    assert not output["complete_month_certified"]


@pytest.fixture
def workspace():
    path = ROOT / "tmp/source-updates" / ("pytest-gdelt-" + uuid4().hex)
    yield path
    if path.exists():
        shutil.rmtree(path)


def capture(workspace, *, articles=None):
    class Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def request(self, method, url, **kw):
            return httpx.Response(
                200,
                content=json.dumps({"articles": [ARTICLE] if articles is None else articles}).encode(),
                request=httpx.Request(method, url),
            )

    # Freeze only the synthetic Bronze capture clock. Wall-clock time must not
    # eventually move this fixture past its intentionally historical cutoff.
    with patch("src.common.storage._utc_now", return_value=datetime.fromisoformat(SOURCE["downloaded_at"])):
        return collect(gdelt.recipe("2026M09", AS_OF), workspace, execute=True, client_factory=Client)


def test_candidate_round_replay_immutable_and_tamper_detection(workspace):
    receipt = capture(workspace)
    # The fixture is a contract exercise, never a claim of real extraction.
    result = gdelt.run(workspace, "2026M09", AS_OF, receipt["run_id"], execute=True)
    assert result["rows"] == 1 and result["agent_eligible"] is False
    checked = gdelt.run(workspace, "2026M09", AS_OF, receipt["run_id"], check=True)
    assert result["output_sha256"] == checked["output_sha256"]
    with pytest.raises(ValueError, match="immutable"):
        gdelt.run(workspace, "2026M09", AS_OF, receipt["run_id"], execute=True)
    target = workspace / "data" / gdelt.OUTPUTS[1]
    changed = json.loads(target.read_text())
    changed["rows"][0]["published_at"] = "2026-09-01"
    target.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match="source replay"):
        gdelt.run(workspace, "2026M09", AS_OF, receipt["run_id"], check=True)


def test_failed_collection_never_constructs_candidate(workspace):
    (workspace / "receipts").mkdir(parents=True)
    run_id = "a" * 32
    (workspace / "receipts" / f"collection-{run_id}.json").write_text(
        json.dumps({"status": "incomplete", "items": [{"http_status": 503}]})
    )
    with pytest.raises(ValueError, match="successful GDELT"):
        gdelt.run(workspace, "2026M09", AS_OF, run_id, execute=True)
    assert not (workspace / "data").exists()


def test_dry_run_never_reads_missing_receipt_or_writes(workspace):
    result = gdelt.run(workspace, "2026M09", AS_OF, "a" * 32)
    assert result["mode"] == "dry_run" and not workspace.exists()


@pytest.mark.parametrize("articles,exit_code", [([], 1), ([ARTICLE], 0)])
def test_cli_certification_exit_tracks_real_candidate_status(workspace, capsys, articles, exit_code):
    # Exercise the actual collector, normalizer, receipt and CLI offline.
    # Synthetic responses test the process contract, never live source readiness.
    receipt = capture(workspace, articles=articles)
    args = [
        "certify",
        "--period",
        "2026M09",
        "--as-of",
        AS_OF,
        "--workspace",
        str(workspace),
        "--collection",
        receipt["run_id"],
    ]
    for mode in ("--execute", "--check"):
        assert gdelt.main([*args, mode]) == exit_code
        result = json.loads(capsys.readouterr().out)
        assert result["status"] == ("empty_result_unproven_coverage" if exit_code else "checks_passed")
        assert result["activation"] == "none"
        assert result["publication"] == "not_authorized"


@pytest.mark.parametrize("action", ["recipe", "certify"])
def test_cli_planning_succeeds_without_reading_source_or_writing(workspace, capsys, action):
    args = [action, "--period", "2026M09", "--as-of", AS_OF, "--dry-run"]
    if action == "certify":
        args += ["--workspace", str(workspace), "--collection", "a" * 32]
    assert gdelt.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["activation"] == "none"
    assert not workspace.exists()


def test_real_capture_after_historical_cutoff_still_rejected():
    source = dict(SOURCE, downloaded_at="2026-10-22T00:00:00Z")
    with pytest.raises(ValueError, match="capture is after"):
        gdelt.normalize({"articles": [ARTICLE]}, "2026M09", source, AS_OF)
