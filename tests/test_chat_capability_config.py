from __future__ import annotations

import pytest

from src.conversational_analytics.config import ChatConfig


def test_new_capabilities_stay_disabled_for_approved_r1_prompt() -> None:
    config = ChatConfig()
    assert not config.enable_route_tools
    assert not config.enable_business_metric_tools
    assert not config.enable_evidence_tools


@pytest.mark.parametrize(
    "capability",
    ("enable_route_tools", "enable_business_metric_tools", "enable_evidence_tools"),
)
def test_r1_prompt_rejects_incompatible_capability_flags(capability: str) -> None:
    with pytest.raises(ValueError, match="exact approved prompt"):
        ChatConfig(**{capability: True})
