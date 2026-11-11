"""Refund/cancellation facts bound to their own observed claim, never other benefits."""

import re

TOPIC = r"\b(?:non-?refundable|reembolsable[s]?|reembolsos?|refundable|refunds?|cancelacion|cancellations?)\b"
OTHER_BENEFIT = (
    r"\b(?:check[- ]?in|equipaje|articulo personal|maleta|abordar|boarding|"
    r"cambios|changes|adelanto|advance|extras|seguros?|insurance|membresia)\b"
)


def _window(claim):
    purchase = bool(
        re.search(
            r"\b(?:(?:primeras?|first)\s+24\s*(?:horas?|h|hours?)|"
            r"(?:dentro de (?:las )?|within (?:the )?)24\s*(?:horas?|h|hours?))\b"
            r"[^.;]{0,45}\b(?:compra|purchase)\b",
            claim,
        )
    )
    departure = bool(
        re.search(
            r"\b(?:hasta|until|up to)\s+24\s*(?:horas?|h|hours?)\s+(?:antes|before)\b"
            r"[^.;]{0,70}\b(?:primer vuelo|first (?:flight|departure))\b",
            claim,
        )
    )
    return (
        "purchase_24h"
        if purchase and not departure
        else ("before_first_departure_24h" if departure and not purchase else None)
    )


def refund_facts(text):
    """Input is accent-folded source text; negative claims take precedence.

    Cancellation within a purchase window is a separate, explicit exception,
    not a general promise that a nonrefundable fare returns its payment.
    Additional material prerequisites unsupported by the closed contract keep
    that benefit unknown instead of advertising an unconditional entitlement.
    """
    denied, specifically_denied, affirmative = False, False, False
    windows, cancellation_exceptions, original_payment = set(), set(), False
    unsupported = False
    for clause in re.split(r"[.;,]|\b(?:pero|but|salvo|excepto|except)\b", text):
        topic = re.search(TOPIC, clause)
        if topic is None:
            continue
        prefix = clause[: topic.start()]
        claim = re.split(OTHER_BENEFIT, clause[topic.start() :], maxsplit=1)[0]
        general_denial = bool(
            re.search(
                r"\bnon-?refundable\b|\bnot refundable\b|\bno (?:es |son )?reembolsable[s]?\b", prefix + claim
            )
        )
        direct_denial = bool(
            re.search(
                r"\b(?:sin|no (?:incluye[n]?|admite[n]?|permite[n]?|hay|se permite)|no)\s+"
                r"(?:(?:el|la|un|una|a|the)\s+)?$",
                prefix,
            )
        )
        coordinated_denial = bool(
            re.search(r"\b(?:sin|no|no incluye[n]?|no permite[n]?)[^.;,:]{0,80}\b(?:ni|or)\s*$", prefix)
        )
        posterior_denial = bool(
            re.search(
                r"\b(?:(?:no|not) (?:esta[n]? |is |are )?(?:incluid[oa]s?|permitid[oa]s?|disponible[s]?|"
                r"allowed|available|permitted|included)|excluid[oa]s?|excluded|sin reembolso|no refunds?)\b",
                claim,
            )
        )
        if general_denial or direct_denial or coordinated_denial or posterior_denial:
            if re.search(r"\b(?:non-?refundable|reembolsos?|refunds?|reembolsable[s]?|refundable)\b", claim):
                denied = True
                specifically_denied |= not general_denial
            continue
        uncertain = bool(
            re.search(
                r"\b(?:no se (?:confirmo|confirma|mostro|muestra|observo)|sin confirmacion de)\s*$", prefix
            )
            or re.search(r"\b(?:no confirmad[oa]|not confirmed|sin confirmar)\b", claim)
        )
        if uncertain:
            continue
        # A separate minimum advance-purchase/departure requirement cannot be
        # replaced by the supported 24-hour refund/cancellation deadline.
        prerequisites = bool(
            re.search(
                r"\b(?:al menos|minim[oa](?: de)?|at least|minimum(?: of)?)\s+"
                r"(?:\d+|siete|seven)\s*(?:dias?|horas?|h|days?|hours?)\b"
                r"|\b(?:vuelo|salida|flight|departure)[^.;]{0,35}\bcon\s+\d+\s+dias? de antelacion\b"
                r"|\b(?:siempre que|sujeto a|subject to|if|con costo adicional)\b"
                r"|\bsi (?:el|la|se|los|las)\b",
                claim,
            )
        )
        window = _window(claim)
        prerequisites |= window is None and bool(
            re.search(
                r"\b(?:hasta|until|up to|dentro de|within|despues de|after)\s+"
                r"(?:(?:las|the) )?(?:(?:primeras|first) )?\d+\s*(?:horas?|h|hours?|dias?|days?)\b",
                claim,
            )
        )
        monetary = bool(re.search(r"\b(?:reembolsos?|refunds?|reembolsable[s]?|refundable)\b", claim))
        granted = monetary and bool(
            re.search(
                r"\b(?:reembolsable[s]?|refundable|total|disponible|available|permitid[oa]|allowed|aprobado)\b",
                claim,
            )
            or re.search(r"\b(?:incluye[n]?|includes?)\s*$", prefix)
            or window
            or re.search(r"\b(?:forma original de pago|original (?:form of )?payment)\b", claim)
        )
        cancellation = bool(re.search(r"\b(?:cancelacion|cancellations?)\b", claim))
        if prerequisites:
            unsupported |= granted or cancellation
            continue
        if cancellation and window == "purchase_24h":
            cancellation_exceptions.add(window)
        if granted:
            affirmative = True
            if window:
                windows.add(window)
            original_payment |= bool(
                re.search(r"\b(?:forma original de pago|original (?:form of )?payment)\b", claim)
            )
    refundable = False if denied else True if affirmative and not unsupported else None
    valid_windows = cancellation_exceptions if denied else windows | cancellation_exceptions
    if specifically_denied or unsupported:
        valid_windows = set()
    deadline = next(iter(valid_windows)) if len(valid_windows) == 1 else None
    if len(valid_windows) > 1 and not denied:
        refundable = None
    return dict(
        refundable=refundable,
        refund_deadline=deadline,
        refund_original_payment=True if refundable is True and original_payment else None,
    )
