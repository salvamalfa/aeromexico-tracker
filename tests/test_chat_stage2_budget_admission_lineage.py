"""Hermetic checks for the sample-derived stage-2 admission lineage."""

from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/chat"))
import stage2_budget_admission_lineage as admission  # noqa: E402


def _digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def _valid_inputs():
    tokens = [(47_785, 1_570) for _ in range(29)]
    tokens[0] = (47_807, 1_587)
    rows = [
        {"model_turn_completed": True, "usage_complete": True, "input_tokens": i, "output_tokens": o}
        for i, o in tokens
    ]
    original = rows[:8] + [{"model_turn_completed": False, "usage_complete": False}]
    reports = {
        "original_report": {"models": [{"candidate": "gpt-6-luna@medium", "cases": original}]},
        "closed_report_luna_medium": {
            "models": [{"candidate": "gpt-6-luna@medium", "cases": rows[8:14]}]
        },
        "closed_report_luna_max": {"models": [{"candidate": "gpt-6-luna@max", "cases": rows[14:]}]},
        "recovery": {
            "capture_kind": "terminal_transport_recovery",
            "source": {"candidate": "gpt-6.1-sol@low", "case_id": "es_am_market_share"},
            "usage": {"usage_complete": True, "input_tokens": 137_951, "output_tokens": 499},
        },
    }
    sample_sha = {name: hashlib.sha256(name.encode()).hexdigest() for name in admission.SAMPLE_SOURCES}
    hashes = {**sample_sha, "recovery": sample_sha["terminal_recovery"]}
    tariff = json.loads(admission.TARIFF_PATH.read_text(encoding="utf-8"))
    all_tokens = [*tokens, (137_951, 499)]
    input_total = sum(item[0] for item in all_tokens)
    output_total = sum(item[1] for item in all_tokens)
    mean_input = (input_total + 29) // 30
    mean_output = (output_total + 29) // 30
    reserved_input = (mean_input * 135 + 99) // 100
    reserved_output = (mean_output * 135 + 99) // 100
    per_case = admission.conservative_usage_cost(reserved_input, reserved_output, tariff)
    rates = tariff["models"]["gpt-6.1-sol"]
    candidate_counts = {
        "gpt-6-luna@medium": 14,
        "gpt-6-luna@max": 15,
        "gpt-6.1-sol@low": 1,
    }
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
    remaining, carry_total = 5.725, 2.275
    approved = admission._forecast(remaining, carry_total, ValueError)
    reservation = {
        "basis": "f2_9_empirical_pilot_estimate_not_hard_cap",
        "input_tokens_per_turn": reserved_input,
        "output_tokens_per_turn": reserved_output,
        "historical_sample_count": 30,
        "historical_candidate_counts": candidate_counts,
        "historical_input_tokens": input_total,
        "historical_output_tokens": output_total,
        "mean_input_tokens_rounded_up": mean_input,
        "mean_output_tokens_rounded_up": mean_output,
        "budget_guaranteed": False,
        "safety_margin_fraction": 0.35,
        "per_case_estimated_reservation_usd": per_case,
        "planned_request_count": 29,
        "planned_batch_estimated_reservation_usd": per_case * 29,
        "note": "planning estimate, not a hard cap",
        "sample_source_sha256": sample_sha,
        "unit_prices_usd_per_million": unit_prices,
        **long_context,
        "price_basis": "separate Sol input at cache-write rate and output at catalog rate; no cache credit",
        "tariff_catalog_sha256": _digest(tariff),
        "approved_budget_forecast_sha256": admission.FORECAST_SHA256,
    }
    policy = {
        "basis": reservation["basis"],
        "sha256": _digest(reservation),
        "historical_sample_count": 30,
        "historical_candidate_counts": candidate_counts,
        "historical_input_tokens": input_total,
        "historical_output_tokens": output_total,
        "safety_margin_fraction": 0.35,
        "input_tokens_per_turn": reserved_input,
        "output_tokens_per_turn": reserved_output,
        "planned_request_count": 29,
        "planned_batch_estimated_reservation_usd": per_case * 29,
        "unit_prices_usd_per_million": unit_prices,
        **long_context,
        "price_basis": "separate Sol input at cache-write rate and output at catalog rate; no cache credit",
        "source_sha256": sample_sha,
        "tariff_catalog_sha256": _digest(tariff),
        "approved_budget_forecast_sha256": admission.FORECAST_SHA256,
        "approved_forecast_range_usd": approved["estimated_cost_range_usd"],
        "budget_guaranteed": False,
    }
    final_runs = [
        {"identity": {"budget_admission_policy": policy}},
        {"identity": {"budget_admission_policy": policy}},
    ]
    final_identity = {"reservation_assumption_override": reservation}
    plan = {
        "billing_reconciliation": {
            "admission_reservation": reservation,
            "budget_admission_policy_sha256": _digest(reservation),
            "approved_estimate_forecast": approved,
            "remaining_budget_usd": remaining,
            "carry_total_estimate_usd": carry_total,
        },
        "finalization": {"budget_admission_policy": policy},
    }
    return plan, reports, hashes, final_identity, final_runs, policy


class BudgetAdmissionLineageTests(unittest.TestCase):
    def test_recomputes_pinned_30_sample_policy_and_accepts_bound_identities(self):
        plan, sources, hashes, campaign, runs, expected = _valid_inputs()
        self.assertEqual(
            admission.validate_budget_admission_policy(
                plan, sources, hashes, campaign, runs, digest=_digest, error=ValueError
            ),
            expected,
        )

    def test_rejects_policy_mismatch_in_finalization_and_native_run_identity(self):
        for target in ("plan", "run", "campaign"):
            with self.subTest(target=target):
                plan, sources, hashes, campaign, runs, _ = _valid_inputs()
                if target == "plan":
                    plan["finalization"]["budget_admission_policy"]["input_tokens_per_turn"] += 1
                elif target == "run":
                    runs[0]["identity"]["budget_admission_policy"]["sha256"] = "0" * 64
                else:
                    campaign["reservation_assumption_override"]["input_tokens_per_turn"] += 1
                with self.assertRaises(ValueError):
                    admission.validate_budget_admission_policy(
                        plan, sources, hashes, campaign, runs, digest=_digest, error=ValueError
                    )

    def test_rejects_unpinned_recovery_capture_kind(self):
        plan, sources, hashes, campaign, runs, _ = _valid_inputs()
        sources["recovery"]["capture_kind"] = "GET_completed_turn_recovery"
        with self.assertRaisesRegex(ValueError, "recuperación terminal exacta"):
            admission.validate_budget_admission_policy(
                plan, sources, hashes, campaign, runs, digest=_digest, error=ValueError
            )


if __name__ == "__main__":
    unittest.main()
