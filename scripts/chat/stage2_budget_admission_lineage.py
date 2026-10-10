"""Strict offline checks for the pilot-only stage-2 budget admission policy."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

from scripts.chat.stage2_finalization import conservative_usage_cost

ROOT = Path(__file__).resolve().parents[2]
FORECAST_PATH = ROOT / "docs/chat/revision-fase-2/F2.9-etapa-2-presupuesto.json"
FORECAST_SHA256 = "0f94efcae33177cde6e1cfc71415a3caa724757b0f053cca82b1e63d18f27803"
TARIFF_PATH = ROOT / "config/chat/models.json"
TARIFF_SHA256 = "9744c985f051c898a8af6e8d3c8766c6885e77d8a13d55b72e30427b15468d4c"
SAMPLE_SOURCES = (
    "original_report",
    "closed_report_luna_medium",
    "closed_report_luna_max",
    "terminal_recovery",
)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _round_up_ratio(total: int, count: int) -> int:
    return (total + count - 1) // count


def _samples(sources: dict[str, dict[str, Any]], source_hashes: dict[str, str], error: type[ValueError]):
    tokens: list[tuple[int, int]] = []
    failed = 0
    candidate_counts: dict[str, int] = {}
    expected_candidates = {
        "original_report": "gpt-6-luna@medium",
        "closed_report_luna_medium": "gpt-6-luna@medium",
        "closed_report_luna_max": "gpt-6-luna@max",
    }
    for name in SAMPLE_SOURCES[:3]:
        report = sources.get(name, {})
        models = report.get("models", [])
        if (
            not isinstance(models, list)
            or len(models) != 1
            or models[0].get("candidate") != expected_candidates[name]
        ):
            raise error("La muestra presupuestal no conserva el reporte de un solo modelo")
        rows = models[0].get("cases", [])
        for row in rows:
            if row.get("model_turn_completed") is not True:
                failed += 1
                continue
            if row.get("usage_complete") is not True:
                raise error("Una respuesta completada de la muestra no tiene uso completo")
            values = (row.get("input_tokens"), row.get("output_tokens"))
            if any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values):
                raise error("Una respuesta de la muestra carece de tokens enteros válidos")
            tokens.append((values[0], values[1]))
            candidate = expected_candidates[name]
            candidate_counts[candidate] = candidate_counts.get(candidate, 0) + 1
    recovery = sources.get("recovery", {})
    usage = recovery.get("usage", {})
    recovered = (usage.get("input_tokens"), usage.get("output_tokens"))
    if (
        recovery.get("capture_kind") != "terminal_transport_recovery"
        or recovery.get("source", {}).get("candidate") != "gpt-6.1-sol@low"
        or recovery.get("source", {}).get("case_id") != "es_am_market_share"
        or usage.get("usage_complete") is not True
        or any(isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in recovered)
        or len(tokens) != 29
        or failed != 1
    ):
        raise error("La muestra requiere 29 respuestas reportadas y la recuperación terminal exacta")
    tokens.append((recovered[0], recovered[1]))
    candidate_counts["gpt-6.1-sol@low"] = 1
    if candidate_counts != {
        "gpt-6-luna@medium": 14,
        "gpt-6-luna@max": 15,
        "gpt-6.1-sol@low": 1,
    }:
        raise error(
            "La mezcla histórica requiere 14 Luna medium, 15 max y 1 Sol low"
        )
    source_sha = {
        "terminal_recovery" if name == "terminal_recovery" else name:
        source_hashes["recovery" if name == "terminal_recovery" else name]
        for name in SAMPLE_SOURCES
    }
    return tokens, source_sha, candidate_counts


def _forecast(remaining: float, carry_total: float, error: type[ValueError]) -> dict[str, Any]:
    try:
        raw = FORECAST_PATH.read_bytes()
        forecast = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise error("No se pudo validar el presupuesto stage-2 aprobado") from exc
    if _sha256(raw) != FORECAST_SHA256:
        raise error("El presupuesto stage-2 no coincide con el pin aprobado")
    estimates = forecast.get("candidate_estimates_usd", {})
    low, medium = estimates.get("gpt-6.1-sol@low"), estimates.get("gpt-6.1-sol@medium")
    if not isinstance(low, list) or len(low) != 2 or not isinstance(medium, list) or len(medium) != 2:
        raise error("El estimado aprobado no conserva los dos rangos Sol")
    lower = low[0] * (14 / 15) + medium[0]
    upper = low[1] * (14 / 15) + medium[1]
    if upper > remaining or carry_total + upper > 8.0:
        raise error("El rango alto aprobado supera el saldo de reserva disponible")
    return {
        "source_path": str(FORECAST_PATH.relative_to(ROOT)),
        "source_sha256": FORECAST_SHA256,
        "low_case_count": 14,
        "medium_case_count": 15,
        "estimated_cost_range_usd": [lower, upper],
        "remaining_after_upper_estimate_usd": remaining - upper,
        "reserve_after_carry_and_upper_estimate_usd": 8.0 - carry_total - upper,
        "basis": "approved stage-2 estimate scaled to 14 Low plus 15 Medium calls",
        "budget_guaranteed": False,
    }


def validate_budget_admission_policy(
    plan: dict[str, Any],
    sources: dict[str, dict[str, Any]],
    source_hashes: dict[str, str],
    final_identity: dict[str, Any],
    final_runs: list[dict[str, Any]],
    *,
    digest: Any,
    error: type[ValueError],
) -> dict[str, Any]:
    """Recompute the admission estimate from pinned pilot usage and bind every identity."""
    billing = plan.get("billing_reconciliation", {})
    final = plan.get("finalization", {})
    reservation = billing.get("admission_reservation")
    if not isinstance(reservation, dict):
        raise error("El plan no conserva la reserva empírica de admisión")
    try:
        tariff_raw = TARIFF_PATH.read_bytes()
        tariff = json.loads(tariff_raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise error("No se pudo validar el catálogo de tarifas fijado") from exc
    if _sha256(tariff_raw) != TARIFF_SHA256:
        raise error("El catálogo de tarifas no coincide con el pin aprobado")

    tokens, sample_sha, candidate_counts = _samples(sources, source_hashes, error)
    sample_count = len(tokens)
    input_total = sum(row[0] for row in tokens)
    output_total = sum(row[1] for row in tokens)
    mean_input = _round_up_ratio(input_total, sample_count)
    mean_output = _round_up_ratio(output_total, sample_count)
    margin = 0.35
    reserved_input = math.ceil(mean_input * (1 + margin))
    reserved_output = math.ceil(mean_output * (1 + margin))
    per_case = conservative_usage_cost(reserved_input, reserved_output, tariff)
    rates = tariff["models"]["gpt-6.1-sol"]
    unit_prices = {
        "input_normal": float(rates["input_usd_per_million"]),
        "input_cache_write": float(rates["cache_write_usd_per_million"]),
        "output": float(rates["output_usd_per_million"]),
    }
    long_context = {
        "long_context_threshold_input_tokens": int(rates["long_context_threshold_input_tokens"]),
        "long_context_input_multiplier": float(rates["long_context_input_multiplier"]),
        "long_context_output_multiplier": float(rates["long_context_output_multiplier"]),
    }
    planned_total = per_case * 29
    remaining = billing.get("remaining_budget_usd")
    carry_total = billing.get("carry_total_estimate_usd")
    if (
        isinstance(remaining, bool)
        or not isinstance(remaining, (int, float))
        or isinstance(carry_total, bool)
        or not isinstance(carry_total, (int, float))
        or not math.isfinite(remaining)
        or not math.isfinite(carry_total)
        or remaining < 0
        or carry_total < 0
    ):
        raise error("La reserva no conserva saldo y gasto acumulado finitos")
    approved = _forecast(float(remaining), float(carry_total), error)
    expected_fields = {
        "basis": "f2_9_empirical_pilot_estimate_not_hard_cap",
        "input_tokens_per_turn": reserved_input,
        "output_tokens_per_turn": reserved_output,
        "historical_sample_count": sample_count,
        "historical_candidate_counts": candidate_counts,
        "historical_input_tokens": input_total,
        "historical_output_tokens": output_total,
        "mean_input_tokens_rounded_up": mean_input,
        "mean_output_tokens_rounded_up": mean_output,
        "budget_guaranteed": False,
        "safety_margin_fraction": margin,
        "per_case_estimated_reservation_usd": per_case,
        "planned_request_count": 29,
        "planned_batch_estimated_reservation_usd": planned_total,
        "unit_prices_usd_per_million": unit_prices,
        **long_context,
        "price_basis": (
            "separate Sol input at cache-write rate and output at catalog rate; no cache credit"
        ),
        "sample_source_sha256": sample_sha,
        "tariff_catalog_sha256": digest(tariff),
        "approved_budget_forecast_sha256": FORECAST_SHA256,
    }
    if (
        _sha256(tariff_raw) != TARIFF_SHA256
        or any(reservation.get(key) != value for key, value in expected_fields.items())
        or billing.get("budget_admission_policy_sha256") != digest(reservation)
        or planned_total > remaining
        or carry_total + planned_total > 8.0
    ):
        raise error("La reserva empírica no coincide con tokens, tarifas y fuentes aprobados")

    policy = {
        "basis": reservation["basis"],
        "sha256": digest(reservation),
        "historical_sample_count": sample_count,
        "historical_candidate_counts": candidate_counts,
        "historical_input_tokens": input_total,
        "historical_output_tokens": output_total,
        "safety_margin_fraction": margin,
        "input_tokens_per_turn": reserved_input,
        "output_tokens_per_turn": reserved_output,
        "planned_request_count": 29,
        "planned_batch_estimated_reservation_usd": planned_total,
        "unit_prices_usd_per_million": unit_prices,
        **long_context,
        "price_basis": expected_fields["price_basis"],
        "source_sha256": sample_sha,
        "tariff_catalog_sha256": expected_fields["tariff_catalog_sha256"],
        "approved_budget_forecast_sha256": FORECAST_SHA256,
        "approved_forecast_range_usd": approved["estimated_cost_range_usd"],
        "budget_guaranteed": False,
    }
    if (
        final.get("budget_admission_policy") != policy
        or final_identity.get("reservation_assumption_override") != reservation
    ):
        raise error("La campaña final no conserva la política y su reserva completa aprobadas")
    if not math.isclose(
        reservation.get("planned_batch_estimated_reservation_usd", -1),
        planned_total,
        rel_tol=0,
        abs_tol=1e-12,
    ):
        raise error("La reserva por corrida no coincide con el costo de 29 solicitudes")
    for run in final_runs:
        identity = run.get("identity", {})
        if identity.get("budget_admission_policy") != policy:
            raise error("Una corrida final no conserva la política de admisión validada")
    if billing.get("approved_estimate_forecast") != approved:
        raise error("El forecast de admisión no coincide con el archivo presupuestal aprobado")
    return policy
