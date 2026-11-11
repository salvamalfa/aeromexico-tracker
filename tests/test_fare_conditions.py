"""Public facts preserve observed meaning without releasing itinerary prose."""

import json
from copy import deepcopy

import pytest
from jsonschema.exceptions import ValidationError

from src.fare_quotes.aggregate import build_averages
from src.fare_quotes.conditions import condition_facts, render_conditions
from src.web_export.fare_averages import validate_averages
from tests.test_fare_averages import observation, private

PLUS = (
    "Un adulto; artículo personal y equipaje de mano (55 x 40 x 25 cm; "
    "peso combinado máximo 20 kg); maleta documentada de 25 kg (158 cm lineales); "
    "check-in app 7 días antes, reembolso hasta 24 horas antes del primer vuelo "
    "a la forma original de pago; cambios sin cargo de servicio pagando diferencia tarifaria; "
    "adelanto del vuelo el mismo día sujeto a disponibilidad; sin seguros ni extras opcionales."
)


def plus(**notes):
    return observation(
        provider="VOLARIS",
        fare="Plus",
        points=None,
        status="ok",
        conditions=PLUS,
        notes=json.dumps(
            dict(
                cabin="Economy",
                passengers=1,
                operator_outbound="Volaris México",
                operator_return="Volaris México",
                **notes,
            )
        ),
    )


def test_public_projection_closes_all_free_text_fields_and_preserves_private_input():
    secrets = "Y9 9876; 23:17; 2026-12-10; 17 diciembre; https://private.example/key; capture-secret"
    row = plus()
    row.update(
        fare=secrets,
        conditions=PLUS + secrets,
        notes=json.dumps(
            dict(
                cabin=secrets,
                operator_outbound=secrets,
                operator_return="Volaris Costa Rica",
                private=secrets,
            )
        ),
    )
    source = private(row)
    original = deepcopy(source)
    value = build_averages(source)
    validate_averages(value)
    raw = json.dumps(value)
    for secret in ("Y9 9876", "23:17", "2026-12-10", "17 diciembre", "https://", "capture-secret"):
        assert secret not in raw
    group = value["groups"][0]
    assert group["fare"] == "Tarifa no clasificada"
    assert group["condition_facts"]["cabin"] is None
    assert group["condition_facts"]["operator_outbound"] is None
    assert group["condition_facts"]["operator_return"] == "Volaris Costa Rica"
    assert source == original


def test_baggage_units_scopes_and_refund_deadlines_are_distinct():
    facts = condition_facts(plus(), PLUS)
    assert facts["personal_item_max_cm"] is None  # adjacent hand baggage limit is not personal item's
    assert facts["carry_on_max_cm"] == [55, 40, 25]
    assert facts["combined_personal_and_carry_on_kg"] == 20
    assert facts["checked_baggage_kg"] == 25
    assert facts["checked_baggage_linear_cm"] == 158
    assert facts["refundable"] is True
    assert facts["refund_deadline"] == "before_first_departure_24h"
    assert facts["refund_original_payment"] is True
    assert facts["changes"] == "service_fee_waived_fare_difference_due"
    viva = condition_facts(
        observation(fare="Zero"),
        "No reembolsable; cancelación primeras 24 horas tras compra; "
        "artículo personal 45 x 35 x 20 cm; sin equipaje de mano/documentado",
    )
    assert viva["refund_deadline"] == "purchase_24h"
    assert viva["refundable"] is False
    assert viva["personal_item_max_cm"] == [45, 35, 20]
    assert viva["carry_on"] is False and viva["checked_baggage"] is False
    assert "tras compra" in render_conditions(viva)
    assert "primera salida" in render_conditions(facts)


@pytest.mark.parametrize(
    "flag", ["seven_day_checkin_benefit_not_shown", "advance_checkin_not_shown_in_fare_details"]
)
def test_unobserved_checkin_is_never_inherited_from_standard_family_or_operator(flag):
    row = plus(**{flag: True})
    facts = condition_facts(row, PLUS)
    assert facts["checkin_advance_hours"] is None
    assert facts["checkin_channel"] is None
    row["notes"] = json.dumps(
        dict(operator_outbound="Volaris Costa Rica", operator_return="Volaris Costa Rica")
    )
    assert condition_facts(row, "Plus; beneficio de check-in no mostrado")["checkin_advance_hours"] is None


def test_checkin_hours_are_bound_to_checkin_not_adjacent_refund_or_negative_prose():
    assert condition_facts(plus(), PLUS)["checkin_advance_hours"] == 168
    negative = "No se mostró check-in app 7 días antes; reembolso hasta 24 horas antes del primer vuelo"
    assert condition_facts(plus(), negative)["checkin_advance_hours"] is None
    assert condition_facts(plus(), "check-in en línea 24 horas antes")["checkin_advance_hours"] == 24
    assert condition_facts(plus(), "check-in app 24 días antes")["checkin_advance_hours"] is None


def test_negated_baggage_or_direct_claims_are_not_positive_benefits():
    facts = condition_facts(
        observation(),
        "No incluye artículo personal; no incluye equipaje de mano; "
        "no incluye maleta documentada; no hay vuelos sin escalas",
    )
    assert facts["personal_item"] is False
    assert facts["carry_on"] is False
    assert facts["checked_baggage"] is False
    assert facts["direct_outbound"] is None and facts["direct_return"] is None


def test_explicit_round_trip_singular_direct_claim_covers_both_directions_only():
    facts = condition_facts(observation(), "1 adulto; ida y vuelta directa; tarifa Zero")
    assert facts["direct_outbound"] is True and facts["direct_return"] is True
    outbound = condition_facts(observation(), "salida directa")
    assert outbound["direct_outbound"] is True and outbound["direct_return"] is None
    for unconfirmed in (
        "itinerario directo",
        "directos",
        "sin escalas",
        "No se confirmó ida y vuelta directa",
    ):
        unknown = condition_facts(observation(), unconfirmed)
        assert unknown["direct_outbound"] is None and unknown["direct_return"] is None


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Un adulto; ida sin escalas; regreso con una escala", (True, False)),
        ("Ida con una escala / regreso sin escalas", (False, True)),
        ("Ida y vuelta: ida sin escalas y regreso con una escala", (True, False)),
        ("Ida directa; no se confirmó el regreso directo", (True, None)),
        ("Ambos vuelos directos", (True, True)),
    ],
)
def test_direct_evidence_is_scoped_to_each_leg(text, expected):
    facts = condition_facts(observation(), text)
    assert (facts["direct_outbound"], facts["direct_return"]) == expected


def test_one_way_never_creates_return_facts_and_conflicting_sources_remain_unknown():
    row = observation(return_date=None, notes=json.dumps(dict(direct_return=True, operator_return="Viva")))
    facts = condition_facts(row, "Un adulto; itinerario directo")
    assert facts["direct_outbound"] is True
    assert facts["direct_return"] is None and facts["operator_return"] is None
    row = observation(notes=json.dumps(dict(direct_outbound=True)))
    conflict = condition_facts(row, "ida con una escala; regreso directo")
    assert conflict["direct_outbound"] is None and conflict["direct_return"] is True


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Sin equipaje de mano ni equipaje documentado", (None, False, False)),
        ("No incluye artículo personal ni equipaje de mano ni equipaje documentado", (False, False, False)),
        ("Sin equipaje de mano/documentado", (None, False, False)),
        ("Sin equipaje de mano; incluye maleta documentada", (None, False, True)),
        ("Sin equipaje de mano pero incluye maleta documentada", (None, False, True)),
        ("Sin equipaje de mano, con maleta documentada", (None, False, True)),
        ("Sin equipaje de mano; incluye equipaje de mano", (None, None, None)),
        ("No se confirmó artículo personal ni equipaje de mano", (None, None, None)),
    ],
)
def test_coordinated_baggage_negation_stops_at_a_new_positive_claim(text, expected):
    facts = condition_facts(observation(), text)
    assert (facts["personal_item"], facts["carry_on"], facts["checked_baggage"]) == expected


def test_mixed_real_operators_require_explicit_common_benefits_evidence():
    row = plus()
    notes = json.loads(row["notes"])
    notes["operator_return"] = "Volaris Costa Rica"
    row["notes"] = json.dumps(notes)
    facts = condition_facts(row, PLUS)
    assert (facts["operator_outbound"], facts["operator_return"]) == ("Volaris Mexico", "Volaris Costa Rica")
    assert facts["benefits_scope"] == "not_verified_for_both"
    assert facts["carry_on"] is None and facts["checkin_advance_hours"] is None
    notes["plus_benefits_same_in_both_selected_fare_options"] = True
    notes["seven_day_checkin_benefit_not_shown"] = True
    row["notes"] = json.dumps(notes)
    facts = condition_facts(row, PLUS)
    assert facts["benefits_scope"] == "both_directions_verified"
    assert facts["checked_baggage_kg"] == 25
    assert facts["checkin_advance_hours"] is None


def test_same_public_label_does_not_merge_distinct_unknown_private_comparisons():
    a = observation(conditions="Condición privada sin equivalencia A", cash_final_mxn=100)
    b = observation(conditions="Condición privada sin equivalencia B", cash_final_mxn=300)
    value = build_averages(private(a, b))
    assert len(value["groups"]) == 2
    assert len({g["conditions"] for g in value["groups"]}) == 1
    assert len({g["group_id"] for g in value["groups"]}) == 2
    assert sorted(g["metrics"]["cash_final_mxn"]["mean"] for g in value["groups"]) == [100, 300]
    assert all(g["observations"] == 1 for g in value["groups"])
    assert build_averages(private(b, a)) == value


def test_unknown_fact_is_not_inherited_but_conflicting_explicit_operators_split():
    a = observation(notes="{}", cash_final_mxn=100)
    b = observation(notes=json.dumps(dict(no_optional_extras_added=True)), cash_final_mxn=300)
    group = build_averages(private(a, b))["groups"][0]
    assert group["condition_facts"]["optional_extras_added"] is None
    assert group["metrics"]["cash_final_mxn"] == {"mean": 200, "n": 2}
    a["notes"] = json.dumps(dict(operator_outbound="Volaris México"))
    b["notes"] = json.dumps(dict(operator_outbound="Volaris Costa Rica"))
    assert len(build_averages(private(a, b))["groups"]) == 2


def test_unrecognized_material_notes_remain_private_and_separate():
    a = observation(notes=json.dumps(dict(operator_return="Unknown carrier Y9 9876")))
    b = observation(notes=json.dumps(dict(operator_return="Other carrier Y9 9876")))
    value = build_averages(private(a, b))
    assert len(value["groups"]) == 2
    assert len({g["group_id"] for g in value["groups"]}) == 2
    assert all(g["condition_facts"]["operator_return"] is None for g in value["groups"])
    assert "Y9 9876" not in json.dumps(value)


def test_observed_english_fare_card_and_spanish_abbreviations_keep_restrictions():
    text = (
        "One personal item 45x35x20 cm under front seat; no carry-on or checked baggage; "
        "online check-in 24 hours before flight; last to board; no flight changes; "
        "nonrefundable after first 24 hours following purchase. No optional extras selected."
    )
    facts = condition_facts(observation(fare="Zero"), text)
    assert facts["personal_item_max_cm"] == [45, 35, 20]
    assert facts["carry_on"] is False and facts["checked_baggage"] is False
    assert facts["checkin_channel"] == "online" and facts["checkin_advance_hours"] == 24
    assert facts["boarding"] == "last" and facts["changes"] == "not_included"
    assert facts["refundable"] is False and facts["refund_deadline"] == "purchase_24h"
    assert facts["optional_extras_added"] is False
    for abbreviated in ("check-in 24h antes; sin cambios ni adelanto gratis", "check-in en linea 24 h antes"):
        assert condition_facts(observation(), abbreviated)["checkin_advance_hours"] == 24
    abbreviated = condition_facts(observation(), "sin cambios ni adelanto gratis")
    assert abbreviated["changes"] == "not_included" and abbreviated["same_day_advance"] == "free_not_included"
    assert condition_facts(observation(), "sin cambios de reserva")["changes"] == "not_included"


def test_explicit_optional_extras_boolean_is_retained_without_prose_defaults():
    for selected in (True, False):
        row = observation(notes=json.dumps(dict(optional_extras_added=selected)))
        assert condition_facts(row, "Condiciones observadas")["optional_extras_added"] is selected
    row = observation(notes=json.dumps(dict(optional_extras_added=True)))
    assert condition_facts(row, "sin extras ni login")["optional_extras_added"] is None


@pytest.mark.parametrize("tamper", ["label", "fare", "cabin", "operator", "extra"])
def test_public_contract_rejects_free_text_reintroduced_after_projection(tamper):
    value = build_averages(private(plus()))
    group = value["groups"][0]
    if tamper == "label":
        group["conditions"] += "; Y9 9876 23:17 https://private.example"
    elif tamper == "fare":
        group["fare"] = "Y9 9876"
    elif tamper == "extra":
        group["condition_facts"]["flight"] = "Y9 9876"
    else:
        group["condition_facts"]["operator_return" if tamper == "operator" else "cabin"] = "Y9 9876"
    with pytest.raises((ValueError, ValidationError)):
        validate_averages(value)
