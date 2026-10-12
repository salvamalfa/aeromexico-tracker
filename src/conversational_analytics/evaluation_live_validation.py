"""Small request guards shared by live-evaluation entry points."""

from __future__ import annotations

import math


def validate_live_request(
    budget_usd: float, models: list[str], prices: dict[str, tuple[float, float]]
) -> None:
    if not math.isfinite(budget_usd) or budget_usd <= 0:
        raise ValueError("el presupuesto operativo por corrida debe ser finito y positivo")
    if len(models) not in (1, 2, 3, 4):
        raise ValueError("se permite una sonda o comparación de 2–4 candidatos modelo@esfuerzo")
    if set(prices) != set(models) or any(
        not math.isfinite(amount) or amount <= 0 for pair in prices.values() for amount in pair
    ):
        raise ValueError("cada candidato requiere precios finitos y positivos de entrada/salida")
