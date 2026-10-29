"""Owner-authorized operational use of unchanged Aerocivil assumptions, not official confirmation.

Attach this policy only after the dedicated source replay. It never replaces
source availability, observations, period, native counts, hashes or lineage.
"""

from __future__ import annotations

import re

POLICY = "aerocivil_operational_assumptions_20261029_v1"
SCOPE = "one_AMX_SLI_query_month_literal_S_I_codes_Colombian_reporting_airports_not_global_network"
DESCRIPTION_SHA256 = "79bd5a4ae4e3abbfc363b3ee44b4ea26352af17484a9d195c8f1cbeafeeb1b4d"
DEFINITIONS_SHA256 = "dadf4e3b4f2e5b0fcba8d524c5dec684421f6f87ae071fd8985c9362d97bde9c"
PENDING = "official_service_code_legend_pending"
ASSUMPTIONS = {
    "flight_type_S": "selected_as_regular_for_operational_use_not_officially_confirmed",
    "traffic_I": "selected_as_international_for_operational_use_not_officially_confirmed",
    "operator_AMX_SLI": "source_derived_labels_used_provisionally_not_independent_AOC_or_codeshare_proof",
    "measure": "reported_airport_movements_not_passengers_seats_departures_or_load_factor",
    "coverage": "one_observed_month_Mexico_Colombia_not_full_quarter_or_global_network",
    "missing_operator": "absence_is_not_zero",
}


def hash_string(value) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def outputs_valid(values) -> bool:
    from src.source_updates.aerocivil import OUTPUTS

    return (
        isinstance(values, dict)
        and set(values) == set(OUTPUTS)
        and all(hash_string(value) for value in values.values())
    )


def measurements_valid(value) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "rows",
        "raw_rows",
        "source_counts",
        "movements",
        "operators_present",
    }:
        return False
    rows, raw = value["rows"], value["raw_rows"]
    operators = value["operators_present"]
    return (
        type(rows) is int
        and type(raw) is int
        and 1 <= rows <= raw <= 1000
        and isinstance(value["source_counts"], list)
        and all(type(count) is int for count in value["source_counts"])
        and value["source_counts"] == [raw, raw]
        and type(value["movements"]) is int
        and value["movements"] >= 0
        and isinstance(operators, list)
        and bool(operators)
        and all(isinstance(operator, str) for operator in operators)
        and operators == sorted(set(operators))
        and set(operators) <= {"AMX", "SLI"}
    )


def from_replay(result: dict, receipt_sha: str, acquisition_sha: str) -> dict | None:
    """Only the read-only adapter invokes this after all native checks pass."""
    metadata = result.get("metadata_review", {})
    if not isinstance(metadata, dict):
        return None
    measure = {
        "rows": result.get("accepted_rows"),
        "raw_rows": result.get("raw_rows"),
        "source_counts": result.get("source_counts"),
        "movements": result.get("reported_operations_under_selected_codes"),
        "operators_present": result.get("operators_present"),
    }
    if not (
        result.get("status") == "checks_passed"
        and result.get("scope") == SCOPE
        and result.get("service_code_mapping_verified") is False
        and result.get("agent_eligible") is False
        and result.get("missing_operator_is_not_zero") is True
        and result.get("interpretation_acceptance")
        == "pending_official_code_legend_and_entity_attribution_review"
        and result.get("commercial_designator_status")
        == "source_derived_from_callsign_not_proven_marketing_carrier"
        and result.get("operator_designator_status")
        == "source_derived_from_aircraft_registration_not_directly_captured"
        and metadata.get("dataset_id") == "jh8x-n6h6"
        and metadata.get("description_sha256") == DESCRIPTION_SHA256
        and metadata.get("field_definitions_sha256") == DEFINITIONS_SHA256
        and metadata.get("service_code_mapping_verified") is False
        and metadata.get("entity_attribution")
        == "source_derived_callsign_and_aircraft_registration_not_independently_verified"
        and metadata.get("code_legend_status") == "no_explicit_literal_mapping_in_reviewed_column_definitions"
        and re.fullmatch(r"\d{4}M(?:0[1-9]|1[0-2])", str(result.get("period")))
        and measurements_valid(measure)
        and outputs_valid(result.get("output_sha256"))
        and all(
            hash_string(value)
            for value in (
                receipt_sha,
                acquisition_sha,
                result.get("metadata_sha256"),
                result.get("reference_sha256"),
            )
        )
    ):
        return None
    return {
        "policy_id": POLICY,
        "status": "usable_with_assumptions_pending_official_confirmation",
        "official_confirmation": False,
        "assumptions": dict(ASSUMPTIONS),
        "scope": SCOPE,
        "native_period": result["period"],
        "measurements": measure,
        "accepted_receipt_sha256": receipt_sha,
        "acquisition_receipt_sha256": acquisition_sha,
        "output_sha256": result["output_sha256"],
        "metadata_sha256": result["metadata_sha256"],
        "reference_sha256": result["reference_sha256"],
        "description_sha256": DESCRIPTION_SHA256,
        "field_definitions_sha256": DEFINITIONS_SHA256,
        "official_response_followup": (
            "compare_official_response_then_version_affected_calculations_preserving_originals"
        ),
    }


def accepted(result: dict) -> bool:
    """Accept official evidence or this exact, physically bound provisional policy."""
    if result.get("status") != "checks_passed":
        return False
    conditions = result.get("source_conditions", [])
    if result.get("semantic_acceptance_verified") is True and PENDING not in conditions:
        return True
    proof = result.get("operational_acceptance")
    if not isinstance(proof, dict) or result.get("semantic_acceptance_verified") is not False:
        return False
    expected = {
        "policy_id",
        "status",
        "official_confirmation",
        "assumptions",
        "scope",
        "native_period",
        "measurements",
        "accepted_receipt_sha256",
        "acquisition_receipt_sha256",
        "output_sha256",
        "metadata_sha256",
        "reference_sha256",
        "description_sha256",
        "field_definitions_sha256",
        "official_response_followup",
    }
    return (
        set(proof) == expected
        and isinstance(conditions, list)
        and all(isinstance(condition, str) for condition in conditions)
        and set(conditions) == {PENDING}
        and proof["policy_id"] == POLICY
        and proof["status"] == "usable_with_assumptions_pending_official_confirmation"
        and proof["official_confirmation"] is False
        and proof["assumptions"] == ASSUMPTIONS
        and proof["scope"] == result.get("scope") == SCOPE
        and proof["native_period"] == result.get("period")
        and re.fullmatch(r"\d{4}M(?:0[1-9]|1[0-2])", str(proof["native_period"])) is not None
        and measurements_valid(proof["measurements"])
        and type(result.get("rows")) is int
        and proof["measurements"]["rows"] == result.get("rows")
        and all(
            hash_string(proof[key]) and proof[key] == result.get(key)
            for key in ("accepted_receipt_sha256", "acquisition_receipt_sha256")
        )
        and outputs_valid(proof["output_sha256"])
        and proof["output_sha256"] == result.get("output_sha256")
        and hash_string(proof["metadata_sha256"])
        and hash_string(proof["reference_sha256"])
        and proof["description_sha256"] == DESCRIPTION_SHA256
        and proof["field_definitions_sha256"] == DEFINITIONS_SHA256
        and proof["official_response_followup"]
        == "compare_official_response_then_version_affected_calculations_preserving_originals"
    )
