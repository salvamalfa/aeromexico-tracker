"""Operational policy contracts with synthetic results, never proof of live data."""

import copy

import pytest

from src.source_updates import aerocivil, aerocivil_metadata
from src.source_updates import aerocivil_operational as policy
from src.source_updates import global_readiness as gate
from tests.test_source_update_global_independent import outcomes, recipe, selected


def checked_raw():
    return {
        "status": "checks_passed",
        "period": "2026M07",
        "scope": policy.SCOPE,
        "service_code_mapping_verified": False,
        "agent_eligible": False,
        "missing_operator_is_not_zero": True,
        "interpretation_acceptance": "pending_official_code_legend_and_entity_attribution_review",
        "commercial_designator_status": "source_derived_from_callsign_not_proven_marketing_carrier",
        "operator_designator_status": "source_derived_from_aircraft_registration_not_directly_captured",
        "metadata_review": {
            "dataset_id": "jh8x-n6h6",
            "description_sha256": policy.DESCRIPTION_SHA256,
            "field_definitions_sha256": policy.DEFINITIONS_SHA256,
            "service_code_mapping_verified": False,
            "entity_attribution": (
                "source_derived_callsign_and_aircraft_registration_not_independently_verified"
            ),
            "code_legend_status": "no_explicit_literal_mapping_in_reviewed_column_definitions",
        },
        "accepted_rows": 8,
        "raw_rows": 10,
        "source_counts": [10, 10],
        "reported_operations_under_selected_codes": 347,
        "operators_present": ["AMX"],
        "output_sha256": {name: "b" * 64 for name in aerocivil.OUTPUTS},
        "metadata_sha256": "c" * 64,
        "reference_sha256": "d" * 64,
    }


def provisional_result():
    raw = checked_raw()
    return {
        "status": "checks_passed",
        "product": "aerocivil",
        "period": raw["period"],
        "scope": raw["scope"],
        "rows": raw["accepted_rows"],
        "accepted_receipt_sha256": "e" * 64,
        "acquisition_receipt_sha256": "f" * 64,
        "output_sha256": raw["output_sha256"],
        "source_conditions": [policy.PENDING],
        "semantic_acceptance_verified": False,
        "latest_source_availability_verified": True,
        "operational_acceptance": policy.from_replay(raw, "e" * 64, "f" * 64),
    }


def test_operational_use_does_not_claim_official_confirmation_or_expand_scope():
    value = provisional_result()
    assert policy.accepted(value)
    assert value["semantic_acceptance_verified"] is False
    proof = value["operational_acceptance"]
    assert proof["official_confirmation"] is False
    assert proof["measurements"]["operators_present"] == ["AMX"]
    assert proof["native_period"] == "2026M07"
    assert "not_full_quarter" in proof["assumptions"]["coverage"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(status="blocked"),
        lambda r: r.update(accepted_rows=0),
        lambda r: r.update(accepted_rows=True),
        lambda r: r.update(source_counts=[10, 9]),
        lambda r: r.update(source_counts=[True, True]),
        lambda r: r.update(operators_present=[]),
        lambda r: r.update(operators_present=["VOI"]),
        lambda r: r.update(scope="global_network"),
        lambda r: r.update(period="2026Q3"),
        lambda r: r.update(reported_operations_under_selected_codes=-1),
        lambda r: r.update(agent_eligible=True),
        lambda r: r.update(service_code_mapping_verified=True),
        lambda r: r.update(output_sha256={}),
        lambda r: r.update(reference_sha256=None),
        lambda r: r["metadata_review"].update(description_sha256="0" * 64),
        lambda r: r["metadata_review"].update(field_definitions_sha256="0" * 64),
        lambda r: r["metadata_review"].update(dataset_id="another-dataset"),
        lambda r: r["metadata_review"].update(entity_attribution="independent_operator_proof"),
    ],
)
def test_policy_cannot_replace_empty_invalid_changed_or_expanded_source_evidence(mutate):
    raw = checked_raw()
    mutate(raw)
    assert policy.from_replay(raw, "e" * 64, "f" * 64) is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.update(status="blocked"),
        lambda r: r.update(rows=0),
        lambda r: r.update(semantic_acceptance_verified=True),
        lambda r: r.update(period="2026M08"),
        lambda r: r.update(scope="another_scope"),
        lambda r: r.update(accepted_receipt_sha256="0" * 64),
        lambda r: r.update(source_conditions=[policy.PENDING, "unknown_condition"]),
        lambda r: r["operational_acceptance"].update(official_confirmation=True),
        lambda r: r["operational_acceptance"].update(description_sha256="0" * 64),
        lambda r: r["operational_acceptance"]["assumptions"].update(traffic_I="officially_confirmed"),
    ],
)
def test_tampering_or_flags_without_bound_positive_replay_remain_blocked(mutate):
    result = copy.deepcopy(provisional_result())
    mutate(result)
    assert not policy.accepted(result)


def test_a_new_contradictory_legend_cannot_inherit_the_reviewed_semantics():
    definition = {
        "id": "jh8x-n6h6",
        "description": (
            "EMPRESA y EXPLOTADOR callsign matrícula trimestralmente. "
            "Nueva leyenda: S=doméstico; I=no regular."
        ),
        "columns": [
            {"fieldName": name, "description": description}
            for name, description in aerocivil_metadata.METADATA_FIELDS.items()
        ],
    }
    # The existing structural reader accepts these tokens; the operational pin must reject the change.
    review = aerocivil_metadata.review_metadata(definition)
    assert review["service_code_mapping_verified"] is False
    raw = checked_raw()
    raw["metadata_review"] = review
    assert policy.from_replay(raw, "e" * 64, "f" * 64) is None


def test_required_aerocivil_is_usable_with_warning_and_dependencies_keep_the_same_policy():
    value = recipe("quarterly")
    data = outcomes(value)
    item = selected(value, "aerocivil")
    item["source_period"] = "2026M07"
    data[item["id"]] = provisional_result()
    extra = selected(value, "h10")
    extra.update(used=True, depends_on=[item["id"]])
    decision = gate.evaluate(value, data)
    assert "aerocivil" in gate.REQUIRED["quarterly"]
    assert decision["core_ready"] and decision["requested_bundle_ready"]
    assert not any("aerocivil" in reason for reason in decision["calendar_blockers"])
    assert any("usable_with_assumptions" in warning for warning in decision["coverage_warnings"])
    task = next(task for task in decision["calendar_tasks"] if task["product"] == "aerocivil")
    assert task["official_confirmation"] is False
    assert task["operational_acceptance"]["policy_id"] == policy.POLICY
    assert decision["ready_for_automatic_execution"] is False


@pytest.mark.parametrize("change", ["missing", "unused", "blocked", "availability", "dependency"])
def test_provisional_policy_never_omits_data_or_current_availability_requirements(change):
    value = recipe("quarterly")
    data = outcomes(value)
    item = selected(value, "aerocivil")
    item["source_period"] = "2026M07"
    data[item["id"]] = provisional_result()
    if change == "missing":
        value["items"].remove(item)
    elif change == "unused":
        item["used"] = False
    elif change == "blocked":
        data[item["id"]]["status"] = "blocked"
    elif change == "availability":
        data[item["id"]]["latest_source_availability_verified"] = False
    else:
        parent = selected(value, "h10")
        parent["used"] = True
        item["depends_on"] = [parent["id"]]
        data[parent["id"]]["status"] = "blocked"
    decision = gate.evaluate(value, data)
    assert not decision["ready_for_calendar_incorporation"]
    if change != "availability":
        assert not decision["core_ready"]
    else:
        assert any(
            "current_source_availability_not_verified" in reason for reason in decision["calendar_blockers"]
        )
