from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.chat import finalize_stage2_campaign as finalizer
from scripts.chat import stage2_finalization_sources as source_validation
from scripts.chat.stage2_finalization import (
    conservative_usage_cost,
    derived_recovery_report,
    final_case_partition,
    read_pinned_sources,
    validate_terminal_recovery,
)
from src.conversational_analytics.evaluation_campaign import STAGE2_EXPECTED_CASE_IDS


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _private_output(monkeypatch, tmp_path: Path) -> Path:
    output = finalizer.SOURCE_ROOT / f"test-{tmp_path.name}"
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    monkeypatch.setattr(finalizer, "FINALIZATION_DIR", output)
    return output


def _write_source_set(tmp_path: Path, *, tamper: str | None = None) -> tuple[dict[str, Path], dict[str, str]]:
    paths: dict[str, Path] = {}
    approved: dict[str, str] = {}
    for name in finalizer.SOURCE_PATHS:
        raw = json.dumps({"name": name, "identity_hash": "b" * 64}, sort_keys=True).encode()
        paths[name] = tmp_path / f"{name}.json"
        paths[name].write_bytes(raw + (b" altered" if name == tamper else b""))
        approved[name] = _digest(raw)
    return paths, approved


def test_pinned_sources_accept_exact_content_copies(tmp_path: Path) -> None:
    paths, approved = _write_source_set(tmp_path)
    copied = {name: tmp_path / f"copy-{name}.json" for name in paths}
    for name, path in paths.items():
        copied[name].write_bytes(path.read_bytes())

    raw = read_pinned_sources(copied, approved)

    assert set(raw) == set(approved)
    assert all(_digest(raw[name]) == approved[name] for name in approved)


def test_rehashed_source_metadata_does_not_replace_fixed_raw_pin(tmp_path: Path) -> None:
    paths, approved = _write_source_set(tmp_path)
    # Tampering and recomputing every self-claimed JSON hash cannot change the trusted pin.
    changed = json.dumps({"name": "original_ledger", "identity_hash": "c" * 64}, sort_keys=True).encode()
    paths["original_ledger"].write_bytes(changed)
    with pytest.raises(ValueError, match="SHA-256 no aprobado"):
        read_pinned_sources(paths, approved)


def test_tampered_cli_source_blocks_before_preflight_or_private_writes(tmp_path: Path, monkeypatch) -> None:
    paths, approved = _write_source_set(tmp_path, tamper="original_ledger")
    monkeypatch.setattr(finalizer, "APPROVED_SOURCE_SHA256", approved)
    output = _private_output(monkeypatch, tmp_path)
    before = (
        {path.name: (_digest(path.read_bytes()), path.stat().st_mode & 0o777) for path in output.iterdir()}
        if output.exists()
        else None
    )
    calls = {"parse": 0, "mkdir": 0, "chmod": 0}
    real_mkdir = Path.mkdir
    real_chmod = finalizer.os.chmod

    def parse_must_not_run(raw: bytes, label: str):
        calls["parse"] += 1
        raise AssertionError("source parsing ran before raw hash validation")

    def count_mkdir(self, *args, **kwargs):
        calls["mkdir"] += 1
        return real_mkdir(self, *args, **kwargs)

    def count_chmod(path, mode):
        calls["chmod"] += 1
        return real_chmod(path, mode)

    monkeypatch.setattr(source_validation, "parse_pinned_object", parse_must_not_run)
    monkeypatch.setattr(Path, "mkdir", count_mkdir)
    monkeypatch.setattr(finalizer.os, "chmod", count_chmod)
    args = SimpleNamespace(
        source_paths=paths,
        output_dir=output,
        campaign_state=output / "campaign.json",
        plan_path=output / "finalization_plan.json",
        derived_report=output / "sol-low-recovered-case.json",
    )

    with pytest.raises(ValueError, match="SHA-256 no aprobado"):
        finalizer.prepare_finalization(args)

    assert calls == {"parse": 0, "mkdir": 0, "chmod": 0}
    after = (
        {path.name: (_digest(path.read_bytes()), path.stat().st_mode & 0o777) for path in output.iterdir()}
        if output.exists()
        else None
    )
    assert after == before


def test_source_symlink_is_rejected_before_reading_or_chmod(tmp_path: Path, monkeypatch) -> None:
    paths, approved = _write_source_set(tmp_path)
    monkeypatch.setattr(finalizer, "APPROVED_SOURCE_SHA256", approved)
    source_copy = tmp_path / "source-copy.json"
    source_copy.write_text("{}", encoding="utf-8")
    paths["original_ledger"].unlink()
    paths["original_ledger"].symlink_to(source_copy)
    output = _private_output(monkeypatch, tmp_path)
    monkeypatch.setattr(
        finalizer,
        "read_pinned_sources",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("source read before symlink check")),
    )
    chmod_calls = []
    monkeypatch.setattr(finalizer.os, "chmod", lambda path, mode: chmod_calls.append((path, mode)))
    args = SimpleNamespace(
        source_paths=paths,
        output_dir=output,
        campaign_state=output / "campaign.json",
        plan_path=output / "finalization_plan.json",
        derived_report=output / "sol-low-recovered-case.json",
    )

    with pytest.raises(ValueError, match="symlink"):
        finalizer.prepare_finalization(args)

    assert chmod_calls == []


def test_output_source_overlap_blocks_before_read_parse_or_parent_permission_change(
    tmp_path: Path, monkeypatch
) -> None:
    output = _private_output(monkeypatch, tmp_path)
    paths = dict(finalizer.SOURCE_PATHS)
    paths["original_ledger"] = output / "campaign.json"
    args = SimpleNamespace(
        source_paths=paths,
        output_dir=output,
        campaign_state=output / "campaign.json",
        plan_path=output / "finalization_plan.json",
        derived_report=output / "sol-low-recovered-case.json",
    )
    watched = [output.parent.parent.parent, output.parent.parent, output.parent, output]
    modes_before = [(path, path.stat().st_mode & 0o777 if path.exists() else None) for path in watched]
    calls = {"read": 0, "parse": 0, "preflight": 0, "mkdir": 0, "chmod": 0}

    def forbidden(name):
        def fail(*args, **kwargs):
            calls[name] += 1
            raise AssertionError(f"{name} ran before path overlap rejection")

        return fail

    monkeypatch.setattr(finalizer, "read_pinned_sources", forbidden("read"))
    monkeypatch.setattr(source_validation, "parse_pinned_object", forbidden("parse"))
    monkeypatch.setattr(finalizer, "prepare", forbidden("preflight"))
    monkeypatch.setattr(Path, "mkdir", forbidden("mkdir"))
    monkeypatch.setattr(finalizer.os, "chmod", forbidden("chmod"))

    with pytest.raises(ValueError, match="solaparse"):
        finalizer.prepare_finalization(args)

    assert calls == {key: 0 for key in calls}
    modes_after = [(path, path.stat().st_mode & 0o777 if path.exists() else None) for path in watched]
    assert modes_after == modes_before


def test_duplicate_output_leaf_paths_block_before_source_read(tmp_path: Path, monkeypatch) -> None:
    output = _private_output(monkeypatch, tmp_path)
    args = SimpleNamespace(
        source_paths=finalizer.SOURCE_PATHS,
        output_dir=output,
        campaign_state=output / "campaign.json",
        plan_path=output / "same.json",
        derived_report=output / "same.json",
    )
    monkeypatch.setattr(
        finalizer,
        "read_pinned_sources",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("source read before output validation")),
    )

    with pytest.raises(ValueError, match="destinos distintos"):
        finalizer.prepare_finalization(args)


@pytest.mark.parametrize("output_leaf", ["sol-low-recovered-case.json", "campaign.json"])
def test_hardlinked_output_rejected_before_read_or_write_and_source_remains_intact(
    tmp_path: Path, monkeypatch, output_leaf: str
) -> None:
    paths, approved = _write_source_set(tmp_path)
    monkeypatch.setattr(finalizer, "APPROVED_SOURCE_SHA256", approved)
    output = _private_output(monkeypatch, tmp_path)
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    linked_output = output / output_leaf
    assert not linked_output.exists()
    source_bytes = paths["original_ledger"].read_bytes()
    shared_source = output.parent / f"{tmp_path.name}-source.json"
    assert not shared_source.exists()
    shared_source.write_bytes(source_bytes)
    paths["original_ledger"] = shared_source
    approved["original_ledger"] = _digest(source_bytes)
    monkeypatch.setattr(finalizer, "APPROVED_SOURCE_SHA256", approved)
    original_sha = _digest(shared_source.read_bytes())
    linked_output.hardlink_to(shared_source)
    parent_modes = [(path, path.stat().st_mode & 0o777) for path in (output.parent, output)]
    args = SimpleNamespace(
        source_paths=paths,
        output_dir=output,
        campaign_state=linked_output if output_leaf == "campaign.json" else output / "campaign.json",
        plan_path=output / "finalization_plan.json",
        derived_report=(
            linked_output
            if output_leaf == "sol-low-recovered-case.json"
            else output / "sol-low-recovered-case.json"
        ),
    )
    calls = {"read": 0, "mkdir": 0, "chmod": 0}

    def fail_read(*a, **k):
        calls["read"] += 1
        raise AssertionError("source read before hardlink rejection")

    def fail_mutation(name):
        def fail(*a, **k):
            calls[name] += 1
            raise AssertionError(f"{name} ran before hardlink rejection")

        return fail

    monkeypatch.setattr(finalizer, "read_pinned_sources", fail_read)
    monkeypatch.setattr(Path, "mkdir", fail_mutation("mkdir"))
    monkeypatch.setattr(finalizer.os, "chmod", fail_mutation("chmod"))

    with pytest.raises(ValueError, match="hardlinks"):
        finalizer.prepare_finalization(args)

    assert calls == {key: 0 for key in calls}
    assert _digest(shared_source.read_bytes()) == original_sha
    assert linked_output.stat().st_ino == shared_source.stat().st_ino
    assert [(path, path.stat().st_mode & 0o777) for path, _ in parent_modes] == parent_modes
    linked_output.unlink()
    shared_source.unlink()


def test_source_symlink_parent_blocks_before_read_parse_and_writes(tmp_path: Path, monkeypatch) -> None:
    paths, approved = _write_source_set(tmp_path)
    monkeypatch.setattr(finalizer, "APPROVED_SOURCE_SHA256", approved)
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    (real_parent / "source.json").write_text("{}", encoding="utf-8")
    link_parent = tmp_path / "linked-parent"
    link_parent.symlink_to(real_parent, target_is_directory=True)
    paths["original_ledger"] = link_parent / "source.json"
    output = _private_output(monkeypatch, tmp_path)
    args = SimpleNamespace(
        source_paths=paths,
        output_dir=output,
        campaign_state=output / "campaign.json",
        plan_path=output / "finalization_plan.json",
        derived_report=output / "sol-low-recovered-case.json",
    )
    calls = {"read": 0, "parse": 0, "mkdir": 0, "chmod": 0}
    real_mkdir = Path.mkdir
    real_chmod = finalizer.os.chmod

    def fail_read(*a, **k):
        calls["read"] += 1
        raise AssertionError("source read before symlink parent rejection")

    def count_parse(*a, **k):
        calls["parse"] += 1
        raise AssertionError("parse before symlink parent rejection")

    def count_mkdir(self, *a, **k):
        calls["mkdir"] += 1
        return real_mkdir(self, *a, **k)

    def count_chmod(path, mode):
        calls["chmod"] += 1
        return real_chmod(path, mode)

    monkeypatch.setattr(finalizer, "read_pinned_sources", fail_read)
    monkeypatch.setattr(source_validation, "parse_pinned_object", count_parse)
    monkeypatch.setattr(Path, "mkdir", count_mkdir)
    monkeypatch.setattr(finalizer.os, "chmod", count_chmod)

    with pytest.raises(ValueError, match="symlink"):
        finalizer.prepare_finalization(args)

    assert calls == {key: 0 for key in calls}


def test_hardlinked_source_rejected_before_source_read(tmp_path: Path, monkeypatch) -> None:
    paths, approved = _write_source_set(tmp_path)
    monkeypatch.setattr(finalizer, "APPROVED_SOURCE_SHA256", approved)
    linked_copy = tmp_path / "linked-copy.json"
    linked_copy.hardlink_to(paths["original_ledger"])
    source_sha = _digest(paths["original_ledger"].read_bytes())
    output = _private_output(monkeypatch, tmp_path)
    args = SimpleNamespace(
        source_paths=paths,
        output_dir=output,
        campaign_state=output / "campaign.json",
        plan_path=output / "finalization_plan.json",
        derived_report=output / "sol-low-recovered-case.json",
    )
    read_calls = []
    monkeypatch.setattr(finalizer, "read_pinned_sources", lambda *a, **k: read_calls.append(True))

    with pytest.raises(ValueError, match="fuente debe ser archivo regular sin hardlinks"):
        finalizer.prepare_finalization(args)

    assert read_calls == []
    assert _digest(paths["original_ledger"].read_bytes()) == source_sha


def test_final_case_partition_excludes_recovered_case_and_avoids_original_failure_replay() -> None:
    partition = final_case_partition(STAGE2_EXPECTED_CASE_IDS)

    assert len(partition["replacement_case_ids"]) == 13
    assert len(partition["never_attempted_case_ids"]) == 1
    assert len(partition["sol_low_case_ids"]) == 14
    assert len(partition["sol_medium_case_ids"]) == 15
    assert partition["recovered_case_id_skipped"] == "es_am_market_share"
    assert "es_am_market_share" not in partition["sol_low_case_ids"]
    assert partition["never_attempted_case_ids"] == ["es_viva_missing_company_passengers"]
    assert partition["replacement_case_ids"] == list(STAGE2_EXPECTED_CASE_IDS[:13])


def test_recovered_case_requires_terminal_get_proof_and_no_automatic_grade() -> None:
    answer = "Synthetic recovered output for unit test."
    answer_sha = _digest(answer.encode())
    recovery = {
        "request_controls": {"side_effecting_requests": 0},
        "source": {
            "candidate": "gpt-6.1-sol@low",
            "case_id": "es_am_market_share",
            "run_id": "run",
            "plan_sha256": "a" * 64,
            "progress_sha256": "b" * 64,
            "continuation_run_identity_hash": "c" * 64,
        },
        "provider": {
            "turn_status": "completed",
            "session_status": "idle",
            "session_idle": True,
            "turn_identity_verified": True,
        },
        "usage": {"usage_complete": True, "input_tokens": 137951, "output_tokens": 499},
        "answer": {
            "present": True,
            "selected_assistant_message_count": 1,
            "text": answer,
            "sha256": answer_sha,
        },
        "evaluation": {
            "transport_recovered": True,
            "latency_valid": False,
            "auto_graded": False,
            "auto_approved": False,
            "tool_calls_inferred": False,
        },
    }
    recovered, input_tokens, output_tokens = validate_terminal_recovery(
        recovery, expected_source=recovery["source"], expected_case_id="es_am_market_share"
    )
    identity = {
        "candidate": "gpt-6.1-sol@low",
        "model": "gpt-6.1-sol",
        "reasoning_effort": "low",
        "run_id": "run",
    }
    report = derived_recovery_report(
        run_identity=identity,
        campaign_identity_hash="e" * 64,
        answer=recovered,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        recovery_sha256="d" * 64,
        progress_sha256="b" * 64,
        continuation_plan_sha256="a" * 64,
        answer_sha256=answer_sha,
        recovery_case_id="es_am_market_share",
    )

    row = report["models"][0]["cases"][0]
    assert report["case_count"] == 1
    assert row["response"] == answer
    assert row["latency_seconds"] is None
    assert row["tool_calls"] is None
    assert row["quality"]["evaluated"] is False
    assert row["quality"]["passed"] is None
    assert row["recovery_metadata"]["tool_calls_inferred"] is False


def test_recovered_sol_cost_uses_conservative_pinned_input_tariff() -> None:
    catalog = json.loads((finalizer.ROOT / "config/chat/models.json").read_text())
    recovery_cost = conservative_usage_cost(137_951, 499, catalog)
    total = 0.05460125 + 0.141395625 + 1.72828 + recovery_cost

    assert recovery_cost == pytest.approx(0.3498675)
    assert total == pytest.approx(2.274144375)
    assert 8.0 - total == pytest.approx(5.725855625)
