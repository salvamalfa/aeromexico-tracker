"""Render the F2.9 coverage matrix from the owner-approved frozen business fixture."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/chat_evals/business_proposed.json"
OUTPUT = ROOT / "docs/chat/revision-fase-2/F2.9-matriz-cobertura-final.md"
EXPECTED_CASE_HASH = "30fc0acfc5d9fee1ffffd3624209712dd8160806dae4d904c4310a8f53537640"

CASE_GUIDANCE = {
    "N20": (
        "Rechazar una cifra para 2027 y no inventar un pronóstico; ofrecer revisar el histórico, "
        "citando cifras solo cuando haya evidencia aprobada."
    ),
    "N22": (
        "Definir qué mide combustible en costos; distinguir gasto total/participación del combustible "
        "del componente CASK. No renombrar un componente de CASK como gasto total; si faltan valores "
        "financieros aprobados, declarar el límite."
    ),
    "N23": (
        "Comparar pasajeros de Viva y Volaris en 1S26 (1T26 + 2T26), con igual fuente y periodos; "
        "no convertir la pregunta en total anual."
    ),
}


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").strip()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _turn_expectations(case: dict[str, Any]) -> list[dict[str, Any]]:
    expected = case.get("expected", {})
    turns = expected.get("turns")
    if not isinstance(turns, list):
        turns = [expected]
    questions = case.get("turns", [case.get("question", "")])
    rendered = []
    for index, turn in enumerate(turns):
        if not isinstance(turn, dict):
            continue
        plan = turn.get("plan", {})
        references = []
        rows = turn.get("rows", [])
        for row in rows:
            references.extend(row.get("source_references", []))
        references.extend(turn.get("source_references", []))
        unique = []
        seen = set()
        for reference in references:
            url = reference.get("url")
            label = reference.get("label", "")
            if isinstance(url, str) and (label, url) not in seen:
                seen.add((label, url))
                unique.append(f"{label}: {url}")
        facts = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            if "value" in row:
                facts.append(
                    f"{row.get('metric_id')}={row.get('value')} {row.get('unit')} "
                    f"({row.get('period_label', row.get('period'))})"
                )
        constraints = []
        if turn.get("response_behavior"):
            constraints.append(f"comportamiento: {turn['response_behavior']}")
        if turn.get("response_terms"):
            constraints.append(f"términos: {', '.join(turn['response_terms'])}")
        if turn.get("preserve_response_terms"):
            constraints.append(f"preservar: {', '.join(turn['preserve_response_terms'])}")
        if turn.get("preserve_any_terms"):
            constraints.append(f"preservar alternativa: {_json(turn['preserve_any_terms'])}")
        if turn.get("forbid_numeric_claims") is True:
            constraints.append("prohibir afirmaciones numéricas")
        if turn.get("must_not_contain"):
            constraints.append(f"no afirmar: {_json(turn['must_not_contain'])}")
        failures = turn.get("critical_failures", [])
        if failures:
            constraints.append(f"fallos críticos: {_json(failures)}")
        prompt = questions[index] if index < len(questions) else f"turno {index + 1}"
        rendered.append(
            {
                "index": index + 1,
                "question": prompt,
                "status": turn.get("status", "missing"),
                "plan": plan,
                "metric_ids": list(plan.get("metric_ids", [])),
                "entities": list(plan.get("entity_ids", [])),
                "periods": list(plan.get("periods", [])),
                "facts": facts,
                "references": unique,
                "constraints": constraints,
            }
        )
    return rendered


def _case_sources(case: dict[str, Any]) -> tuple[list[str], list[str]]:
    references = [reference for turn in _turn_expectations(case) for reference in turn["references"]]
    metric_ids = list(
        dict.fromkeys(metric for turn in _turn_expectations(case) for metric in turn["metric_ids"])
    )
    unique = []
    seen = set()
    for reference in references:
        if reference not in seen:
            seen.add(reference)
            unique.append(reference)
    return metric_ids, unique


def render_matrix(fixture: dict[str, Any]) -> str:
    fixture_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    if fixture_hash != EXPECTED_CASE_HASH:
        raise ValueError("El fixture de negocio cambió; requiere revisión y nuevo pin")
    if fixture != json.loads(FIXTURE.read_text(encoding="utf-8")):
        raise ValueError("La matriz debe renderizarse desde el fixture congelado en disco")
    cases = fixture["cases"]
    if fixture.get("status") != "OWNER_APPROVED" or len(cases) != 30:
        raise ValueError("La matriz requiere los 30 casos business OWNER_APPROVED congelados")

    lines = [
        "# F2.9 · Matriz de cobertura de la etapa 3 parcial de negocio",
        "",
        "Generada desde `tests/fixtures/chat_evals/business_proposed.json` sin modificarlo. "
        f"SHA-256 canónico del fixture: `{fixture_hash}`. Las preguntas, estados, acciones, "
        "dependencias, IDs de métricas, referencias y fallos críticos se copian del fixture aprobado; "
        "esta tabla no redefine su Gold.",
        "",
        "El preflight parcial usa Sol low, una sola repetición, 30 casos business y 34 turnos de usuario. "
        "Excluye la cohorte safety y no agrega casos de prompt injection, de acuerdo con la instrucción "
        "explícita del dueño; no representa cobertura ni validación completa de seguridad. Es una "
        "proyección offline; requiere revalidar Gold/snapshot y aprobar un presupuesto nuevo antes de "
        "cualquier llamada.",
        "",
        "| ID | Pregunta(s) congelada(s) | Acción esperada congelada | Métricas / fuentes en Gold | "
        "Dependencias y fallos críticos |",
        "|---|---|---|---|---|",
    ]
    for case in cases:
        case_id = case["id"]
        expected = case.get("expected", {})
        turns = case.get("turns", [case.get("question", "")])
        turn_expectations = _turn_expectations(case)
        questions = "<br>".join(
            f"{index}. {_cell(question)}" for index, question in enumerate(turns, 1)
        )
        if expected.get("status") == "multi_turn":
            action = f"`multi_turn` · `{expected.get('behavior', 'missing')}`"
            action += "<br>" + "<br>".join(
                f"turno {turn['index']}: `{turn['status']}`"
                + (f" · {_cell('; '.join(turn['constraints']))}" if turn["constraints"] else "")
                for turn in turn_expectations
            )
        else:
            action = f"`{expected.get('status', 'missing')}` · `{expected.get('behavior', 'missing')}`"
        metric_ids, references = _case_sources(case)
        plan = expected.get("plan", {})
        details = []
        for turn in turn_expectations:
            if len(turn_expectations) > 1:
                details.append(f"turno {turn['index']} Gold: `{turn['status']}`")
            if turn["metric_ids"]:
                details.append(f"métricas turno {turn['index']}: `{', '.join(turn['metric_ids'])}`")
            if turn["entities"]:
                details.append(f"entidades turno {turn['index']}: `{', '.join(turn['entities'])}`")
            if turn["periods"]:
                details.append(f"periodos turno {turn['index']}: `{', '.join(turn['periods'])}`")
            details.extend(f"Gold turno {turn['index']}: `{_cell(fact)}`" for fact in turn["facts"])
            details.extend(_cell(reference) for reference in turn["references"])
            details.extend(
                f"restricción turno {turn['index']}: {_cell(constraint)}"
                for constraint in turn["constraints"]
            )
        if metric_ids:
            details.append(f"metric IDs: `{', '.join(metric_ids)}`")
        if plan.get("entity_ids"):
            details.append(f"entidades: `{', '.join(plan['entity_ids'])}`")
        if plan.get("periods"):
            details.append(f"periodos: `{', '.join(plan['periods'])}`")
        if plan.get("dimensions") or plan.get("filters"):
            filter_data = {
                "dimensions": plan.get("dimensions", []),
                "filters": plan.get("filters", {}),
            }
            details.append(f"filtros: `{_json(filter_data)}`")
        if references:
            details.extend(_cell(reference) for reference in references)
        if not details:
            details.append("sin fuente/plan Gold numérico fijado")
        evidence = "<br>".join(details)
        dependencies = ", ".join(
            f"`{dependency}`" for dependency in case.get("dependencies", [])
        ) or "ninguna"
        failures = "; ".join(
            f"`{failure}`" for failure in case.get("critical_failures", [])
        ) or "ninguno fijado"
        gold_state = case.get("gold_state", "missing")
        gate = f"dependencias: {dependencies}; Gold: `{gold_state}`; críticos: {failures}"
        if case_id in CASE_GUIDANCE:
            gate += f"; guía: {CASE_GUIDANCE[case_id]}"
        lines.append(f"| {case_id} | {questions} | {action} | {evidence} | {_cell(gate)} |")

    lines.extend(["", "## Contrato Gold completo por caso", ""])
    lines.append(
        "Los bloques siguientes conservan íntegro `expected` del fixture congelado, incluidos "
        "Gold derivado, fórmulas, denominadores, fuentes, restricciones y expectativas por turno."
    )
    lines.append("")
    for case in cases:
        expected_json = html.escape(_json(case.get("expected", {})))
        lines.extend(
            [
                "<details>",
                f"<summary>{case['id']} · contrato Gold congelado</summary>",
                "",
                f"<pre>{expected_json}</pre>",
                "",
                "</details>",
                "",
            ]
        )

    lines.extend(
        [
            "",
            "## Puertas de integración",
            "",
            "| Paquete | Interfaz a integrar | Estado necesario antes de la campaña |",
            "|---|---|---|",
            "| F2.3 | `query_business_metrics`, `get_business_metric_definition`, "
            "`aggregate_quarters` | Totales financieros permanecen gate-closed hasta recibo/aprobación "
            "del dueño y snapshot publicado. |",
            "| F2.4 | `query_routes`, `find_shared_routes` | Integrar dispatch y validar "
            "cobertura/periodos; etiquetar estimaciones. |",
            "| F2.5–F2.6 | `search_reports`, `search_news` | Índices con recibo del dueño, "
            "referencias rastreables y citas/páginas; sin habilitar candidatos no aprobados. |",
            "| F2.7 | `config/chat/prompt_rules/f2_7_attributed_causes.v1.md` | Regla en "
            "prompt efectivo: atribución explícita citada; simultaneidad no es causa. |",
            "| F2.8 | `src/conversational_analytics/presentation.py` y renderer "
            "`web/src/views/chat/` | Mostrar solo payload validado por referencia, persistido, "
            "coincidente con filas de herramienta. |",
            "",
            "Los paquetes F2.3–F2.8 siguen requiriendo revisión y enlace efectivo al registry/worker; "
            "la presencia de módulos aislados no abre las puertas. Todo Gold dependiente debe generarse "
            "contra snapshot y versión semántica fijados después de integrar esos paquetes. Las fuentes "
            "financieras candidatas de F2.3 permanecen cerradas hasta recibo/aprobación del dueño. "
            "La cotización offline vigente de etapa 3 es US$7.05–7.21 con margen de 35%; propone "
            "US$8 disponibles si el saldo confirmado fuera cero. No es una reserva aprobada ni un hard cap, "
            "y el saldo de cuenta es desconocido. El detalle y los hashes están en la "
            "[cotización actual](F2.9-etapa-3-presupuesto-actual.md).",
            "",
            "Estado del plan (2026-10-12): la etapa 3 está propuesta solo como campaña parcial de negocio. "
            "El perfil `config/chat/f2_9_business_stage3_partial.json` limita el alcance a los 30 casos "
            "business y una repetición; safety y prompt injection quedan fuera, sin presentarse como "
            "validados. El preflight `scripts/chat/prepare_final_campaign.py` compara hashes y totales "
            "de tokens de uso medido con el artefacto público de cierre etapa 2 fijado, además de validar "
            "fixture y catálogo. Persisten gates de integración, Gold/snapshot y presupuesto; no está "
            "autorizada ninguna llamada. Detalles del preflight de cobertura y sus pruebas en "
            "[`bitácora de preflight`](../../etapas/chat-f2-9-preflight-integridad-20261011.md).",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    OUTPUT.write_text(render_matrix(fixture), encoding="utf-8")


if __name__ == "__main__":
    main()
