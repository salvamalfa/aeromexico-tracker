"""Research error rates retain flight-volume weights and signed direction."""

import pandas as pd
import pytest

from scripts.research.frozen_seed_temporal_validation import metrics


def test_error_diagnostic_weights_departures_and_does_not_average_route_percentages():
    result = metrics(pd.DataFrame({"truth": [100, 1], "estimate": [110, 0]}))
    assert result["wape"] == pytest.approx(11 / 101)
    assert result["signed_bias"] == pytest.approx(9 / 101)
    assert result["observed_departures"] == 101


def test_recorded_zero_has_error_but_an_unscored_empty_denominator_is_not_accuracy():
    result = metrics(pd.DataFrame({"truth": [0], "estimate": [5]}))
    assert result["wape"] is None
    assert result["signed_bias"] is None
    assert result["p90_absolute_percentage_error"] is None
