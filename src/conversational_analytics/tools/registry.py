"""Deterministic read-only tool registry over the verified public snapshot."""

from __future__ import annotations

import copy
from typing import Any
from urllib.parse import urlparse

from src.conversational_analytics.data.snapshot import Snapshot
from src.conversational_analytics.semantic.context import validate_context
from src.conversational_analytics.semantic.plan import (
    ENTITY_IDS,
    PERIOD_RE,
    SEGMENTS,
    PlanValidationError,
    QueryPlan,
    validate_plan,
)

ALLOWED_HOSTS = {"sec.gov", "www.sec.gov", "gob.mx", "www.gob.mx", "github.com", "salvamalfa.github.io"}
TOOL_NAMES = (
    "get_data_catalog",
    "get_metric_definition",
    "query_metrics",
    "compare_metrics",
    "get_time_series",
    "get_source_references",
    "get_dashboard_context",
)


def _reference_label(hostname: str, path: str) -> str:
    """Name the publisher of an allowed reference by its host, never by default.

    Only AFAC pages under gob.mx are cited as AFAC; a SEC filing or the
    project repository keeps its own provenance.
    """
    if hostname == "salvamalfa.github.io":
        return "Datos publicados del dashboard"
    if hostname in {"gob.mx", "www.gob.mx"}:
        return "Fuente pública AFAC" if path.startswith("/afac/") else "Fuente pública del Gobierno de México"
    if hostname in {"sec.gov", "www.sec.gov"}:
        return "Documento público en SEC EDGAR"
    if hostname == "github.com":
        return "Repositorio público del proyecto"
    raise PlanValidationError("La referencia no pertenece a la lista pública permitida")


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required, "additionalProperties": False}


class ToolRegistry:
    def __init__(self, snapshot: Snapshot):
        self.snapshot = snapshot
        self._catalog = snapshot.catalog()
        self._metrics = {item["id"]: item for item in self._catalog["metrics"]["metrics"]}
        self._entities = {item["id"]: item for item in self._catalog["entities"]["entities"]}
        self._tool_specs = self._make_specs()

    def tool_specs(self) -> list[dict[str, Any]]:
        return copy.deepcopy(self._tool_specs)

    @staticmethod
    def _make_specs() -> list[dict[str, Any]]:
        qstr = {"type": "string", "minLength": 1}
        arr = {"type": "array", "items": qstr, "minItems": 1, "maxItems": 32}
        return [
            {
                "type": "function",
                "name": "get_data_catalog",
                "description": "Métricas, entidades y periodos disponibles en este snapshot público.",
                "parameters": _schema({}, []),
            },
            {
                "type": "function",
                "name": "get_metric_definition",
                "description": "Definición, unidad, cobertura y límites de una métrica permitida.",
                "parameters": _schema({"metric_id": qstr}, ["metric_id"]),
            },
            {
                "type": "function",
                "name": "query_metrics",
                "description": "Consulta determinista por métricas, entidades y periodos permitidos.",
                "parameters": _schema(
                    {
                        "metric_ids": arr,
                        "entity_ids": {"type": "array", "items": qstr, "minItems": 1, "maxItems": 4},
                        "periods": arr,
                        "segment": {"type": "string", "enum": sorted(SEGMENTS)},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    ["metric_ids", "entity_ids", "periods"],
                ),
            },
            {
                "type": "function",
                "name": "compare_metrics",
                "description": (
                    "Compara dos periodos y separa delta nativo, puntos porcentuales y cambio relativo."
                ),
                "parameters": _schema(
                    {
                        "metric_id": qstr,
                        "entity_id": qstr,
                        "periods": {"type": "array", "items": qstr, "minItems": 2, "maxItems": 2},
                        "segment": {"type": "string", "enum": sorted(SEGMENTS)},
                        "data_version": qstr,
                        "semantic_version": qstr,
                    },
                    ["metric_id", "entity_id", "periods"],
                ),
            },
            {
                "type": "function",
                "name": "get_time_series",
                "description": (
                    "Serie ordenada en periodos publicados. Si el intervalo excede el límite de "
                    "filas, devuelve los periodos más recientes e indica cuántos anteriores omitió."
                ),
                "parameters": _schema(
                    {
                        "metric_id": qstr,
                        "entity_id": qstr,
                        "start_period": qstr,
                        "end_period": qstr,
                        "segment": {"type": "string", "enum": sorted(SEGMENTS)},
                        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                    },
                    ["metric_id", "entity_id", "start_period", "end_period"],
                ),
            },
            {
                "type": "function",
                "name": "get_source_references",
                "description": "Referencias públicas permitidas para métricas consultables.",
                "parameters": _schema({"metric_ids": {"type": "array", "items": qstr, "maxItems": 10}}, []),
            },
            {
                "type": "function",
                "name": "get_dashboard_context",
                "description": (
                    "Devuelve únicamente contexto visible del dashboard después de validar "
                    "sus claves y valores."
                ),
                "parameters": _schema({}, []),
            },
        ]

    def catalog(self) -> dict[str, Any]:
        exec_doc = self.snapshot.payload("data/v1/executive.json")
        market = self.snapshot.payload("data/v1/market.json")
        try:
            flights = self.snapshot.payload("data/v1/flights/quarters.json")
        except ValueError:
            flights = {}
        periods = {
            "economic_quarters": sorted(
                {row["period_id"] for item in exec_doc["entities"].values() for row in item["records"]}
            ),
            "market_months": [row["period_id"] for row in market["months"]],
            "market_quarters": [row["period_id"] for row in market["quarters"]],
            "flight": copy.deepcopy(flights.get("available_periods", {})),
        }
        summary_fields = (
            "id",
            "label",
            "aliases",
            "unit",
            "grain",
            "dimensions",
            "period_grains",
            "coverage",
        )
        enabled_summary = [
            {field: copy.deepcopy(metric[field]) for field in summary_fields}
            for metric in self._catalog["metrics"]["metrics"]
        ]
        deferred_summary = [
            {
                field: copy.deepcopy(item[field])
                for field in ("id", "label", "unit", "grain", "coverage", "why_not_enabled")
            }
            for item in self._catalog["metrics"]["inventory_not_enabled"]
        ]
        return {
            "data_version": self.snapshot.version,
            "semantic_version": self.snapshot.semantic_version,
            "entities": copy.deepcopy(self._catalog["entities"]["entities"]),
            "metrics": enabled_summary,
            "inventory_not_enabled": deferred_summary,
            "periods": periods,
        }

    def _validate_context(self, context: dict[str, Any] | None) -> dict[str, Any]:
        return validate_context(context)

    def _validate_metric(self, metric_id: str) -> dict[str, Any]:
        if not isinstance(metric_id, str):
            raise PlanValidationError("metric_id debe ser un ID semántico")
        try:
            return self._metrics[metric_id]
        except KeyError as exc:
            raise PlanValidationError(f"Métrica desconocida: {metric_id}") from exc

    @staticmethod
    def _source_refs(
        metric: dict[str, Any], entity_id: str | None = None, period: str | None = None
    ) -> list[dict[str, str]]:
        refs = []
        for url in metric["references"]:
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
                raise PlanValidationError("La referencia no pertenece a la lista pública permitida")
            refs.append({"label": _reference_label(parsed.hostname, parsed.path), "url": url})
        # This filing supports only Aeroméxico's 2026Q2 report. Do not cite it
        # for peer carriers, other periods, or unrelated AFAC metrics.
        if (
            entity_id == "AEROMEXICO"
            and period == "2026Q2"
            and any("executive.json" in ref["url"] for ref in refs)
        ):
            refs.append(
                {
                    "label": "Reporte trimestral Aeroméxico 2026Q2",
                    "url": "https://www.sec.gov/Archives/edgar/data/1561861/000119312526302103/d112634dex991.htm",
                }
            )
        return refs

    def _fetch(self, metric_id: str, entity_id: str, period: str, segment: str | None) -> dict[str, Any]:
        metric = self._validate_metric(metric_id)
        if entity_id not in ENTITY_IDS:
            raise PlanValidationError(f"Entidad desconocida: {entity_id}")
        value = None
        quality = metric["quality"]
        period_label = period
        availability = "missing"
        if metric_id in {
            "company_passengers",
            "ask_km",
            "load_factor",
            "rask_cents_per_km",
            "cask_cents_per_km",
            "unit_margin_cents_per_km",
        }:
            doc = self.snapshot.payload("data/v1/executive.json")
            entity = doc["entities"].get(entity_id)
            record = (
                next((row for row in entity["records"] if row["period_id"] == period), None)
                if entity
                else None
            )
            field_map = {
                "company_passengers": "passengers",
                "ask_km": "ask_km",
                "load_factor": "load_factor",
                "rask_cents_per_km": "rask_cents_per_km",
                "cask_cents_per_km": "cask_cents_per_km",
                "unit_margin_cents_per_km": "unit_margin_cents_per_km",
            }
            if record:
                period_label = record["period_label"]
                value = record.get(field_map[metric_id])
                availability = "missing" if value is None else "available"
                if metric_id == "load_factor":
                    quality = f"{record['load_factor_basis']}: {quality}"
        elif metric_id in {
            "afac_passengers",
            "afac_market_passengers",
            "market_share",
            "market_share_change_qoq_pp",
            "market_share_change_yoy_pp",
        }:
            if not segment:
                raise PlanValidationError(f"{metric_id} requiere dimensión segment explícita")
            doc = self.snapshot.payload("data/v1/market.json")
            collection = "months" if "M" in period else "quarters"
            row = next((item for item in doc[collection] if item["period_id"] == period), None)
            if row:
                period_label = row["period_label"]
                segment_data = row["segments"].get(segment, {})
                entity_data = (
                    segment_data.get("industry")
                    if entity_id == "INDUSTRY"
                    else segment_data.get("carriers", {}).get(entity_id)
                )
                if metric_id == "afac_market_passengers":
                    value = segment_data.get("mexican_carriers_passengers")
                    availability = "missing" if value is None else "available"
                elif entity_data:
                    field = {
                        "afac_passengers": "passengers",
                        "market_share": "share",
                        "market_share_change_qoq_pp": "share_change_qoq_pp",
                        "market_share_change_yoy_pp": "share_change_yoy_pp",
                    }[metric_id]
                    value = entity_data.get(field)
                    availability = "missing" if value is None else "available"
        # All payload reads are projections over public `site/data/v1` fields.
        source_refs = self._source_refs(metric, entity_id, period)
        scale = metric["unit"].get("scale", 1)
        rounding = metric["unit"].get("rounding", 4)
        display_value = None if value is None else round(value * scale, rounding)
        return {
            "metric_id": metric_id,
            "entity_id": entity_id,
            "period": period,
            "period_label": period_label,
            **({"segment": segment} if segment else {}),
            "value": value,
            "unit": metric["unit"]["storage"],
            "display_value": display_value,
            "display_unit": metric["unit"]["display"],
            "display_scale": scale,
            "availability": availability,
            "quality": quality,
            "source_references": source_refs,
        }

    def _query(
        self,
        metric_ids: list[str],
        entity_ids: list[str],
        periods: list[str],
        segment: str | None,
        limit: int,
    ) -> dict[str, Any]:
        if segment is not None and segment not in SEGMENTS:
            raise PlanValidationError("segment inválido")
        plan = QueryPlan(
            metric_ids,
            entity_ids,
            periods,
            dimensions=["segment"] if segment else [],
            filters={"segment": segment} if segment else {},
            limit=limit,
        )
        clean = validate_plan(plan, self._catalog, self.snapshot.version, self.snapshot.semantic_version)
        for metric_id in clean.metric_ids:
            if metric_id == "afac_market_passengers" and any(
                entity_id != "MEXICAN_CARRIERS" for entity_id in clean.entity_ids
            ):
                raise PlanValidationError(
                    "afac_market_passengers solo admite la entidad sintética MEXICAN_CARRIERS"
                )
            if metric_id != "afac_market_passengers" and "MEXICAN_CARRIERS" in clean.entity_ids:
                raise PlanValidationError("MEXICAN_CARRIERS solo está disponible para afac_market_passengers")
            supports_segment = "segment" in self._metrics[metric_id]["dimensions"]
            if segment is None and supports_segment:
                raise PlanValidationError(f"{metric_id} requiere un segmento explícito")
            if segment is not None and not supports_segment:
                raise PlanValidationError(f"{metric_id} no admite dimensión segment")
            unsupported_periods = [
                period
                for period in clean.periods
                if ("month" if "M" in period else "quarter") not in self._metrics[metric_id]["period_grains"]
            ]
            if unsupported_periods:
                raise PlanValidationError(
                    f"Grano temporal no permitido para {metric_id}: {unsupported_periods[:2]}"
                )
        all_rows = [
            self._fetch(mid, ent, period, segment)
            for mid in clean.metric_ids
            for ent in clean.entity_ids
            for period in clean.periods
        ]
        rows = all_rows[: clean.limit]
        references = list(
            {(ref["url"], ref["label"]): ref for row in rows for ref in row["source_references"]}.values()
        )
        return {
            "data_version": self.snapshot.version,
            "semantic_version": self.snapshot.semantic_version,
            "rows": rows,
            "row_count": len(rows),
            "truncated": len(all_rows) > len(rows),
            "references": references,
        }

    def _compare(
        self, metric_id: str, entity_id: str, periods: list[str], segment: str | None
    ) -> dict[str, Any]:
        if not isinstance(periods, list) or len(periods) != 2 or not all(isinstance(p, str) for p in periods):
            raise PlanValidationError("compare_metrics requiere exactamente dos periodos")
        if periods[0] == periods[1]:
            raise PlanValidationError("compare_metrics requiere dos periodos distintos")
        if ("M" in periods[0]) != ("M" in periods[1]):
            raise PlanValidationError("compare_metrics no mezcla meses y trimestres")
        # YYYYQn and YYYYMmm sort chronologically as text; the earlier period is
        # always the base, whatever order the model used.
        periods = sorted(periods)
        data = self._query([metric_id], [entity_id], periods, segment, 2)
        previous, current = data["rows"]
        delta = (
            current["value"] - previous["value"]
            if previous["availability"] == current["availability"] == "available"
            else None
        )
        relative = None if delta is None or previous["value"] == 0 else delta / abs(previous["value"]) * 100
        metric = self._metrics[metric_id]
        pp_delta = None
        if delta is not None and metric["unit"].get("storage") == "fraction":
            pp_delta = delta * 100
        return {
            **data,
            "comparison": {
                "previous": previous,
                "current": current,
                "absolute_delta": delta,
                "delta_unit": metric["unit"]["storage"],
                "percentage_point_delta": pp_delta,
                "relative_change_percent": relative,
                "relative_change_available": relative is not None,
            },
        }

    def invoke(
        self, name: str, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if name not in TOOL_NAMES:
            raise PlanValidationError(f"Herramienta desconocida: {name}")
        if not isinstance(arguments, dict):
            raise PlanValidationError("arguments debe ser un objeto")
        clean_context = self._validate_context(context)
        if name == "get_dashboard_context":
            if arguments:
                raise PlanValidationError("get_dashboard_context no acepta argumentos")
            return {
                "data_version": self.snapshot.version,
                "semantic_version": self.snapshot.semantic_version,
                "context": clean_context,
                "context_available": bool(clean_context),
            }
        if name == "get_data_catalog":
            if arguments:
                raise PlanValidationError("get_data_catalog no acepta argumentos")
            return self.catalog()
        if name == "get_metric_definition":
            if set(arguments) != {"metric_id"}:
                raise PlanValidationError("Se requiere solo metric_id")
            metric = self._validate_metric(arguments["metric_id"])
            return {
                "data_version": self.snapshot.version,
                "semantic_version": self.snapshot.semantic_version,
                "metric": copy.deepcopy(metric),
                "source_references": self._source_refs(metric),
            }
        if name == "query_metrics":
            allowed = {"metric_ids", "entity_ids", "periods", "segment", "limit"}
            if set(arguments) - allowed or not {"metric_ids", "entity_ids", "periods"} <= set(arguments):
                raise PlanValidationError("Argumentos query_metrics no válidos")
            segment = arguments.get("segment")
            if segment is None and all(
                "segment" in self._metrics[mid]["dimensions"]
                for mid in arguments["metric_ids"]
                if mid in self._metrics
            ):
                segment = clean_context.get("filters", {}).get("segment")
            return self._query(
                arguments["metric_ids"],
                arguments["entity_ids"],
                arguments["periods"],
                segment,
                arguments.get("limit", 20),
            )
        if name == "compare_metrics":
            allowed = {"metric_id", "entity_id", "periods", "segment", "data_version", "semantic_version"}
            if set(arguments) - allowed or not {"metric_id", "entity_id", "periods"} <= set(arguments):
                raise PlanValidationError("Argumentos compare_metrics no válidos")
            if arguments.get("data_version") not in (None, self.snapshot.version) or arguments.get(
                "semantic_version"
            ) not in (None, self.snapshot.semantic_version):
                raise PlanValidationError("La conversación está fijada a una versión distinta")
            metric_id = arguments["metric_id"]
            segment = arguments.get("segment")
            if segment is None and "segment" in self._metrics.get(metric_id, {}).get("dimensions", []):
                segment = clean_context.get("filters", {}).get("segment")
            return self._compare(metric_id, arguments["entity_id"], arguments["periods"], segment)
        if name == "get_time_series":
            allowed = {"metric_id", "entity_id", "start_period", "end_period", "segment", "limit"}
            if set(arguments) - allowed or not {
                "metric_id",
                "entity_id",
                "start_period",
                "end_period",
            } <= set(arguments):
                raise PlanValidationError("Argumentos get_time_series no válidos")
            start, end = arguments["start_period"], arguments["end_period"]
            if (
                not isinstance(start, str)
                or not isinstance(end, str)
                or not PERIOD_RE.fullmatch(start)
                or not PERIOD_RE.fullmatch(end)
                or start > end
            ):
                raise PlanValidationError("Intervalo de periodos inválido")
            if start[4] != end[4]:
                raise PlanValidationError("No se pueden mezclar meses y trimestres")
            limit = arguments.get("limit", 20)
            if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 20:
                raise PlanValidationError("limit debe estar entre 1 y 20")
            metric_id = arguments["metric_id"]
            periods = self._periods(metric_id, arguments["entity_id"], start, end)
            if not periods:
                # Nothing published in range: query the bounds so they read as missing.
                periods = [start] if start == end else [start, end]
            # A long range keeps its most recent periods; truncating from the
            # end would silently drop the latest published data.
            selected = periods[-limit:]
            omitted = len(periods) - len(selected)
            segment = arguments.get("segment")
            if segment is None and "segment" in self._metrics[metric_id]["dimensions"]:
                segment = clean_context.get("filters", {}).get("segment")
            result = self._query([metric_id], [arguments["entity_id"]], selected, segment, limit)
            result["truncated"] = result["truncated"] or omitted > 0
            result["omitted_earlier_periods"] = omitted
            title = self._metrics[metric_id]["label"]
            if omitted:
                title = f"{title} (últimos {len(selected)} de {len(periods)} periodos)"
            result["chart"] = {
                "type": "line",
                "title": title,
                "x": [row["period_label"] for row in result["rows"]],
                "series": [
                    {
                        "name": self._entities[arguments["entity_id"]]["label"],
                        "y": [row["display_value"] for row in result["rows"]],
                    }
                ],
                "unit": self._metrics[metric_id]["unit"]["display"],
            }
            return result
        if name == "get_source_references":
            if set(arguments) - {"metric_ids"}:
                raise PlanValidationError("Argumentos get_source_references no válidos")
            metric_ids = arguments.get("metric_ids", list(self._metrics))
            if not isinstance(metric_ids, list) or len(metric_ids) > 10:
                raise PlanValidationError("metric_ids debe tener máximo 10 elementos")
            refs = []
            for metric_id in metric_ids:
                metric = self._validate_metric(metric_id)
                refs.extend({**ref, "metric_id": metric_id} for ref in self._source_refs(metric))
            # Deduplicate without changing order.
            unique = list({(ref["metric_id"], ref["url"]): ref for ref in refs}.values())
            return {
                "data_version": self.snapshot.version,
                "semantic_version": self.snapshot.semantic_version,
                "references": unique,
            }
        raise PlanValidationError("Herramienta no implementada")

    def execute(
        self, name: str, arguments: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Alias for provider adapters that use execute terminology."""
        return self.invoke(name, arguments, context)

    def _periods(self, metric_id: str, entity_id: str, start: str, end: str) -> list[str]:
        self._validate_metric(metric_id)
        if metric_id in {
            "company_passengers",
            "ask_km",
            "load_factor",
            "rask_cents_per_km",
            "cask_cents_per_km",
            "unit_margin_cents_per_km",
        }:
            doc = self.snapshot.payload("data/v1/executive.json")
            entity = doc["entities"].get(entity_id, {})
            periods = [row["period_id"] for row in entity.get("records", [])]
        else:
            key = "months" if "M" in start else "quarters"
            doc = self.snapshot.payload("data/v1/market.json")
            periods = [row["period_id"] for row in doc[key]]
        return sorted(period for period in periods if start <= period <= end)


__all__ = ["ToolRegistry", "TOOL_NAMES"]
