from __future__ import annotations

import pytest

from src.conversational_analytics import evaluation, evaluation_live


@pytest.mark.parametrize(
    "args",
    [
        ["--budget-usd", "nan"],
        ["--budget-usd", "inf"],
    ],
)
def test_live_cli_rejects_nonfinite_budget_before_runtime(monkeypatch, args) -> None:
    monkeypatch.setattr(
        evaluation_live, "_live_provider_run", lambda **kwargs: pytest.fail("runtime invoked")
    )
    with pytest.raises(SystemExit) as error:
        evaluation.main(
            [
                "--run",
                "--opt-in",
                *args,
                "--models",
                "gpt-6-luna",
                "--model-price",
                "gpt-6-luna=0.1:0.5",
                "--probe-only",
            ]
        )
    assert error.value.code == 2


@pytest.mark.parametrize("price", ["nan:0.5", "0.1:inf", "0:0.5"])
def test_live_cli_rejects_nonfinite_or_nonpositive_prices_before_runtime(monkeypatch, price) -> None:
    monkeypatch.setattr(
        evaluation_live, "_live_provider_run", lambda **kwargs: pytest.fail("runtime invoked")
    )
    with pytest.raises(SystemExit) as error:
        evaluation.main(
            [
                "--run",
                "--opt-in",
                "--budget-usd",
                "1",
                "--models",
                "gpt-6-luna",
                "--model-price",
                f"gpt-6-luna={price}",
                "--probe-only",
            ]
        )
    assert error.value.code == 2
