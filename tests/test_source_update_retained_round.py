"""Batch stages are explicit, offline, immutable and stop on incomplete source semantics."""

import pytest

from src.source_updates.retained_round import execute
from tests.test_source_update_retained import candidate as retained_fixture

candidate = retained_fixture


def recipe(source, selected, period="2026M07"):
    return dict(
        version=1,
        source_root=str(source),
        as_of="2026-10-19T12:00:00-06:00",
        items=[dict(product="afac_airports", period=period, originals=selected)],
    )


def test_default_batch_is_only_a_plan_and_success_is_fully_replayed(candidate):
    workspace, source, selected = candidate
    preview = execute(recipe(source, selected), workspace)
    assert preview["mode"] == "dry_run" and not workspace.exists()
    assert preview["network_requests"] == 0 and not preview["new_source_capture"]
    output = execute(recipe(source, selected), workspace, write=True)
    assert output["status"] == "checks_passed" and output["results"][0]["offline_replay_identical"]
    assert output["results"][0]["rows"] == 42 and output["activation"] == "none"
    with pytest.raises(ValueError, match="empty workspace"):
        execute(recipe(source, selected), workspace, write=True)


def test_failed_second_product_stops_and_preserves_first_candidate(candidate):
    workspace, source, selected = candidate
    proposal = recipe(source, selected)
    proposal["items"].append(dict(product="afac_airports", period="2026M06", originals=selected))
    output = execute(proposal, workspace, write=True)
    assert output["status"] == "blocked" and len(output["results"]) == 1
    assert output["results"][0]["status"] == "checks_passed" and output["remaining_products_not_started"] == 0
    assert "afac_airports-2026M06" in output["failed_target"]
    assert (workspace / "afac_airports-2026M07/data/gold/fact_afac_airport_observations.parquet").exists()
    assert not (workspace / "afac_airports-2026M06/data/gold").exists()
    assert output["publication"] == "not_authorized"


def test_duplicate_open_period_and_implicit_baseline_batches_block_before_writes(candidate):
    workspace, source, selected = candidate
    proposal = recipe(source, selected)
    proposal["items"] *= 2
    with pytest.raises(ValueError, match="Duplicate"):
        execute(proposal, workspace)
    proposal = recipe(source, selected, period="2026M10")
    with pytest.raises(ValueError, match="closed"):
        execute(proposal, workspace)
    proposal = recipe(source, selected)
    proposal["items"][0]["baseline"] = "baselines/prior.parquet"
    with pytest.raises(ValueError, match="no implicit baseline"):
        execute(proposal, workspace)
    assert not workspace.exists()


def test_pdf_parser_exception_preserves_prior_success_and_writes_blocked_receipt(candidate, monkeypatch):
    from pypdf.errors import PdfReadError
    from src.source_updates import retained_round

    workspace, source, selected = candidate
    proposal = recipe(source, selected)
    proposal["items"].append(dict(product="afac_airports", period="2026M06", originals=selected))
    original = retained_round.run

    def parse_failure(*args, **kwargs):
        if args[2] == "2026M06":
            raise PdfReadError("malformed retained PDF test")
        return original(*args, **kwargs)

    monkeypatch.setattr(retained_round, "run", parse_failure)
    output = execute(proposal, workspace, write=True)
    assert (
        output["status"] == "blocked"
        and output["failed_action"] == "certify"
        and output["error_type"] == "PdfReadError"
    )
    assert len(output["results"]) == 1 and len(list(workspace.glob("retained-round-*.json"))) == 1
