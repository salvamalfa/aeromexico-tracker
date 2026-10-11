from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from src.conversational_analytics.providers._openai_prompt import (
    APPROVED_EFFECTIVE_PROMPT_SHA256,
    SYSTEM_INSTRUCTIONS,
    effective_prompt_sha256,
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
