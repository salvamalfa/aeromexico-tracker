"""Render the standalone Vuelos review page as self-contained HTML."""

from __future__ import annotations

from html import escape
import json
from pathlib import Path
import re
from typing import Any

from plotly.offline import get_plotlyjs

from src.config import PATHS


CSS_PATH = PATHS.root / "src" / "dashboard" / "assets" / "flights.css"
JS_PATH = PATHS.root / "src" / "dashboard" / "assets" / "flights.js"
DEFAULT_OUTPUT = PATHS.root / "prototypes" / "vuelos" / "vuelos_revision.html"


def _safe_json(payload: dict[str, Any]) -> str:
    return (
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _kpi_card(key: str, label: str, description: str, accent: str) -> str:
    return f"""
      <article class="flight-kpi" data-accent="{escape(accent, quote=True)}">
        <span class="info" title="{escape(description, quote=True)}" aria-label="{escape(description, quote=True)}">i</span>
        <p class="kpi-label">{escape(label)}</p>
        <p class="kpi-value" id="flight-kpi-{escape(key, quote=True)}">—</p>
        <div class="kpi-deltas">
          <span>vs. trimestre anterior <strong id="flight-kpi-{escape(key, quote=True)}-qoq">—</strong></span>
          <span>vs. año anterior <strong id="flight-kpi-{escape(key, quote=True)}-yoy">—</strong></span>
        </div>
      </article>
    """


def render_flights_panel(payload: dict[str, Any]) -> str:
    """Return the three approved Vuelos blocks for the main dashboard."""

    if payload.get("schema_version") != "flight_dashboard_payload_v1":
        raise ValueError("Unsupported flight dashboard payload")
    return f"""
    <div class="flights-shell flights-integrated" data-testid="flights-dashboard-root">
      <section class="flight-kpi-grid" aria-label="Capacidad y demanda trimestral">
        {_kpi_card('passengers', 'Pasajeros', 'Pasajeros transportados por Grupo Aeroméxico durante el trimestre.', 'blue')}
        {_kpi_card('asm_miles', 'ASM', 'Asientos disponibles multiplicados por millas voladas.', 'gold')}
        {_kpi_card('rpm_miles', 'RPM', 'Pasajeros transportados multiplicados por millas voladas.', 'violet')}
        {_kpi_card('load_factor', 'Ocupación', 'RPM dividido entre ASM; porcentaje de capacidad utilizada.', 'amber')}
      </section>
      <section aria-labelledby="network-title">
        <div class="section-heading network-heading">
          <div><p class="section-kicker">Red de vuelos</p><h2 id="network-title">Rutas nacionales</h2><p class="network-scope-note" id="network-scope-note"></p></div>
        </div>
        <div class="network-mode-switch" role="radiogroup" aria-label="Tipo de red">
          <button type="button" id="network-mode-domestic" role="radio" aria-checked="true" aria-pressed="true">Nacional</button>
          <button type="button" id="network-mode-international" role="radio" aria-checked="false" aria-pressed="false">Internacional</button>
          <div class="network-region-switch" id="network-region-switch" role="group" aria-label="Región internacional" hidden></div>
        </div>
        <div class="network-month-switch" id="network-month-switch" role="group" aria-label="Meses nacionales (selección múltiple)"></div>
        <div class="network-volume" id="network-volume" hidden></div>
        <div class="network-layout">
          <article class="panel flow-map-panel" id="map-panel">
            <div class="map-detail-layout">
              <div class="map-canvas-column">
                <div class="chart flow-map" id="route-flow-map" role="img" aria-label="Mapa de rutas por fuente y tipo de observación"></div>
              </div>
              <aside class="airport-tooltip" id="airport-tooltip" role="region" aria-label="Detalle de rutas por aeropuerto"></aside>
            </div>
          </article>
        </div>
      </section>

      <section aria-labelledby="mix-title">
        <div class="section-heading">
          <div><p class="section-kicker">Capacidad y demanda</p><h2 id="mix-title">Mezcla nacional e internacional</h2></div>
          <p class="source-inline">AFAC Gold · serie mensual consolidada</p>
        </div>
        <article class="panel chart-panel">
          <div class="panel-heading chart-heading">
            <div><p class="panel-title">Pasajeros y contribución por segmento</p></div>
            <label class="chart-range-control" for="passenger-period">Periodo
              <select id="passenger-period">
                <option value="quarter" selected>Trimestral</option>
                <option value="month">Mensual</option>
              </select>
            </label>
          </div>
          <div class="chart chart-mix" id="mix-chart" role="img" aria-label="Pasajeros por periodo: barras apiladas nacional e internacional y línea del total calculado"></div>
        </article>
      </section>
    </div>
    """


def integration_flight_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only data consumed by the three blocks included in the main dashboard."""

    if payload.get("schema_version") != "flight_dashboard_payload_v1":
        raise ValueError("Unsupported flight dashboard payload")
    endpoint_keys = ("iata", "city", "name", "lat", "lon")
    metric_keys = ("passengers", "seats", "departures", "load_factor")

    def endpoint(value: dict[str, Any]) -> dict[str, Any]:
        return {key: value[key] for key in endpoint_keys}

    def compact_number(value: Any, digits: int = 1) -> Any:
        return round(float(value), digits) if value is not None else None

    def monthly_item(item: dict[str, Any], estimated: bool) -> dict[str, Any]:
        keys = (
            "period_id", "carrier_key", "carrier_label", "origin_iata",
            "destination_iata", "support_observed_in_period",
            "support_source_periods", "support_month_gap",
        )
        result = {key: item.get(key) for key in keys}
        for key in ("passengers", "passengers_low", "passengers_high", "seats", "departures"):
            result[key] = compact_number(item.get(key)) if estimated else item.get(key)
        result["load_factor"] = compact_number(item.get("load_factor"), 4) if estimated else item.get("load_factor")
        result["capacity_estimated"] = item.get("capacity_estimated", False)
        return result

    def route(value: dict[str, Any]) -> dict[str, Any]:
        estimated = value.get("passengers_estimated", False)
        metrics = {key: value[key] for key in metric_keys}
        if estimated:
            metrics = {
                "passengers": compact_number(value.get("passengers")),
                "seats": compact_number(value.get("seats")),
                "departures": compact_number(value.get("departures")),
                "load_factor": compact_number(value.get("load_factor"), 4),
            }
        return {
            "market_key": value["market_key"],
            "coverage_note": value.get("coverage_note", ""),
            "source_label": value.get("source_label", "BTS T-100"),
            "operation_status": value.get("operation_status", "operated_observed"),
            "context": value.get("context"),
            "passengers_low": compact_number(value.get("passengers_low")) if estimated else value.get("passengers_low"),
            "passengers_high": compact_number(value.get("passengers_high")) if estimated else value.get("passengers_high"),
            "passengers_estimated": estimated,
            "capacity_estimated": value.get("capacity_estimated", False),
            "seats_low": compact_number(value.get("seats_low")) if estimated else value.get("seats_low"),
            "seats_high": compact_number(value.get("seats_high")) if estimated else value.get("seats_high"),
            "load_factor_low": compact_number(value.get("load_factor_low"), 4) if estimated else value.get("load_factor_low"),
            "load_factor_high": compact_number(value.get("load_factor_high"), 4) if estimated else value.get("load_factor_high"),
            "load_factor_status": value.get("load_factor_status"),
            "support_repair_applied": value.get("support_repair_applied", False),
            "months_covered": value.get("months_covered"),
            "months_selected": value.get("months_selected"),
            "origin": endpoint(value["origin"]),
            "destination": endpoint(value["destination"]),
            **metrics,
            "previous": {key: value["previous"].get(key) for key in metric_keys},
            "directions": [] if estimated else [
                {
                    key: direction.get(key)
                    for key in (
                        "origin_iata",
                        "destination_iata",
                        "passengers",
                        "passengers_low",
                        "passengers_high",
                        "seats",
                        "departures",
                    )
                }
                for direction in value.get("directions", [])
            ],
            "monthly": [monthly_item(item, estimated) for item in value.get("monthly", [])],
        }

    def network(value: dict[str, Any]) -> dict[str, Any]:
        return {
            key: value[key]
            for key in ("period_label", "expected_months", "observed_months")
        } | {
            "routes": [route(item) for item in value["routes"]],
            "airports": [endpoint(item) for item in value["airports"]],
            "coverage_by_source": value.get("coverage_by_source", {}),
            "mode": value.get("mode", "observed_international"),
            "source_url": value.get("source_url"),
            "availability": value.get("availability"),
            "agent_eligible": value.get("agent_eligible", False),
            "eligibility_reason": value.get("eligibility_reason"),
            "represented_passengers": value.get("represented_passengers"),
            "represented_movements": value.get("represented_movements"),
            "aena_airport_activity": [
                {key: item[key] for key in (
                    "airport_iata", "passengers", "operations", "observed_months",
                    "expected_months", "coverage_status",
                )}
                for item in value.get("aena_airport_activity", [])
            ],
        }

    monthly_domestic = {
        period_id: network(value)
        for period_id, value in payload.get("domestic_monthly_networks", {}).items()
    }
    return {
        "schema_version": payload["schema_version"],
        "metadata": payload["metadata"],
        "quarters": payload["quarters"],
        "monthly_passengers": payload["monthly_passengers"],
        "route_network": {"world_geometry": payload["route_network"]["world_geometry"]},
        "route_networks": {
            period_id: network(value)
            for period_id, value in payload.get("international_networks", payload["route_networks"]).items()
        },
        "domestic_networks": {
            period_id: network(value)
            for period_id, value in payload.get("domestic_networks", {}).items()
        } if not monthly_domestic else {},
        "domestic_monthly_networks": monthly_domestic,
    }


def standalone_flight_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Embed a single consumer network, with review-only context kept separately."""
    return integration_flight_payload(payload) | {
        key: payload[key] for key in ('forecast', 'sources', 'agent_eligibility')
    }


def integrated_flights_css() -> str:
    """Scope the shared Vuelos stylesheet so the main dashboard keeps its theme."""

    css = CSS_PATH.read_text(encoding="utf-8")
    start = css.index(".flight-kpi-grid")
    variables = css[css.index(":root {") + len(":root {") : css.index("}", css.index(":root {"))]
    scoped: list[str] = []
    for line in css[start:].splitlines():
        stripped = line.lstrip()
        if "{" in stripped and not stripped.startswith("@"):
            selector, remainder = stripped.split("{", 1)
            selectors = ", ".join(
                f"#panel-flights {item.strip()}" for item in selector.split(",")
            )
            line = f"{line[: len(line) - len(stripped)]}{selectors} {{{remainder}"
        scoped.append(line)
    return f"#panel-flights {{{variables}}}\n" + "\n".join(scoped)


def render_flights_html(payload: dict[str, Any]) -> str:
    """Return a portable review document from a validated flight payload."""

    if payload.get("schema_version") != "flight_dashboard_payload_v1":
        raise ValueError("Unsupported flight dashboard payload")
    css = CSS_PATH.read_text(encoding="utf-8")
    app_js = JS_PATH.read_text(encoding="utf-8")
    plotly_js = get_plotlyjs()
    if re.search(r"</script", plotly_js, re.IGNORECASE):
        raise ValueError("Bundled Plotly JavaScript contains an unsafe script terminator")
    document = f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{escape(payload['metadata']['title'])}</title>
  <style>{css}</style>
</head>
<body>
  <main class="flights-shell" data-testid="flights-review-root">
    <header class="flights-hero">
      <div>
        <p class="hero-kicker">Vista autónoma de revisión · Primer incremento</p>
        <h1>Aeroméxico Tracker</h1>
        <p class="hero-title">Vuelos</p>
      </div>
      <div class="period-control">
        <span class="period-label">Trimestre analizado</span>
        <div class="period-stepper" role="group" aria-label="Cambiar trimestre analizado">
          <button type="button" id="period-prev" aria-label="Ir al trimestre anterior" title="Trimestre anterior">▼</button>
          <output id="period-display" aria-live="polite">—</output>
          <button type="button" id="period-next" aria-label="Ir al trimestre siguiente" title="Trimestre siguiente">▲</button>
        </div>
      </div>
    </header>

    <section class="flight-kpi-grid" aria-label="Capacidad y demanda trimestral">
      {_kpi_card('passengers', 'Pasajeros', 'Pasajeros transportados por Grupo Aeroméxico durante el trimestre.', 'blue')}
      {_kpi_card('asm_miles', 'ASM', 'Asientos disponibles multiplicados por millas voladas.', 'gold')}
      {_kpi_card('rpm_miles', 'RPM', 'Pasajeros transportados multiplicados por millas voladas.', 'violet')}
      {_kpi_card('load_factor', 'Ocupación', 'RPM dividido entre ASM; porcentaje de capacidad utilizada.', 'amber')}
    </section>
    <section aria-labelledby="network-title">
      <div class="section-heading network-heading">
        <div><p class="section-kicker">Red de vuelos</p><h2 id="network-title">Rutas nacionales</h2><p class="network-scope-note" id="network-scope-note"></p></div>
      </div>
      <div class="network-mode-switch" role="radiogroup" aria-label="Tipo de red">
        <button type="button" id="network-mode-domestic" role="radio" aria-checked="true" aria-pressed="true">Nacional</button>
        <button type="button" id="network-mode-international" role="radio" aria-checked="false" aria-pressed="false">Internacional</button>
        <div class="network-region-switch" id="network-region-switch" role="group" aria-label="Región internacional" hidden></div>
      </div>
      <div class="network-month-switch" id="network-month-switch" role="group" aria-label="Meses nacionales (selección múltiple)"></div>
      <div class="network-volume" id="network-volume" hidden></div>
      <div class="network-layout">
        <article class="panel flow-map-panel" id="map-panel">
          <div class="map-detail-layout">
            <div class="map-canvas-column">
              <div class="chart flow-map" id="route-flow-map" role="img" aria-label="Mapa de rutas por fuente y tipo de observación"></div>
            </div>
            <aside class="airport-tooltip" id="airport-tooltip" role="region" aria-label="Detalle de rutas por aeropuerto"></aside>
          </div>
        </article>
      </div>
    </section>

    <section aria-labelledby="mix-title">
      <div class="section-heading">
        <div><p class="section-kicker">Capacidad y demanda</p><h2 id="mix-title">Mezcla nacional e internacional</h2></div>
        <p class="source-inline">AFAC Gold · serie mensual consolidada</p>
      </div>
      <article class="panel chart-panel">
        <div class="panel-heading chart-heading">
          <div><p class="panel-title">Pasajeros y contribución por segmento</p></div>
          <label class="chart-range-control" for="passenger-period">Periodo
            <select id="passenger-period">
              <option value="quarter" selected>Trimestral</option>
              <option value="month">Mensual</option>
            </select>
          </label>
        </div>
        <div class="chart chart-mix" id="mix-chart" role="img" aria-label="Pasajeros por periodo: barras apiladas nacional e internacional y línea del total calculado"></div>
      </article>
    </section>

    <section aria-labelledby="forecast-title">
      <div class="section-heading">
        <div><p class="section-kicker">Perspectiva secundaria</p><h2 id="forecast-title">Pronóstico mensual de pasajeros</h2></div>
        <p class="source-inline">Modelo vigente · fuera del paquete histórico 2T26</p>
      </div>
      <article class="panel chart-panel">
        <div class="forecast-warning" role="note"><strong>Perspectiva actual.</strong> Este modelo fue entrenado después del corte 2T26 y no alimenta al Analysis Agent piloto.</div>
        <div class="chart forecast-chart" id="forecast-chart" role="img" aria-label="Pasajeros observados y pronosticados con intervalos de 80 y 95 por ciento"></div>
        <p class="model-note" id="model-note"></p>
      </article>
    </section>

    <details class="methodology">
      <summary>Fuentes, periodos y elegibilidad para el agente</summary>
      <div class="methodology-body">
        <div id="source-inventory"></div>
        <h3>Exclusiones del paquete candidato</h3>
        <ul id="eligibility-exclusions"></ul>
      </div>
    </details>

    <footer>
      <span>Vista local de revisión · No integrada en la navegación principal.</span>
      <span>Proyecto independiente y no oficial · No es consejo de inversión.</span>
    </footer>
    <p class="sr-only" id="live-status" aria-live="polite"></p>
  </main>
  <script type="application/json" id="flight-dashboard-data">{_safe_json(standalone_flight_payload(payload))}</script>
  <script data-runtime="plotly-local">{plotly_js}</script>
  <script data-runtime="flights-review">{app_js}</script>
</body>
</html>
"""
    return "\n".join(line.rstrip() for line in document.splitlines()) + "\n"


def write_flights_html(payload: dict[str, Any], output: Path = DEFAULT_OUTPUT) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_flights_html(payload), encoding="utf-8")
    return output.resolve()
