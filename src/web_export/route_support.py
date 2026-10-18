"""Pure route metric support checks shared by exporters and the chat runtime."""

from __future__ import annotations

from collections import defaultdict
import math


def metric_support(network, route, metric):
    """Return (detailed, operator/direction scope, incompleteness reason).

    Old signed payloads without either detail keep their explicit legacy policy.
    Flight components establish departures only, never passenger/seat coverage.
    """
    if metric == "departures":
        if "flight_components" not in route:
            return False, set(), None
        components = route["flight_components"]
        if not components:
            return (
                True,
                set(),
                "No hay celdas fechadas de vuelos para esta ruta; un faltante no equivale a cero",
            )
        items = [c for c in components if c.get("kind") != "scheduled"] or components
    else:
        items = route.get("monthly")
    if not items:
        return False, set(), None
    expected = set(network.get("expected_months") or [])
    if not expected:
        return True, set(), "No se declara el calendario esperado de la métrica de esta ruta"
    known = defaultdict(set)
    seen = set()
    for item in items:
        scope = tuple(item.get(k) for k in ("carrier_key", "origin_iata", "destination_iata"))
        if not all(isinstance(k, str) and k for k in scope):
            return True, set(), "El detalle mensual de la métrica no identifica operador y sentido"
        identity = (*scope, item.get("period_id"))
        if identity in seen:
            return True, set(), "El detalle mensual duplica una celda de operador y sentido"
        seen.add(identity)
        known[scope]  # Unknown values still declare a required operator/direction.
        value = item.get(metric)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            known[scope].add(item.get("period_id"))
    if any(months != expected for months in known.values()):
        return (
            True,
            set(known),
            (
                "La cobertura mensual de la métrica de esta ruta es parcial por operador o sentido; "
                "no se completan faltantes con cero"
            ),
        )
    return True, set(known), None


def route_metric_support_reason(current, previous, route, previous_route, metric):
    current_detail, current_scope, current_error = metric_support(current, route, metric)
    previous_detail, previous_scope, previous_error = metric_support(previous, previous_route, metric)
    if current_error or previous_error:
        return current_error or previous_error
    if current_detail != previous_detail:
        return "El detalle mensual de la métrica de esta ruta no está disponible en ambos periodos"
    if current_detail and current_scope != previous_scope:
        return "Cambió el conjunto de operadores o sentidos de la métrica de la ruta"
    return None


def comparable_previous_departures(network, current_cells, previous_cells, previous_value):
    """Keep a native year-ago count only when the exact dated scopes reconcile.

    The map's `previous` is the same calendar month/quarter one year earlier.
    No estimate is created for that period and no missing cell becomes zero.
    """
    if not isinstance(previous_value, (int, float)) or not math.isfinite(previous_value):
        return None
    months = network.get("expected_months") or []
    if len(months) not in (1, 3):
        return None
    try:
        previous_months = [f"{int(month[:4]) - 1}{month[4:]}" for month in months]
    except (ValueError, TypeError):
        return None
    current = {"flight_components": current_cells}
    previous = {"flight_components": previous_cells or []}
    prior_network = {"expected_months": previous_months}
    if route_metric_support_reason(network, prior_network, current, previous, "departures"):
        return None

    def active(items):
        return [c for c in items if c["kind"] != "scheduled"] or items

    current_active, previous_active = active(current_cells), active(previous_cells or [])
    keys = ("carrier_key", "origin_iata", "destination_iata", "kind", "source_label")
    if {tuple(c[k] for k in keys) for c in current_active} != {
        tuple(c[k] for k in keys) for c in previous_active
    }:
        return None
    previous_sum = sum(c["departures"] for c in previous_active)
    return previous_value if math.isclose(previous_sum, previous_value, rel_tol=0, abs_tol=1e-9) else None
