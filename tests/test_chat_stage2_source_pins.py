from __future__ import annotations

import hashlib
import json
from argparse import Namespace
from pathlib import Path

import pytest

from scripts.chat import continue_stage2_campaign as continuation_cli


def _source_bytes() -> dict[str, bytes]:
    ledger = json.dumps({"status": "stopped_unknown_spend", "known_spend_usd": 0.05460125}).encode()
    report = json.dumps({"cases": [{"id": "case-1", "answer": "saved answer"}]}).encode()
    ledger_sha = hashlib.sha256(ledger).hexdigest()
    report_sha = hashlib.sha256(report).hexdigest()
    evidence = json.dumps({"source_identity": {"ledger_sha256": ledger_sha, "report_sha256": report_sha}}).encode()
    return {"source ledger": ledger, "source report": report, "owner evidence": evidence}


def _write_sources(directory: Path, data: dict[str, bytes]) -> dict[str, Path]:
    paths = {}
    for label, raw in data.items():
        path = directory / f"{label.replace(' ', '-')}.json"
        path.write_bytes(raw)
        paths[label] = path
    return paths


def _argv(paths: dict[str, Path], tmp_path: Path) -> list[str]:
    return [
        "--source-ledger", str(paths["source ledger"]),
        "--source-report", str(paths["source report"]),
        "--owner-evidence", str(paths["owner evidence"]),
        "--output-dir", str(tmp_path / "new-output"),
        "--campaign-state", str(tmp_path / "new-output/campaign.json"),
        "--plan-path", str(tmp_path / "continuation-plan.json"),
    ]


def _pin_test_bytes(monkeypatch: pytest.MonkeyPatch, original: dict[str, bytes]) -> None:
    monkeypatch.setattr(
        continuation_cli,
        "APPROVED_PRIVATE_SOURCE_SHA256",
        {label: hashlib.sha256(raw).hexdigest() for label, raw in original.items()},
    )


@pytest.mark.parametrize("changed_source", ["source report", "source ledger", "owner evidence"])
def test_cli_rejects_rehashed_user_source_before_parse_prepare_or_plan_write(
    changed_source: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _source_bytes()
    changed = dict(original)
    if changed_source == "source report":
        report = json.loads(changed[changed_source])
        report["cases"][0]["answer"] = "tampered saved answer"
        # Keep the same case IDs and let the fabricated owner evidence self-reference the new hash.
        changed[changed_source] = json.dumps(report).encode()
        evidence = json.loads(changed["owner evidence"])
        evidence["source_identity"]["report_sha256"] = hashlib.sha256(changed[changed_source]).hexdigest()
        changed["owner evidence"] = json.dumps(evidence).encode()
    elif changed_source == "source ledger":
        ledger = json.loads(changed[changed_source])
        ledger["known_spend_usd"] = 0
        changed[changed_source] = json.dumps(ledger).encode()
        evidence = json.loads(changed["owner evidence"])
        evidence["source_identity"]["ledger_sha256"] = hashlib.sha256(changed[changed_source]).hexdigest()
        changed["owner evidence"] = json.dumps(evidence).encode()
    else:
        evidence = json.loads(changed[changed_source])
        evidence["owner_confirmed"] = True
        changed[changed_source] = json.dumps(evidence).encode()

    _pin_test_bytes(monkeypatch, original)
    paths = _write_sources(tmp_path, changed)
    monkeypatch.setattr(
        continuation_cli,
        "_parse_pinned_private_json",
        lambda *args, **kwargs: pytest.fail("Un pin fallido no debe parsear ninguna fuente"),
    )
    monkeypatch.setattr(
        continuation_cli,
        "prepare",
        lambda *args, **kwargs: pytest.fail("Un pin fallido no debe preparar la campaña"),
    )
    plan_path = tmp_path / "continuation-plan.json"

    with pytest.raises(SystemExit):
        continuation_cli.main(_argv(paths, tmp_path))

    assert not plan_path.exists()
    assert not (tmp_path / "new-output").exists()


def test_cli_accepts_exact_external_copies_and_reads_each_source_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = _source_bytes()
    _pin_test_bytes(monkeypatch, original)
    paths = _write_sources(tmp_path, original)
    read_counts = {path: 0 for path in paths.values()}
    real_read_bytes = Path.read_bytes

    def tracked_read_bytes(path: Path) -> bytes:
        if path in read_counts:
            read_counts[path] += 1
        return real_read_bytes(path)

    class BasePreparationReached(Exception):
        pass

    monkeypatch.setattr(Path, "read_bytes", tracked_read_bytes)
    monkeypatch.setattr(continuation_cli, "_require_private_destination", lambda path, **_: path)
    monkeypatch.setattr(continuation_cli, "_validate_destination_relationships", lambda *args: None)
    monkeypatch.setattr(
        continuation_cli,
        "prepare",
        lambda *args, **kwargs: (_ for _ in ()).throw(BasePreparationReached()),
    )

    with pytest.raises(BasePreparationReached):
        continuation_cli.main(_argv(paths, tmp_path))

    assert set(read_counts.values()) == {1}
    assert not (tmp_path / "continuation-plan.json").exists()


def test_source_pin_constants_are_the_approved_private_artifacts() -> None:
    assert continuation_cli.APPROVED_PRIVATE_SOURCE_SHA256 == {
        "source ledger": "fb6a661a8635b8e139951a541ee549ba7f3b35dfde611ebfc73e31eb5fad5140",
        "source report": "0305ac40cc52e72371a1ed3b3334624c6261ed4be99adcfd9518727265913002",
        "owner evidence": "a042789788649f22e9bf213d14a274fc9e117fcd825b8ce6cfd0221007c4446c",
    }
