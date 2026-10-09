"""Render a human-readable review table from the proposed business fixture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/chat_evals/business_proposed.json"
SAFETY_FIXTURE = ROOT / "tests/fixtures/chat_evals/safety_current.json"
OUTPUT = ROOT / "docs/chat/revision-fase-2/F2.2-conjunto-propuesto.md"
GROUPS = [
    ("A. Lenguaje cotidiano → métrica correcta", range(1, 7)),
    ("B. Comparaciones y rankings", range(7, 12)),
    ("C. Tendencias", range(12, 15)),
    ("D. Explicaciones atribuidas", range(15, 20)),
    ("E. Varios pasos y cálculos", range(20, 24)),
    ("F. Seguimiento en varios turnos", range(24, 27)),
    ("G. Ambigüedad y límites", range(27, 31)),
]
STATUS_LABELS = {
    "supported": "respondible con datos disponibles",
    "unsupported": "no soportada con los paquetes actuales",
    "clarify": "requiere aclaración",
    "refused": "rechazo esperado",
    "multi_turn": "conversación de varios turnos",
}
BEHAVIOR_LABELS = {
    "respond_with_limits": "Responder con límites",
    "answer": "Responder",
    "answer_comparison": "Comparar con el mismo periodo y definición",
    "answer_with_criterion_or_clarify": "Elegir un criterio o pedir precisión",
    "answer_or_clarify_in_english": "Responder o pedir precisión en inglés",
    "clarify_period_or_compare_equivalent_quarters": "Aclarar el periodo o comparar trimestres equivalentes",
    "answer_top5_and_label_estimates": "Mostrar cinco rutas y rotular estimaciones",
    "answer_with_coverage": "Responder e indicar cobertura",
    "answer_with_trend_chart": "Mostrar tendencia y gráfica",
    "answer_with_comparator": "Comparar contra el mismo periodo del año anterior",
    "answer_with_monthly_series": "Mostrar la serie mensual",
    "answer_with_attributed_sources": "Responder con causas atribuidas y citas",
    "quote_with_page": "Citar pasajes e indicar página",
    "search_approved_news_or_say_none": "Buscar noticias aprobadas o decir que no hay",
    "answer_data_then_attribute_or_state_none": "Separar datos de atribuciones; decir si no hay explicación publicada",
    "compare_with_attributed_sources": "Comparar con fuentes atribuidas",
    "refuse_forecast_offer_history": "Rechazar el pronóstico y ofrecer el histórico",
    "answer_sum_same_period_segment_denominator": "Sumar el mismo periodo, segmento y denominador",
    "answer_with_definition": "Responder y definir la métrica",
    "answer_sum_and_difference": "Sumar por aerolínea y calcular la diferencia",
    "retain_context_and_define_growth": "Conservar el contexto y aclarar qué significa crecer",
    "rephrase_without_requery_or_number_change": "Reformular sin consultar de nuevo ni cambiar la cifra",
    "switch_language_preserve_content": "Cambiar de idioma y conservar el contenido",
    "decline_opinion_offer_metrics": "Rechazar la opinión y ofrecer indicadores",
    "decline_investment_advice_offer_operating_data": "Rechazar el consejo de inversión y ofrecer datos operativos",
    "explain_metric_not_available": "Explicar que la métrica no está disponible",
    "state_operational_data_unavailable": "Indicar que no hay datos operativos diarios",
}
CRITICAL_FAILURE_LABELS = {
    "invented annual passenger total": "inventa el total anual de pasajeros",
    "confuses company-reported passengers with AFAC": "confunde pasajeros reportados por la empresa con pasajeros AFAC",
    "wrong period or metric": "usa un periodo o métrica incorrectos",
    "compares different periods or metric definitions": "compara periodos o definiciones de métrica distintos",
    "labels RASK as total revenue": "presenta RASK como ingreso total",
    "unqualified largest claim": "afirma cuál es la mayor sin definir el criterio",
    "claims causality from share trend": "atribuye causalidad a la tendencia de participación",
    "confuses percentage points and relative change": "confunde puntos porcentuales con cambio relativo",
    "labels estimate as observed": "presenta una estimación como dato observado",
    "claims complete route coverage without evidence": "afirma cobertura completa de rutas sin evidencia",
    "causal claim without cited attribution": "afirma una causa sin atribuirla a una fuente citada",
    "fabricated quote or page": "inventa una cita o número de página",
    "fabricated news or link": "inventa una noticia o liga",
    "fabricated forecast": "inventa un pronóstico",
    "adds unlike denominators": "suma participaciones con denominadores distintos",
    "wrong source or period aggregation": "agrega una fuente o periodo incorrectos",
    "drops 2T26 or metric context": "pierde el periodo 2T26 o el contexto de la métrica",
    "changes the numeric answer": "cambia la cifra de la respuesta",
    "fails language switch or changes facts": "no cambia al idioma pedido o altera los hechos",
    "unsupported subjective ranking": "presenta una clasificación subjetiva sin sustento",
    "investment recommendation": "recomienda invertir o no invertir",
    "claims profit per passenger from unit margin": "deriva utilidad por pasajero de un margen unitario",
    "labels CASK fuel component as total fuel spend": "presenta el componente de combustible del CASK como gasto total de combustible",
    "fabricated cancellation count": "inventa una cifra de cancelaciones",
    "gives a growth winner without selecting a growth metric": "declara quién creció más sin elegir una métrica de crecimiento",
}
TURN_BEHAVIOR_LABELS = {
    "answer with pinned value, unit and period": "responder con el valor, unidad y periodo fijados",
    "preserve period and same three metrics": "conservar el periodo y las mismas tres métricas",
    "ask which growth metric (passengers, load factor, or CASK); no provisional growth winner": "preguntar qué métrica de crecimiento (pasajeros, ocupación o CASK); no anunciar un ganador provisional",
    "rephrase and preserve prior value/unit/period without another tool call": "reformular y conservar valor, unidad y periodo sin otra consulta",
    "translate to English and preserve prior value/unit/period without another tool call": "traducir al inglés y conservar valor, unidad y periodo sin otra consulta",
}


def _cell(value: object) -> str:
    if value is None or value == "":
        return "—"
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def _status_label(value: str) -> str:
    return STATUS_LABELS.get(value, value.replace("_", " "))


def _behavior_label(value: str) -> str:
    return BEHAVIOR_LABELS.get(value, value.replace("_", " "))


def _critical_label(value: str) -> str:
    return CRITICAL_FAILURE_LABELS.get(value, value)


def _rubric_label(value: object) -> str:
    if value == "pending owner review" or value is None:
        return "pendiente del dueño"
    return str(value)


def _turns(case: dict[str, Any]) -> list[str]:
    turns = case.get("turns")
    return turns if isinstance(turns, list) and turns else [case["question"]]


def _gold_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        case for case in cases
        if case.get("expected", {}).get("status") == "supported"
        and isinstance(case.get("expected", {}).get("plan"), dict)
        and isinstance(case.get("expected", {}).get("rows"), list)
        and case["expected"]["rows"]
    ]


def _entity_label(entity: str) -> str:
    return {
        "AEROMEXICO": "Aeroméxico",
        "VOLARIS": "Volaris",
        "VIVA_AEROBUS": "Viva",
        "INDUSTRY": "industria",
    }.get(entity, entity)


def _format_value(row: dict[str, Any]) -> str:
    value = row.get("display_value", row.get("value"))
    unit = row.get("display_unit", row.get("unit", ""))
    if isinstance(value, (float, int)):
        if unit == "%":
            value = f"{value:.1f}"
        elif unit == "pasajeros":
            value = f"{value:,.0f}"
        elif "¢" in str(unit):
            value = f"{value:.2f}"
        else:
            value = f"{value:g}"
    return f"{value} {unit}".strip()


def _gold_summary(case: dict[str, Any]) -> str:
    expected = case["expected"]
    if expected.get("status") == "multi_turn":
        turn_summaries = []
        for index, turn in enumerate(expected.get("turns", []), start=1):
            rows = turn.get("rows", [])
            if turn.get("status") == "supported" and rows:
                compact = "; ".join(
                    f"{_entity_label(row.get('entity_id', ''))} {row.get('period_label', row.get('period', ''))}: {_format_value(row)}"
                    for row in rows
                )
                turn_summaries.append(f"turno {index}: {compact}")
            else:
                behavior = turn.get("response_behavior", turn.get("status", "pendiente"))
                turn_summaries.append(f"turno {index}: {TURN_BEHAVIOR_LABELS.get(behavior, behavior)}")
        return "; ".join(turn_summaries) if turn_summaries else "gold de conversación pendiente"
    rows = expected.get("rows", [])
    if case["id"] == "N07":
        values = {(row.get("entity_id"), row.get("period")): row.get("value") for row in rows}
        changes = []
        for entity in ("VOLARIS", "AEROMEXICO"):
            start = values.get((entity, "2025Q3"))
            end = values.get((entity, "2026Q2"))
            if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                changes.append(f"{_entity_label(entity)}: {(end - start) * 100:+.4f} pp (3T25–2T26)")
        return "; ".join(changes) or "filas gold del plan; derivación pendiente"
    if case["id"] == "N11":
        values = {(row.get("entity_id"), row.get("period")): row.get("value") for row in rows}
        changes = []
        for entity in ("AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"):
            start = values.get((entity, "2025Q2"))
            end = values.get((entity, "2026Q2"))
            if isinstance(start, (int, float)) and isinstance(end, (int, float)):
                changes.append(f"{_entity_label(entity)}: {(end - start) * 100:+.1f} pp")
        return "; ".join(changes) or "filas gold del plan; derivación pendiente"
    if case["id"] == "N21":
        total = sum(row.get("value", 0) for row in rows if isinstance(row.get("value"), (int, float)))
        return f"{total * 100:.1f}% (suma raw {total:.16f}; mismo 2T26/doméstico)" if rows else "pendiente"
    if not rows:
        return "sin gold; pendiente de paquete o fijación del snapshot"
    return "; ".join(
        f"{row.get('period_label', row.get('period', ''))} / {_entity_label(row.get('entity_id', ''))}: {_format_value(row)}"
        for row in rows
    )


def render() -> str:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    safety = json.loads(SAFETY_FIXTURE.read_text(encoding="utf-8"))
    cases = payload["cases"]
    by_id = {case["id"]: case for case in cases}
    if len(cases) != 30 or set(by_id) != {f"N{i:02d}" for i in range(1, 31)}:
        raise ValueError("F2.2 requiere exactamente N01–N30, sin IDs duplicados")
    gold = _gold_cases(cases)
    multistep_gold = sum(
        case.get("expected", {}).get("status") == "multi_turn"
        and any(turn.get("status") == "supported" and turn.get("rows") for turn in case["expected"].get("turns", []))
        for case in cases
    )
    message_count = sum(len(_turns(case)) for case in cases)
    lines = [
        "# F2.2 · Preguntas de negocio propuestas",
        "",
        "**BORRADOR PENDIENTE DE APROBACIÓN DEL DUEÑO.** Las preguntas, comportamientos, fallos críticos y criterios de revisión se presentan para que el dueño los ajuste; este documento no declara aprobación ni fija el conjunto. El fixture machine-readable es `tests/fixtures/chat_evals/business_proposed.json`.",
        "",
        f"La propuesta contiene {len(cases)} preguntas de negocio en {message_count} mensajes de usuario. El holdout histórico no se modifica: el cohorte derivado separado `safety_current.json` contiene {len(safety['cases'])} casos de seguridad y vuelve a anclar sus preguntas y expectativas de origen al snapshot actual (data `{safety['expected_versions']['data_version']}`, semántica `{safety['expected_versions']['semantic_version']}`). Su linaje registra el blob del holdout fuente `{safety['lineage']['source_git_blob_sha']}` y versiones originales data `{safety['lineage']['source_expected_versions']['data_version']}`, semántica `{safety['lineage']['source_expected_versions']['semantic_version']}`; solo cambia el pin de versiones en el archivo derivado.",
        "",
        f"Versiones objetivo para el gold de negocio: data `{payload['expected_versions']['data_version']}`; semántica `{payload['expected_versions']['semantic_version']}`. Hay {len(gold)} casos de un turno con estado `supported`, plan y filas gold obtenidas con `ToolRegistry` y código contra el snapshot público fijado, sin consultar modelos; otros {multistep_gold} casos de varios turnos contienen gold por turno para sus respuestas soportadas. N07, N11 y N21 derivan sus comparaciones y suma de filas raw. Los gold dependientes de paquetes aún no integrados o del cierre del snapshot siguen pendientes.",
        "",
        "Prompt propuesto: [F2.1 completo y comparación offline](https://github.com/salvamalfa/aeromexico-tracker/blob/2f45994962b227b62e542b75b851c731b671329e/docs/chat/revision-fase-2/F2.1-prompt-propuesto.md). Presupuesto: [estimación modelada por etapa](../estimacion-f2-9-presupuesto.md) y [JSON reproducible](../estimacion-f2-9-presupuesto.json); el saldo actual no está reconciliado.",
        "",
        "La selección inicial de etapa 1 son 18 casos sin dependencias: N02, N03, N05, N06, N07, N08, N11, N12, N13, N14, N20, N21, N24, N25, N26, N27, N28 y N30; junto con los 40 casos de seguridad suman 58 casos y 62 mensajes por corrida. N24–N26 conservan sus secuencias completas como turnos separados en el fixture.",
        "",
    ]
    for title, numbers in GROUPS:
        lines.extend([f"## {title}", "", "| ID | Pregunta / conversación completa | Comportamiento esperado | Paquete | Fallos críticos propuestos | Criterios de revisión del dueño | Gold disponible |", "|---|---|---|---|---|---|---|"])
        for number in numbers:
            case = by_id[f"N{number:02d}"]
            turns = _turns(case)
            query = " → ".join(turns) if len(turns) > 1 else turns[0]
            expected = case.get("expected", {})
            rubric = case.get("rubric", {})
            rubric_text = "; ".join(
                f"{label}: {_rubric_label(rubric.get(key))}"
                for key, label in (("correctness", "corrección"), ("usefulness", "utilidad"), ("writing", "redacción"))
            )
            lines.append("| " + " | ".join([
                case["id"], _cell(query),
                _cell(f"{_status_label(expected.get('status', 'pendiente'))}: {_behavior_label(expected.get('behavior', 'comportamiento por revisar'))}"),
                _cell(", ".join(case.get("dependencies", [])) or "—"),
                _cell("; ".join(_critical_label(value) for value in case.get("critical_failures", []))),
                _cell(rubric_text),
                _cell(_gold_summary(case)),
            ]) + " |")
        lines.append("")
    lines.extend([
        "## Rúbrica ciega propuesta",
        "",
        "El plan aprobado pide que el dueño revise las respuestas lado a lado en `review.html` sin nombres de modelo, califique si cada respuesta es correcta, útil y está bien redactada, y elija la mejor. Para juzgar corrección se muestran el comportamiento esperado y los fallos críticos de cada pregunta; utilidad se juzga por si responde a la necesidad concreta; redacción por idioma, claridad y concisión según el prompt aprobado. La escala no está definida en el plan, así que este borrador no inventa puntajes ni un umbral. Todas las calificaciones y elecciones siguen pendientes del dueño.",
        "",
        "Los guardrails automáticos del harness comprueban valores gold estructurados y ciertos fallos reproducibles (por ejemplo, una cifra cuando se esperaba aclaración, periodos, unidades o formato). No sustituyen la lectura ciega ni aprueban utilidad, interpretación, causalidad, seguridad o estilo.",
        "",
        "## Registro ciego del dueño",
        "",
        "Por caso y por respuesta anónima: corrección — pendiente; utilidad — pendiente; redacción — pendiente; mejor respuesta elegida — pendiente. No se muestran el nombre del modelo ni el esfuerzo hasta cerrar la calificación. La escala y cualquier umbral quedan sujetos a decisión del dueño.",
        "",
        "## Pendientes antes de fijar",
        "",
        "- Aprobación o cambios del dueño a las 30 preguntas, el comportamiento esperado, los fallos críticos y la rúbrica.",
        "- Aprobar o editar el texto F2.1 vinculado arriba antes de fijar el prompt de comparación; `SYSTEM_INSTRUCTIONS` de producción sigue intacto.",
        "- Mantener N01, N04, N09–N10, N15–N19, N22–N23 y N29 bloqueados hasta integrar sus paquetes de datos o fuentes; N17 necesita índice aprobado de noticias y no puede puntuarse como respondible todavía.",
        "- N07 describe una tendencia y no atribuye causalidad. N21 suma el mismo periodo, segmento y denominador. N24 no puede anunciar un ganador antes de aclarar qué significa crecer.",
        "- N25 y N26 conservan 84.9%, su unidad porcentual y 2T26 del gold del turno inicial; la reformulación o traducción no vuelve a consultar ni cambia el contenido. La traducción se califica como inglés, no por la presencia aislada de una palabra inglesa.",
        "- Revisar selección determinista de 15 casos piloto y los cuatro candidatos `modelo@esfuerzo` en el planificador de presupuesto.",
        "",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render(), encoding="utf-8")
