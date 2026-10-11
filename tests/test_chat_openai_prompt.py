from __future__ import annotations

import pytest

from src.conversational_analytics.providers._openai_prompt import (
    APPROVED_BASE_PROMPT_SHA256,
    APPROVED_EFFECTIVE_PROMPT_SHA256,
    PERIOD_SELECTION_POLICY,
    SYSTEM_INSTRUCTIONS,
    load_system_instructions,
    prompt_sha256,
)


def test_runtime_prompt_matches_approved_stage_two_sol_low_prompt():
    assert prompt_sha256(SYSTEM_INSTRUCTIONS) == APPROVED_EFFECTIVE_PROMPT_SHA256
    assert APPROVED_BASE_PROMPT_SHA256 == "33b8f7a0900869812d98bba57daa2ce3ea2f6b5c02a86a7eb3b8e830c7f7694b"
    assert APPROVED_EFFECTIVE_PROMPT_SHA256 == "439d24fd58a7b3c6c721e15a390824c1b477f52b2b568881dd68bd3655db22a5"
    assert SYSTEM_INSTRUCTIONS.count(PERIOD_SELECTION_POLICY) == 1
    assert "get_dashboard_context" in SYSTEM_INSTRUCTIONS
    assert "No prometas buscar en reportes o noticias" in SYSTEM_INSTRUCTIONS


def test_prompt_source_drift_fails_closed(tmp_path):
    altered = tmp_path / "system_prompt.txt"
    altered.write_text("prompt alterado", encoding="utf-8")
    with pytest.raises(RuntimeError, match="SHA-256 aprobado"):
        load_system_instructions(altered)
