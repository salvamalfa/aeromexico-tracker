from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from src.conversational_analytics.providers._openai_prompt import (
    APPROVED_EFFECTIVE_PROMPT_SHA256,
    R2_PROMPT_SHA256,
    SYSTEM_INSTRUCTIONS,
    effective_prompt_sha256,
    load_active_system_instructions,
)


def test_r2_candidate_hash_is_exact_and_does_not_replace_active_r1() -> None:
    prompt_path = Path("config/chat/prompt_candidates/system_prompt_r2-proposed.txt")
    metadata_path = Path("config/chat/prompt_candidates/system_prompt_r2-proposed.json")
    schema_path = Path("contracts/chat/prompt-candidate.schema.json")
    prompt = prompt_path.read_text(encoding="utf-8").strip()
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    assert not list(Draft202012Validator(schema).iter_errors(metadata))
    assert hashlib.sha256(prompt.encode("utf-8")).hexdigest() == metadata["proposed_effective_prompt_sha256"]
    assert metadata["status"] == "proposed_not_approved_not_active"
    assert metadata["current_effective_prompt_sha256"] == APPROVED_EFFECTIVE_PROMPT_SHA256
    assert effective_prompt_sha256() == APPROVED_EFFECTIVE_PROMPT_SHA256
    assert SYSTEM_INSTRUCTIONS != prompt
    assert "{{<display_id>}}" in prompt
    assert "(1) dato medido" in prompt
    assert "(2) atribución de la empresa" in prompt
    assert "(3) contexto de noticias" in prompt


def _write_r2_receipt(path: Path) -> str:
    candidate_path = "config/chat/prompt_candidates/system_prompt_r2-proposed.txt"
    receipt = {
        "schema_version": 1,
        "status": "owner_approved",
        "version": "r2-proposed",
        "prompt_sha256": R2_PROMPT_SHA256,
        "prompt_path": candidate_path,
        "capabilities": [
            "route_queries",
            "business_metric_queries",
            "evidence_search",
            "same_turn_displays",
            "three_layer_causal_explanations",
        ],
        "decision_ref": "owner-decision-test-fixture",
        "owner": "salvamalfa",
        "approved_at": "2026-10-12T22:56:00Z",
    }
    schema = json.loads(
        Path("contracts/chat/prompt-approval-receipt.schema.json").read_text(encoding="utf-8")
    )
    assert not list(Draft202012Validator(schema).iter_errors(receipt))
    raw = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def test_r2_selector_defaults_to_r1_and_requires_receipt(monkeypatch) -> None:
    monkeypatch.delenv("CHAT_PROMPT_VERSION", raising=False)
    monkeypatch.delenv("CHAT_PROMPT_APPROVAL_RECEIPT_SHA256", raising=False)
    assert load_active_system_instructions() == SYSTEM_INSTRUCTIONS
    monkeypatch.setenv("CHAT_PROMPT_VERSION", "r2-proposed")
    import pytest

    with pytest.raises(RuntimeError, match="recibo de aprobación"):
        load_active_system_instructions()


def test_r2_selector_accepts_only_receipt_with_exact_prompt_and_metadata(monkeypatch, tmp_path: Path) -> None:
    import pytest

    from src.conversational_analytics.providers import _openai_prompt as prompt_module

    receipt_path = tmp_path / "approval.json"
    receipt_hash = _write_r2_receipt(receipt_path)
    monkeypatch.setenv("CHAT_PROMPT_VERSION", "r2-proposed")
    monkeypatch.setenv("CHAT_PROMPT_APPROVAL_RECEIPT_PATH", str(receipt_path))
    monkeypatch.setenv("CHAT_PROMPT_APPROVAL_RECEIPT_SHA256", receipt_hash)
    assert hashlib.sha256(load_active_system_instructions().encode()).hexdigest() == R2_PROMPT_SHA256

    monkeypatch.setenv("CHAT_PROMPT_APPROVAL_RECEIPT_SHA256", "0" * 64)
    with pytest.raises(RuntimeError, match="hash fijado"):
        load_active_system_instructions()

    monkeypatch.setenv("CHAT_PROMPT_APPROVAL_RECEIPT_SHA256", receipt_hash)
    original_metadata = prompt_module.R2_PROMPT_METADATA_PATH
    changed_metadata = json.loads(original_metadata.read_text(encoding="utf-8"))
    changed_metadata["capabilities"] = ["route_queries"]
    changed_path = tmp_path / "drifted-candidate.json"
    changed_path.write_text(json.dumps(changed_metadata), encoding="utf-8")
    monkeypatch.setattr(prompt_module, "R2_PROMPT_METADATA_PATH", changed_path)
    with pytest.raises(RuntimeError, match="no coincide"):
        load_active_system_instructions()


def test_persisted_owner_prompt_receipt_matches_immutable_decision(monkeypatch, tmp_path: Path) -> None:
    from src.conversational_analytics.providers import _openai_prompt as prompt_module

    canonical_path = Path("config/chat/prompt_approval.json")
    original_bytes = canonical_path.read_bytes()
    receipt = json.loads(original_bytes)
    schema = json.loads(Path("contracts/chat/prompt-approval-receipt.schema.json").read_text())
    assert not list(Draft202012Validator(schema).iter_errors(receipt))
    assert receipt["owner"] == "salvamalfa"
    assert receipt["decision_ref"] == "https://github.com/salvamalfa/aeromexico-tracker/blob/76407da561ac1ff799c012ce5390c01176b30772/docs/decisiones/20261012-chat-periodo-selector-cierre-fase2.md"
    assert receipt["approved_at"] == "2026-10-13T00:44:04Z"
    assert receipt["prompt_sha256"] == R2_PROMPT_SHA256
    assert json.loads(Path("config/chat/prompt_candidates/system_prompt_r2-proposed.json").read_text())["status"] == "proposed_not_approved_not_active"
    monkeypatch.setenv("CHAT_PROMPT_VERSION", "r2-proposed")
    monkeypatch.setenv("CHAT_PROMPT_APPROVAL_RECEIPT_PATH", str(canonical_path))
    monkeypatch.setenv("CHAT_PROMPT_APPROVAL_RECEIPT_SHA256", hashlib.sha256(original_bytes).hexdigest())
    assert hashlib.sha256(prompt_module.load_active_system_instructions().encode()).hexdigest() == R2_PROMPT_SHA256

    import pytest

    forged_path = tmp_path / "forged-prompt-approval.json"
    for field, forged_value in (("owner", "untrusted-contributor"), ("approved_at", "not-a-date")):
        forged = dict(receipt)
        forged[field] = forged_value
        forged_bytes = json.dumps(forged).encode("utf-8")
        forged_path.write_bytes(forged_bytes)
        monkeypatch.setenv("CHAT_PROMPT_APPROVAL_RECEIPT_PATH", str(forged_path))
        monkeypatch.setenv("CHAT_PROMPT_APPROVAL_RECEIPT_SHA256", hashlib.sha256(forged_bytes).hexdigest())
        with pytest.raises(RuntimeError, match="no coincide"):
            prompt_module.load_active_system_instructions()

    assert canonical_path.read_bytes() == original_bytes


def test_r2_selected_period_examples_do_not_request_an_already_resolved_period() -> None:
    from src.conversational_analytics.providers._openai_prompt import (
        PERIOD_SELECTION_POLICY, with_dashboard_period_policy,
    )

    prompt = Path("config/chat/prompt_candidates/system_prompt_r2-proposed.txt").read_text().strip()
    clarification = prompt.split('<ejemplo id="aclaracion_sin_cifra">', 1)[1].split('</ejemplo>', 1)[0]
    assert 'dashboard_context.period = "2026Q2"' in clarification
    assert "y para qué periodo" not in clarification
    assert "¿Te refieres a ‹definición A› o ‹definición B›?" in clarification
    direct = prompt.split('<ejemplo id="periodo_omitido_con_selector">', 1)[1].split('</ejemplo>', 1)[0]
    assert "Tras consultar las herramientas para 2026Q2" in direct
    assert "valor y unidad devueltos por la herramienta" in direct
    assert "No vuelvas a preguntar por el periodo que ya aporta el selector" in prompt
    assert "combustible → fuel" in prompt
    assert "Una búsqueda vacía no demuestra que el reporte no trate el tema" in prompt
    assert prompt.endswith(PERIOD_SELECTION_POLICY)
    assert with_dashboard_period_policy(prompt) == prompt
