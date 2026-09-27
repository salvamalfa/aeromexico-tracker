"""CI guard for the literal registry contract in `validate_stage9`.

`dashboard.validate_stage9` only runs with local data, so a DAG change that
forgets to update its expected counts would only surface in a private
`just rebuild` (as it did after the route-extension generators were added).
"""

from collections import Counter

from src.pipeline.registry import PIPELINE_STEPS
from src.transform.validate_stage9 import (
    EXPECTED_REGISTRY_PHASE_COUNTS,
    EXPECTED_REGISTRY_STEPS,
)


def test_stage9_registry_contract_matches_the_registry() -> None:
    assert len(PIPELINE_STEPS) == EXPECTED_REGISTRY_STEPS
    assert dict(Counter(step.phase.value for step in PIPELINE_STEPS)) == EXPECTED_REGISTRY_PHASE_COUNTS
    assert PIPELINE_STEPS[-2].step_id == "dashboard.materialize_stage9"
    assert PIPELINE_STEPS[-1].step_id == "dashboard.validate_stage9"
