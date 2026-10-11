"""Validated, same-turn presentation objects for conversational tool results."""

from __future__ import annotations

import hashlib
import logging
import math
import re
from typing import Any
from urllib.parse import urlsplit

LOG = logging.getLogger("conversational_analytics.presentation")
_MARKER = re.compile(r"\{\{(tabla|grafica):([A-Za-z0-9][A-Za-z0-9_.-]{0,95})\}\}")
_DISPLAY_ID = re.compile(r"^(tabla|grafica):[A-Za-z0-9][A-Za-z0-9_.-]{0,95}$")
_VALUE_KINDS = {
    "reported",
    "observed",
    "calculated",
    "inferred",
    "estimated",
    "scheduled",
    "mixed",
    "derived_sum_of_reported_quarters",
    "candidate_unapproved",
    "missing",
}
_SAFE_HOSTS = {"sec.gov", "www.sec.gov", "gob.mx", "www.gob.mx", "github.com", "salvamalfa.github.io"}


def _safe_sources(*candidates: Any) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate = [candidate]
        if not isinstance(candidate, list):
            continue
        for item in candidate:
            if not isinstance(item, dict):
                continue
            label, raw_url = item.get("label"), item.get("url")
            if not isinstance(label, str) or not label.strip() or not isinstance(raw_url, str):
                continue
            try:
                parsed = urlsplit(raw_url)
                if (
                    parsed.scheme != "https"
                    or parsed.username
                    or parsed.password
                    or parsed.query
                    or parsed.fragment
                    or parsed.hostname not in _SAFE_HOSTS
                ):
                    continue
                url = parsed.geturl()
            except ValueError:
                continue
            if url in seen:
                continue
            seen.add(url)
            sources.append({"label": label.strip()[:160], "url": url})
            if len(sources) == 12:
                return sources
    return sources


def _kind(rows: list[dict[str, Any]]) -> str:
    kinds = {
        row.get("value_kind")
        for row in rows
        if isinstance(row.get("value_kind"), str) and row.get("value_kind") in _VALUE_KINDS
    }
    return next(iter(kinds)) if len(kinds) == 1 else "mixed" if kinds else "reported"


def _described_sources(raw: Any, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    sources = _safe_sources(*raw) if isinstance(raw, list) else _safe_sources(raw)
    periods = list(
        dict.fromkeys(
            str(row.get("period_label") or row.get("period"))
            for row in rows
            if row.get("period_label") or row.get("period")
        )
    )
    period = ", ".join(periods[:3])
    templates = {
        "Fuente pública AFAC": "AFAC, estadística de transporte aéreo",
        "Documento público en SEC EDGAR": "SEC EDGAR, filing público",
        "Datos publicados del dashboard": "Airline Tracker, datos publicados del dashboard",
        "Fuente pública del Gobierno de México": "Gobierno de México, publicación pública",
    }
    if period:
        for source in sources:
            prefix = templates.get(source["label"])
            if prefix:
                source["label"] = f"{prefix}, {period}"[:160]
    return sources


def _validated_display(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or not isinstance(raw.get("display_id"), str):
        return None
    display_id = raw["display_id"]
    match = _DISPLAY_ID.fullmatch(display_id)
    kind = raw.get("kind")
    if not match or ((match.group(1) == "tabla") != (kind == "table")):
        return None
    title = raw.get("title")
    value_kind = raw.get("value_kind", "reported")
    if (
        not isinstance(title, str)
        or not title.strip()
        or not isinstance(value_kind, str)
        or value_kind not in _VALUE_KINDS
    ):
        return None
    result: dict[str, Any] = {
        "display_id": display_id,
        "kind": kind,
        "title": title.strip()[:200],
        "value_kind": value_kind,
        "sources": _safe_sources(raw.get("sources"), raw.get("source"), raw.get("source_references")),
    }
    if kind == "table":
        columns, rows = raw.get("columns"), raw.get("rows")
        if (
            not isinstance(columns, list)
            or not 1 <= len(columns) <= 12
            or not isinstance(rows, list)
            or len(rows) > 100
        ):
            return None
        clean_columns: list[dict[str, str]] = []
        keys: set[str] = set()
        for column in columns:
            if not isinstance(column, dict):
                return None
            key, label = column.get("key"), column.get("label")
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", key) or key in keys:
                return None
            if not isinstance(label, str) or not label.strip():
                return None
            keys.add(key)
            clean_columns.append(
                {
                    "key": key,
                    "label": label.strip()[:120],
                    **({"unit": column["unit"][:60]} if isinstance(column.get("unit"), str) else {}),
                }
            )
        clean_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                return None
            clean: dict[str, Any] = {}
            for key in keys:
                value = row.get(key)
                if value is None or isinstance(value, (str, bool)):
                    clean[key] = value
                elif isinstance(value, (int, float)) and not isinstance(value, bool):
                    try:
                        finite = math.isfinite(value)
                    except (OverflowError, TypeError, ValueError):
                        finite = False
                    if not finite:
                        return None
                    clean[key] = value
                else:
                    return None
            clean_rows.append(clean)
        result.update(columns=clean_columns, rows=clean_rows)
    elif kind == "chart":
        chart = raw.get("chart", raw)
        if not isinstance(chart, dict) or chart.get("type") not in {"line", "bar"}:
            return None
        x, series = chart.get("x"), chart.get("series")
        if (
            not isinstance(x, list)
            or not 1 <= len(x) <= 100
            or not isinstance(series, list)
            or not 1 <= len(series) <= 8
        ):
            return None
        if not all(
            isinstance(point, str)
            or (isinstance(point, (int, float)) and not isinstance(point, bool) and math.isfinite(point))
            for point in x
        ):
            return None
        clean_series = []
        for item in series:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                return None
            values = item.get("y")
            if (
                not isinstance(values, list)
                or len(values) != len(x)
                or not all(
                    value is None
                    or (
                        isinstance(value, (int, float))
                        and not isinstance(value, bool)
                        and math.isfinite(value)
                    )
                    for value in values
                )
            ):
                return None
            clean_series.append({"name": item["name"][:120], "y": values})
        result["chart"] = {
            "type": chart["type"],
            "title": result["title"],
            "x": x,
            "series": clean_series,
            **({"unit": chart["unit"][:60]} if isinstance(chart.get("unit"), str) else {}),
        }
    else:
        return None
    return result


def _build_query_display(
    result: dict[str, Any], tool_name: str, call_id: str, catalog: dict[str, Any] | None = None
) -> dict[str, Any] | None:
    rows = result.get("rows")
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        return None
    chart = result.get("chart")
    short_id = hashlib.sha256(call_id.encode("utf-8", errors="replace")).hexdigest()[:12]
    if tool_name == "get_time_series" and isinstance(chart, dict):
        series = chart.get("series")
        if not isinstance(series, list) or not series:
            return None
        # Preserve raw validated values; display_value is rounded for prose.
        raw_values = [row.get("value") for row in rows]
        raw_unit = rows[0].get("unit") or chart.get("unit")
        display_chart = {**chart, "unit": raw_unit, "series": [{**series[0], "y": raw_values}]}
        return {
            "display_id": f"grafica:serie_{short_id}",
            "kind": "chart",
            "title": chart.get("title") or "Serie temporal",
            "chart": display_chart,
            "value_kind": _kind(rows),
            "sources": _described_sources([result.get("references"), result.get("source_references")], rows),
        }
    columns = [
        {"key": "entity", "label": "Aerolínea"},
        {"key": "period", "label": "Periodo"},
    ]
    metric_ids = {row.get("metric_id") for row in rows}
    if len(metric_ids) > 1:
        columns.append({"key": "metric", "label": "Métrica"})
    units = {row.get("unit") for row in rows}
    unit = next(iter(units)) if len(units) == 1 and isinstance(next(iter(units)), str) else None
    value_column = {"key": "value", "label": "Valor"}
    if unit:
        value_column["unit"] = unit
    columns.append(value_column)
    catalog = catalog or {}
    entity_catalog = catalog.get("entities", [])
    metric_catalog = catalog.get("metrics", [])
    if isinstance(entity_catalog, dict):
        entity_catalog = entity_catalog.get("entities", [])
    if isinstance(metric_catalog, dict):
        metric_catalog = metric_catalog.get("metrics", [])
    entities = {item.get("id"): item.get("label") for item in entity_catalog if isinstance(item, dict)}
    metrics = {item.get("id"): item.get("label") for item in metric_catalog if isinstance(item, dict)}
    entities.update(
        {row.get("entity_id"): row.get("entity_label") for row in rows if row.get("entity_label")}
    )
    metrics.update({row.get("metric_id"): row.get("metric_label") for row in rows if row.get("metric_label")})
    display_rows = []
    for row in rows:
        if "value" not in row:
            continue
        item = {
            "entity": str(entities.get(row.get("entity_id"), row.get("entity_id") or "")),
            "period": str(row.get("period_label") or row.get("period") or ""),
            "value": row["value"],
        }
        if len(metric_ids) > 1:
            item["metric"] = str(metrics.get(row.get("metric_id"), row.get("metric_id") or ""))
        display_rows.append(item)
    if not display_rows:
        return None
    title = next(iter(metrics.values())) if len(metrics) == 1 else "Resultados de la consulta"
    return {
        "display_id": f"tabla:consulta_{short_id}",
        "kind": "table",
        "title": str(title),
        "columns": columns,
        "rows": display_rows,
        "value_kind": _kind(rows),
        "sources": _described_sources([result.get("references"), result.get("source_references")], rows),
    }


class DisplayRegistry:
    """Contains only validated displays produced by this provider turn."""

    def __init__(self, catalog: dict[str, Any] | None = None) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._catalog = catalog or {}

    def add(self, raw: Any) -> dict[str, Any] | None:
        display = _validated_display(raw)
        if display is None:
            return None
        existing = self._items.get(display["display_id"])
        if existing is not None and existing != display:
            LOG.info("Discarded conflicting presentation object")
            return None
        self._items[display["display_id"]] = display
        return display

    def add_tool_result(self, result: dict[str, Any], tool_name: str, call_id: str) -> dict[str, Any]:
        candidates = result.get("displays")
        if not isinstance(candidates, list):
            candidates = [result.get("display")] if result.get("display") is not None else []
        accepted = [display for raw in candidates if (display := self.add(raw)) is not None]
        if not accepted and tool_name in {
            "query_metrics",
            "compare_metrics",
            "get_time_series",
            "query_business_metrics",
        }:
            raw = _build_query_display(result, tool_name, call_id, self._catalog)
            if raw is not None and (display := self.add(raw)) is not None:
                accepted.append(display)
        if accepted:
            result = {**result, "displays": accepted}
            if len(accepted) == 1:
                result["display"] = accepted[0]
        return result

    def finalize(
        self, content: str, references: Any = None
    ) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
        selected: list[dict[str, Any]] = []
        seen: set[str] = set()

        def replace(match: re.Match[str]) -> str:
            display_id = f"{match.group(1)}:{match.group(2)}"
            display = self._items.get(display_id)
            expected_kind = "table" if match.group(1) == "tabla" else "chart"
            if display is None or display["kind"] != expected_kind:
                LOG.info("Removed unknown or mismatched presentation reference")
                return ""
            if display_id not in seen:
                selected.append(display)
                seen.add(display_id)
            return match.group(0)

        sanitized = _MARKER.sub(replace, content)
        # Strip malformed presentation syntax too; it must never become a user-visible error.
        sanitized = re.sub(
            r"\{\{(?:tabla|grafica):(?![A-Za-z0-9][A-Za-z0-9_.-]{0,95}\}\})[^{}\n]{0,120}\}\}?",
            "",
            sanitized,
        )
        ref_candidates = [references]
        ref_candidates.extend(display.get("sources") for display in selected)
        unique_sources = _safe_sources(*ref_candidates)
        shown_urls = {source["url"] for display in selected for source in display.get("sources", [])}
        return sanitized, selected, [source for source in unique_sources if source["url"] not in shown_urls]


def make_displays(
    result: dict[str, Any], tool_name: str, call_id: str, catalog: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Convenience adapter for direct integrations and tests."""
    return DisplayRegistry(catalog).add_tool_result(dict(result), tool_name, call_id)


__all__ = ["DisplayRegistry", "make_displays"]
