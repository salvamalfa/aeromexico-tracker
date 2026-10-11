"""Render the F2.9 coverage matrix from the owner-approved frozen business fixture."""

from __future__ import annotations

import hashlib
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


def _case_sources(case: dict[str, Any]) -> tuple[list[str], list[str]]:
    expected = case.get("expected", {})
    plan = expected.get("plan", {})
    metric_ids = list(plan.get("metric_ids", []))
    references = []
    for row in expected.get("rows", []):
        references.extend(row.get("source_references", []))
    references.extend(expected.get("source_references", []))
    unique = []
    seen = set()
    for reference in references:
        url = reference.get("url")
        label = reference.get("label", "")
        if isinstance(url, str) and (label, url) not in seen:
            seen.add((label, url))
            unique.append(f"{label}: {url}")
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
        "# F2.9 · Matriz de cobertura para la campaña final",
        "",
        "Generada desde `tests/fixtures/chat_evals/business_proposed.json` sin modificarlo. "
        f"SHA-256 canónico del fixture: `{fixture_hash}`. Las preguntas, estados, acciones, "
        "dependencias, IDs de métricas, referencias y fallos críticos se copian del fixture aprobado; "
        "esta tabla no redefine su Gold.",
        "",
        "La campaña propuesta usa Sol low, una sola repetición, 30 casos business y 34 turnos de usuario. "
        "No agrega casos de prompt injection. Es una proyección offline; requiere revalidar Gold/snapshot "
        "y aprobar un presupuesto nuevo antes de cualquier llamada.",
        "",
        "| ID | Pregunta(s) congelada(s) | Acción esperada congelada | Métricas / fuentes en Gold | "
        "Dependencias y fallos críticos |",
        "|---|---|---|---|---|",
    ]
    for case in cases:
        case_id = case["id"]
        expected = case.get("expected", {})
        turns = case.get("turns", [case.get("question", "")])
        questions = "<br>".join(f"{index}. {_cell(question)}" for index, question in enumerate(turns, 1))
        action = f"`{expected.get('status', 'missing')}` · `{expected.get('behavior', 'missing')}`"
        metric_ids, references = _case_sources(case)
        plan = expected.get("plan", {})
        details = []
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
            "La proyección actual de US$6.58 corresponde a una repetición y margen de 35%, no a una reserva "
            "aprobada ni a un hard cap; debe recalcularse tras integrar dependencias.",
            "",
            "El preflight `scripts/chat/prepare_final_campaign.py` valida el perfil, fixture, catálogo de "
            "precios y evidencia de uso; el perfil rechaza repeticiones distintas de una.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    OUTPUT.write_text(render_matrix(fixture), encoding="utf-8")


if __name__ == "__main__":
    main()
