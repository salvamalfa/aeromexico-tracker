"""OpenAI client configuration safety tests."""

from types import SimpleNamespace

import pytest

from src.conversational_analytics.providers._openai_helpers import OpenAIProviderError
from src.conversational_analytics.providers.openai import OpenAIProvider


def test_openai_client_requires_existing_key_without_printing_or_probing(monkeypatch, capsys):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(OpenAIProviderError, match="no está configurada"):
        OpenAIProvider(SimpleNamespace(openai_enabled=True, model="explicit-model"))

    assert capsys.readouterr().out == ""
