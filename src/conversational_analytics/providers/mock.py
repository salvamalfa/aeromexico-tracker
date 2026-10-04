"""Deterministic offline provider that grounds every answer in a real tool."""

from __future__ import annotations

import re
import threading
from typing import Any

from .base import InputAuthorizer, ProviderResult, ToolCall

ENTITY_ALIASES = {
    "AEROMEXICO": ("aeroméxico", "aeromexico", "grupo aeroméxico"),
    "VOLARIS": ("volaris",),
    "VIVA_AEROBUS": ("viva aerobus", "viva", "viva aéreo", "viva aerolínea"),
    "INDUSTRY": ("industria", "mercado total"),
    "MEXICAN_CARRIERS": (
        "pasajeros de todas las aerolíneas mexicanas",
        "todas las aerolíneas mexicanas",
        "todas las aerolineas mexicanas",
    ),
}


class MockProvider:
    """A narrow test/demo router, never a fabricated LLM response."""

    supports_input_authorization = True

    def __init__(self, snapshot: Any = None):
        self.snapshot = snapshot

    def run_turn(
        self,
        *,
        session_id: str | None,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
        tool_specs: list[dict[str, Any]],
        call_tool: ToolCall,
        emit,
        persist_session,
        cancel_event: threading.Event,
        authorize_input: InputAuthorizer | None = None,
    ) -> ProviderResult:
        if cancel_event.is_set():
            raise InterruptedError("cancelled")
        if authorize_input is not None:
            authorize_input()
        session_id = session_id or "mock:offline"
        last = next((m for m in reversed(messages) if m.get("role") == "user"), {})
        user_text = last.get("content", "")
        specs = {str(s.get("name")): s for s in tool_specs if s.get("name")}
        selected, clarification = self._select_tool(user_text, context, specs)
        if selected is None:
            return ProviderResult(
                clarification or "No pude resolver una consulta disponible.",
                provider_session_id=session_id,
                usage_complete=True,
            )
        name, args = selected
        call_id = f"mock-{last.get('turn_id', len(messages))}-{name}"
        emit("tool.started", {"call_id": call_id, "name": name})
        result = call_tool(str(last.get("turn_id", "")), call_id, name, args)
        if cancel_event.is_set():
            raise InterruptedError("cancelled")
        emit("tool.completed", {"call_id": call_id, "name": name, "result": result})
        content, references = self._format_result(name, result)
        emit("message.delta", {"text": content})
        return ProviderResult(
            content=content,
            references=references,
            chart=result.get("chart") if isinstance(result, dict) else None,
            input_tokens=max(1, len(user_text) // 4),
            output_tokens=max(1, len(content) // 4),
            provider_session_id=session_id,
            usage_complete=True,
        )

    def _select_tool(self, text: str, context: dict[str, Any], specs: dict[str, dict[str, Any]]):
        lowered = text.casefold()
        if "get_data_catalog" not in specs:
            return None, "No hay herramientas cargadas para este snapshot."
        if any(
            word in lowered for word in ("catálogo", "catalogo", "qué métricas", "que metricas", "disponible")
        ):
            return ("get_data_catalog", {}), None
        catalog = self.snapshot.catalog() if self.snapshot and hasattr(self.snapshot, "catalog") else {}
        metrics = catalog.get("metrics", {}).get("metrics", [])
        candidates = []
        for metric in metrics:
            aliases = [metric.get("label", ""), metric.get("id", ""), *metric.get("aliases", [])]
            matches = [str(alias) for alias in aliases if alias and str(alias).casefold() in lowered]
            if matches:
                candidates.append((max(matches, key=len), metric))
        if not candidates:
            return (
                None,
                "El modo simulado solo responde métricas nombradas en el catálogo. "
                "Indica una métrica, una entidad y un periodo publicado.",
            )
        candidates.sort(key=lambda entry: len(entry[0]), reverse=True)
        if len(candidates) > 1 and len(candidates[0][0]) == len(candidates[1][0]):
            return None, "La pregunta menciona más de una métrica posible. Indica cuál quieres consultar."
        metric = candidates[0][1]
        metric_id = metric["id"]
        is_source = any(word in lowered for word in ("fuente", "fuentes", "origen", "cita"))
        if is_source and "get_source_references" in specs:
            return ("get_source_references", {"metric_ids": [metric_id]}), None
        context_filters = context.get("filters", {}) if isinstance(context.get("filters"), dict) else {}
        segment = context_filters.get("segment")
        if "segment" in metric.get("dimensions", []) and not segment:
            segment = next((s for s in ("domestic", "international", "total") if s in lowered), None)
            if not segment:
                return None, "Esta métrica requiere indicar el segmento: total, domestic o international."
        ids = [
            entity for entity, aliases in ENTITY_ALIASES.items() if any(alias in lowered for alias in aliases)
        ]
        ids = list(dict.fromkeys(ids))
        contextual = context.get("entity")
        if not ids:
            if isinstance(contextual, list):
                ids = [e for e in contextual if e in ENTITY_ALIASES]
            elif isinstance(contextual, str) and contextual in ENTITY_ALIASES:
                ids = [contextual]
        if any(phrase in lowered for phrase in ("tres aerolíneas", "tres aerolineas", "las tres")):
            ids = ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"]
        ids = list(dict.fromkeys(ids))
        if not ids:
            return None, "Indica la aerolínea que quieres consultar."
        periods = re.findall(r"\b(?:20\d{2}Q[1-4]|20\d{2}M(?:0[1-9]|1[0-2]))\b", text)
        if not periods and isinstance(context.get("period"), str):
            periods = [context["period"]]
        if not periods:
            return None, "Indica el periodo exacto o selecciona un periodo en el dashboard."
        periods = list(dict.fromkeys(periods))
        is_series = any(
            word in lowered for word in ("serie", "historial", "evolución", "evolucion", "tendencia")
        )
        if is_series and "get_time_series" in specs:
            if len(periods) < 2:
                return None, "Para una serie indica un periodo inicial y final, por ejemplo 2024Q1 a 2026Q2."
            args = {
                "metric_id": metric_id,
                "entity_id": ids[0],
                "start_period": periods[0],
                "end_period": periods[-1],
            }
            if segment:
                args["segment"] = segment
            return ("get_time_series", args), None
        if len(periods) == 2 and len(ids) == 1 and "compare_metrics" in specs:
            args = {"metric_id": metric_id, "entity_id": ids[0], "periods": periods}
            if segment:
                args["segment"] = segment
            return ("compare_metrics", args), None
        if len(periods) > 1 and len(ids) > 1:
            return (
                None,
                "La comparación de varios periodos y aerolíneas en modo simulado no está habilitada; "
                "separa la consulta.",
            )
        args = {"metric_ids": [metric_id], "entity_ids": ids, "periods": periods}
        if segment:
            args["segment"] = segment
        return ("query_metrics", args), None

    def _format_result(self, tool_name: str, result: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        if tool_name == "get_data_catalog":
            return "Catálogo de consultas obtenido del snapshot público verificado.", []
        rows = result.get("rows") if isinstance(result, dict) else None
        refs = result.get("references", []) if isinstance(result, dict) else []
        if not refs and isinstance(rows, list):
            refs = list(
                {
                    (r.get("url"), r.get("label")): r
                    for row in rows
                    for r in row.get("source_references", [])
                }.values()
            )
        if not isinstance(rows, list):
            return (
                f"Resultado de la herramienta `{tool_name}` obtenido del snapshot público. "
                "Revisa las referencias y metadatos adjuntos.",
                refs,
            )
        lines = ["Consulta basada en datos del snapshot público verificado:"]
        catalog = self.snapshot.catalog() if self.snapshot and hasattr(self.snapshot, "catalog") else {}
        entities = catalog.get("entities", {}).get("entities", [])
        entity_labels = {item.get("id"): item.get("label") for item in entities if isinstance(item, dict)}
        for row in rows:
            if row.get("availability") != "available" or row.get("display_value") is None:
                value = "sin dato publicado"
            else:
                value = f"{row['display_value']} {row['display_unit']}"
            raw_quality = str(row.get("quality", "")).split(":", 1)[0].strip().casefold()
            quality = (
                "Reportado"
                if raw_quality.startswith(("reported", "reportado"))
                else "Calculado"
                if raw_quality.startswith(("calculated", "calculado"))
                else "Estimado"
                if raw_quality.startswith(("estimated", "estimado"))
                else "No disponible"
                if row.get("availability") != "available"
                else "Calidad indicada en la definición"
            )
            entity_name = entity_labels.get(row.get("entity_id"), row.get("entity_id", "Entidad"))
            lines.append(
                f"- {entity_name} · {row.get('period_label', row.get('period', ''))}: {value} ({quality})."
            )
        lines.append(
            "Modo simulado: se muestran resultados directos de herramientas deterministas; "
            "no hay respuesta generativa."
        )
        return "\n".join(lines), refs if isinstance(refs, list) else []

    def cancel(self, session_id: str) -> None:
        return None

    def delete(self, session_id: str) -> None:
        return None


__all__ = ["MockProvider"]
