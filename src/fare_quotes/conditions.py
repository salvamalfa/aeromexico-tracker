"""Closed public fare facts; itinerary prose remains exclusively private."""

from __future__ import annotations

import json
import re
import unicodedata

VERSION = "fare_condition_facts_v1"
FAMILIES = {"main": "Main", "premier": "Premier", "zero": "Zero", "plus": "Plus"}
CABINS = {
    "economy": "Economy",
    "economica": "Economy",
    "business": "Business",
    "premium economy": "Premium Economy",
    "first": "First",
    "main": "Main",
    "premier": "Premier",
}
OPERATORS = {
    "aeromexico": "Aeromexico",
    "aeromexico connect": "Aeromexico Connect",
    "viva": "Viva",
    "viva aerobus": "Viva",
    "vivaaerobus": "Viva",
    "volaris mexico": "Volaris Mexico",
    "volaris costa rica": "Volaris Costa Rica",
    "volaris el salvador": "Volaris El Salvador",
}
CONTRACTS = {
    "installed_worker_schema_pair_and_fenced_sheet_readback",
    "installed_worker_schema_and_fenced_sheet_readback",
}
BENEFITS = (
    "personal_item",
    "personal_item_max_cm",
    "carry_on",
    "carry_on_max_cm",
    "combined_personal_and_carry_on_kg",
    "checked_baggage",
    "checked_baggage_kg",
    "checked_baggage_linear_cm",
    "refundable",
    "refund_deadline",
    "refund_original_payment",
    "changes",
    "same_day_advance",
    "checkin_channel",
    "checkin_advance_hours",
    "boarding",
)


def fold(value):
    if not isinstance(value, str):
        return ""
    return " ".join(
        "".join(
            c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c)
        ).split()
    )


def source_notes(row):
    try:
        value = json.loads(row.get("notes") or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def public_fare(value):
    return FAMILIES.get(fold(value), "Tarifa no clasificada")


def unclassified_comparison_notes(row):
    """Private identity only: an unrecognized material value is not equivalence."""
    notes = source_notes(row)
    unknown = {}
    for key, catalog in (("cabin", CABINS), ("operator_outbound", OPERATORS), ("operator_return", OPERATORS)):
        if notes.get(key) is not None and fold(notes[key]) not in catalog:
            unknown[key] = notes[key]
    passengers = notes.get("passengers")
    if (
        passengers is not None
        and passengers != "A1"
        and not (type(passengers) is int and 0 < passengers <= 9)
    ):
        unknown["passengers"] = passengers
    return unknown


def _bool(notes, key):
    value = notes.get(key)
    return value if isinstance(value, bool) else None


def _bounded_number(text, pattern, maximum):
    match = re.search(pattern, text)
    if match:
        value = int(match[1])
        if 0 < value <= maximum:
            return value
    return None


def _dimensions(text, item):
    # A nearby limit for the next baggage item is not this item's limit.
    other_item = r"(?:equipaje de mano|articulo personal|maleta documentada|equipaje documentado)"
    match = re.search(
        item + r"(?:(?!" + other_item + r")[^.;]){0,45}?"
        r"(\d{1,2})\s*[x×]\s*(\d{1,2})\s*[x×]\s*(\d{1,2})\s*cm",
        text,
    )
    if match:
        values = [int(v) for v in match.groups()]
        if all(0 < v <= 99 for v in values):
            return values
    return None


def observed_text(value):
    """Strict equivalents observed in the English guest fare card, not defaults."""
    text = fold(value)
    for original, equivalent in (
        ("one personal item", "articulo personal"),
        ("no carry-on or checked baggage", "sin equipaje de mano/documentado"),
        ("online check-in", "check-in en linea"),
        ("24 hours before flight", "24 horas antes"),
        ("last to board", "ultimo en abordar"),
        ("no flight changes", "sin cambios de vuelo"),
        (
            "nonrefundable after first 24 hours following purchase",
            "no reembolsable; primeras 24 horas tras compra",
        ),
        ("no optional extras selected", "no se anadieron extras opcionales"),
    ):
        text = text.replace(original, equivalent)
    return text


def _direct_claim(text):
    if re.search(r"\bno (?:se )?(?:confirm\w*|mostr\w*|observ\w*|hay)\b|\bsin confirmacion\b", text):
        return None
    negative = r"\b(?:con (?:una|un|[1-9]) escalas?|no (?:es |son )?direct[oa]s?)\b"
    denied = bool(re.search(negative, text))
    affirmative = bool(re.search(r"\b(?:sin escalas|direct[oa]s?)\b", re.sub(negative, "", text)))
    return None if denied == affirmative else not denied


def direction_facts(text, has_return):
    """A leg-specific claim cannot supply evidence for the other leg."""
    values = {"direct_outbound": set(), "direct_return": set()}
    for clause in re.split(r"[.;,]|\bpero\b", text):
        both = re.search(
            r"\b(?:ida y vuelta|ambos (?:vuelos|tramos))\s+(?:son )?"
            r"(?:sin escalas|direct[oa]s?|no direct[oa]s?|con (?:una|un|[1-9]) escalas?)\b",
            clause,
        )
        if both:
            claim = _direct_claim(clause)
            if claim is not None:
                values["direct_outbound"].add(claim)
                if has_return:
                    values["direct_return"].add(claim)
            continue
        mentions = list(re.finditer(r"\b(ida|salida|regreso|vuelta)\b", clause))
        for index, mention in enumerate(mentions):
            end = mentions[index + 1].start() if index + 1 < len(mentions) else len(clause)
            # Include a preceding denial/uncertainty, but never the other leg's claim.
            start = 0 if index == 0 else mention.start()
            uncertainty = re.search(
                r"\bno se (?:confirmo|confirma|mostro|muestra|observo)\s+(?:el |la )?$",
                clause[: mention.start()],
            )
            if uncertainty:
                start = uncertainty.start()
            claim = _direct_claim(clause[start:end])
            key = "direct_outbound" if mention[1] in {"ida", "salida"} else "direct_return"
            if claim is not None and (has_return or key == "direct_outbound"):
                values[key].add(claim)
        if not mentions and not has_return:
            claim = _direct_claim(clause)
            if claim is not None:
                values["direct_outbound"].add(claim)
    return {key: next(iter(found)) if len(found) == 1 else None for key, found in values.items()}


def baggage_facts(text):
    """Keep a coordinated negation inside its list, stopping at contrast/new clauses."""
    values = {key: set() for key in ("personal_item", "carry_on", "checked_baggage")}
    items = (
        r"(?P<personal_item>(?:articulo|equipaje) personal)"
        r"|(?P<carry_on>equipaje de mano)|(?P<checked_baggage>(?:(?:maleta|equipaje) )?documentad[oa])"
    )
    for clause in re.split(r"[.;]|\bpero\b|\bsin embargo\b", text):
        previous, previous_value, previous_uncertain = None, None, False
        for mention in re.finditer(items, clause):
            prefix = clause[: mention.start()]
            between = clause[previous.end() : mention.start()] if previous else prefix
            negative = re.search(r"\b(?:sin|no incluye[n]?)(?: (?:un|una|ningun|ninguna|el|la))?\s*$", prefix)
            coordinated = previous is not None and re.fullmatch(r"\s*(?:ni|/|o|y|,)\s*", between)
            positive_reset = re.search(r"\b(?:con|incluye[n]?)\s*$", between)
            # Uncertainty must govern this item, not an unrelated refund/login
            # restriction earlier in the clause. Carry it only across its list.
            uncertain = bool(
                re.search(
                    r"\b(?:no se (?:confirmo|confirma|mostro|muestra|observo)|sin confirmacion de)"
                    r"\s+(?:(?:el|la|un|una) )?$",
                    prefix,
                )
            ) or (bool(coordinated) and previous_uncertain)
            if negative or (previous_value is False and coordinated):
                value = False
            elif positive_reset:
                value = True
            elif previous_value is False or uncertain:
                value = None
            else:
                value = True
            values[mention.lastgroup].add(value)
            previous, previous_value, previous_uncertain = mention, value, value is None
    return {key: next(iter(found)) if len(found) == 1 else None for key, found in values.items()}


def condition_facts(row, private_conditions):
    """Extract only explicit observations, never standard benefits by provider."""
    text, notes = observed_text(private_conditions), source_notes(row)
    family = public_fare(row.get("fare"))
    facts = dict(
        schema_version=VERSION,
        family=None if family == "Tarifa no clasificada" else family,
        cabin=CABINS.get(fold(notes.get("cabin"))),
        passengers=None,
        adults=None,
        direct_outbound=_bool(notes, "direct_outbound"),
        direct_return=_bool(notes, "direct_return"),
        operator_outbound=OPERATORS.get(fold(notes.get("operator_outbound"))),
        operator_return=OPERATORS.get(fold(notes.get("operator_return"))),
        optional_extras_added=_bool(notes, "optional_extras_added"),
        membership_included=_bool(notes, "vclub_included"),
        benefits_scope="observed_fare_terms",
        **{key: None for key in BENEFITS},
    )
    passengers = notes.get("passengers")
    if type(passengers) is int and 0 < passengers <= 9:
        facts["passengers"] = passengers
    adult = re.search(r"\b(un|[1-9]) adulto(?:s)?\b", text)
    if adult or passengers == "A1":
        facts["adults"] = 1 if not adult or adult[1] == "un" else int(adult[1])
        facts["passengers"] = facts["passengers"] or facts["adults"]
    if row["provider"] == "AMR" and notes.get("validation") in CONTRACTS:
        facts.update(adults=1, passengers=1)
        if family in {"Main", "Premier"}:
            facts["cabin"] = family
    has_return = bool(row.get("return_date"))
    for key, claim in direction_facts(text, has_return).items():
        if claim is not None:
            facts[key] = claim if facts[key] is None or facts[key] == claim else None
    if not has_return:
        facts.update(direct_return=None, operator_return=None)
    if notes.get("no_optional_extras_added") is True or re.search(
        r"(?:sin (?:seguros ni )?extras opcionales|no se anadieron extras opcionales|sin extras ni login)",
        text,
    ):
        facts["optional_extras_added"] = None if facts["optional_extras_added"] is True else False
    if facts["membership_included"] is None and "sin membresia" in text:
        facts["membership_included"] = False

    facts.update(baggage_facts(text))
    if facts["personal_item"] is True:
        facts["personal_item_max_cm"] = _dimensions(text, r"(?:articulo|equipaje) personal")
    if facts["carry_on"] is True:
        facts["carry_on_max_cm"] = _dimensions(text, "equipaje de mano")
        facts["combined_personal_and_carry_on_kg"] = _bounded_number(
            text, r"combinado[^.;]{0,100}?(\d{1,2})\s*kg", 50
        )
    if facts["checked_baggage"] is True:
        facts["checked_baggage_kg"] = _bounded_number(text, r"documentad[oa][^.;]{0,20}?(\d{1,2})\s*kg", 50)
        facts["checked_baggage_linear_cm"] = _bounded_number(text, r"\b(\d{2,3})\s*cm lineales", 300)
    purchase = bool(re.search(r"24 horas.{0,30}(compra)|primeras 24 horas", text))
    before_departure = bool(re.search(r"24 horas antes.{0,70}primer vuelo", text))
    if purchase != before_departure:
        facts["refund_deadline"] = "purchase_24h" if purchase else "before_first_departure_24h"
    if "no reembolsable" in text:
        facts["refundable"] = False
    elif "reembolso" in text and before_departure:
        facts["refundable"] = True
    if "reembolso" in text and "forma original de pago" in text:
        facts["refund_original_payment"] = True
    if any(
        term in text
        for term in ("sin cambios de vuelo", "sin cambios de reserva", "sin cambios ni adelanto gratis")
    ):
        facts["changes"] = "not_included"
    elif re.search(r"cambios[^.;]{0,40}sin cargo[^.;]{0,80}(diferencia|nivelacion) tarifaria", text):
        facts["changes"] = "service_fee_waived_fare_difference_due"
    if (
        re.search(r"sin adelanto(?: de vuelo)? (?:gratis|de vuelo gratis)", text)
        or "ni adelanto gratis" in text
    ):
        facts["same_day_advance"] = "free_not_included"
    elif "adelanto" in text and "sujeto a disponibilidad" in text:
        facts["same_day_advance"] = "subject_to_availability"
    if "ultimo en abordar" in text:
        facts["boarding"] = "last"
    checkin_clauses = re.findall(r"[^.;,]*check[- ]?in[^.;,]*", text)
    not_shown = any(
        notes.get(key) is True
        for key in ("seven_day_checkin_benefit_not_shown", "advance_checkin_not_shown_in_fare_details")
    )
    negative_checkin = any(
        re.search(
            r"\bno (?:se (?:muestra|mostro|observo)|indica[n]?|muestra[n]?)[^.;]{0,60}check[- ]?in"
            r"|\bsin (?:beneficio de )?check[- ]?in"
            r"|check[- ]?in[^.;]{0,60}\b(?:no (?:aplica|incluido|mostrado|confirmado|observado)|not shown)",
            clause,
        )
        for clause in checkin_clauses
    )
    if not not_shown and not negative_checkin:
        values = {
            hours
            for clause in checkin_clauses
            for pattern, hours in ((r"\b7 dias antes\b", 168), (r"\b24\s*(?:horas?|h) antes\b", 24))
            if re.search(pattern, clause)
        }
        if len(values) == 1:
            facts["checkin_advance_hours"] = values.pop()
            if any("app" in clause for clause in checkin_clauses):
                facts["checkin_channel"] = "app"
            elif any("en linea" in clause for clause in checkin_clauses):
                facts["checkin_channel"] = "online"
    operators = (facts["operator_outbound"], facts["operator_return"])
    if all(operators) and operators[0] != operators[1]:
        if notes.get("plus_benefits_same_in_both_selected_fare_options") is True:
            facts["benefits_scope"] = "both_directions_verified"
        else:
            facts["benefits_scope"] = "not_verified_for_both"
            for key in BENEFITS:
                facts[key] = None
    return facts


def render_conditions(facts):
    """All words come from constants; only bounded typed quantities are inserted."""
    parts = []
    if facts["cabin"] is not None:
        parts.append("Cabina: " + facts["cabin"])
    for key, label in (("passengers", "Pasajeros"), ("adults", "Adultos")):
        if facts[key] is not None:
            parts.append(f"{label}: {facts[key]}")
    for key, label in (
        ("direct_outbound", "Directo ida"),
        ("direct_return", "Directo regreso"),
        ("personal_item", "Articulo personal"),
        ("carry_on", "Equipaje de mano"),
        ("checked_baggage", "Equipaje documentado"),
        ("optional_extras_added", "Extras anadidos"),
        ("membership_included", "Membresia incluida"),
    ):
        if facts[key] is not None:
            parts.append(f"{label}: {'si' if facts[key] else 'no'}")
    for key, label in (
        ("personal_item_max_cm", "Limite articulo personal"),
        ("carry_on_max_cm", "Limite mano"),
    ):
        if facts[key] is not None:
            parts.append(label + ": " + " x ".join(str(v) for v in facts[key]) + " cm")
    for key, label, unit in (
        ("combined_personal_and_carry_on_kg", "Peso combinado personal y mano", "kg"),
        ("checked_baggage_kg", "Peso documentado", "kg"),
        ("checked_baggage_linear_cm", "Tamano lineal documentado", "cm"),
    ):
        if facts[key] is not None:
            parts.append(f"{label}: {facts[key]} {unit}")
    if facts["refundable"] is not None:
        parts.append("Reembolsable: " + ("si" if facts["refundable"] else "no"))
    deadline = {
        "purchase_24h": "Cancelacion: primeras 24 horas tras compra",
        "before_first_departure_24h": "Reembolso: hasta 24 horas antes de la primera salida",
    }
    if facts["refund_deadline"] is not None:
        parts.append(deadline[facts["refund_deadline"]])
    if facts["refund_original_payment"] is True:
        parts.append("Reembolso a forma original de pago")
    changes = {
        "not_included": "Cambios de vuelo no incluidos",
        "service_fee_waived_fare_difference_due": "Cambios sin cargo de servicio; diferencia tarifaria",
    }
    if facts["changes"] is not None:
        parts.append(changes[facts["changes"]])
    advance = {
        "free_not_included": "Adelanto gratis no incluido",
        "subject_to_availability": "Adelanto el mismo dia sujeto a disponibilidad",
    }
    if facts["same_day_advance"] is not None:
        parts.append(advance[facts["same_day_advance"]])
    checkin = "Check-in: no confirmado"
    if facts["checkin_advance_hours"] is not None:
        channel = {"app": "app", "online": "en linea", None: "canal no confirmado"}[facts["checkin_channel"]]
        checkin = f"Check-in {channel}: {facts['checkin_advance_hours']} horas antes"
    parts.append(checkin)
    if facts["boarding"] == "last":
        parts.append("Ultimo en abordar")
    for key, label in (("operator_outbound", "Operador ida"), ("operator_return", "Operador regreso")):
        parts.append(label + ": " + (facts[key] or "no confirmado"))
    if facts["benefits_scope"] == "not_verified_for_both":
        parts.append("Beneficios de ambos tramos no confirmados")
    else:
        parts.append("Beneficios y restricciones limitados a lo observado")
    return "; ".join(parts)
