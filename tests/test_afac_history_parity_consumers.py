"""The composed consumer must propagate refusal instead of falling back to B."""

import pytest

from src.publish import afac_history_scope
from tests import _quarterly_story_parity as readings
from tests import _site_publication_parity as financial

PROFILE = "src.publish.afac_history_scope"


def test_composed_financial_consumer_rejects_failed_scope_without_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(financial, "verifier_for", lambda *args: PROFILE)
    monkeypatch.setattr(afac_history_scope, "verify_afac_history", lambda *args: ["C source refused"])
    with pytest.raises(AssertionError, match="C source refused"):
        financial.verify_current_publication(tmp_path, tmp_path, lambda *args: pytest.fail("fallback"))


def test_composed_reading_consumer_rejects_failed_scope_before_using_parent(tmp_path, monkeypatch):
    monkeypatch.setattr(readings, "verifier_for", lambda *args: PROFILE)
    monkeypatch.setattr(afac_history_scope, "verify_afac_history", lambda *args: ["C source refused"])
    monkeypatch.setattr(readings.scope, "verify_story", lambda *args: pytest.fail("parent fallback"))
    with pytest.raises(AssertionError, match="C source refused"):
        readings.publication(tmp_path, tmp_path)
