// Compact, quarter-level route reading for the executive map preview.

import { $, deltaDisplay, esc, finite, formatRouteMetric, integer } from "./dom";
import { state } from "./state";
import { coverageDotHtml, scheduledIconHtml, sourceFooterHtml, SCHEDULED_STATUSES } from "./coverage";
import { bindAirportSearchControls } from "./search";
import { routeTitle } from "./network";
import type { Route } from "../../types/domain";

function routeStatus(route: Route): string {
  if (route.passengers_estimated) return "Estimación";
  if (route.operation_status && SCHEDULED_STATUSES.includes(route.operation_status)) return "Programado";
  if (route.operation_status === "carrier_inferred_market_observed") return "Inferido";
  return "Observado";
}

function routeCaveat(route: Route): string {
  if (route.passengers_estimated) return "";
  if (route.operation_status && SCHEDULED_STATUSES.includes(route.operation_status)) return "Vuelos previstos; operación no confirmada";
  return "";
}

function routeRows(routes: Route[]): string {
  return routes.map((route, index) => {
    const flights = finite(route.departures) ? `${integer.format(route.departures)} ${route.operation_status && SCHEDULED_STATUSES.includes(route.operation_status) ? "programados" : route.capacity_estimated ? "estimados" : "observados"}` : "N/D";
    const occupancy = finite(route.load_factor) ? formatRouteMetric("load_factor", route.load_factor) : "N/D";
    const caveat = routeCaveat(route);
    const previousPassengers = route.previous?.passengers;
    const change = !route.passengers_estimated && finite(previousPassengers)
      ? deltaDisplay(route.passengers, previousPassengers) : null;
    return `<li class="executive-route-row">
      <span class="executive-route-rank">${index + 1}</span>
      <div class="executive-route-copy">
        <strong>${esc(routeTitle(route))}${coverageDotHtml(route)}${scheduledIconHtml(route)}</strong>
        <span>${esc(routeStatus(route))}${caveat ? ` · ${esc(caveat)}` : ""}</span>
        <small>Vuelos: ${esc(flights)} · ocupación ${esc(occupancy)}</small>
      </div>
      <div class="executive-route-value"><strong>${finite(route.passengers) ? integer.format(route.passengers) : "N/D"}</strong><span>pasajeros</span>${change && change.text !== "No disponible" ? `<small class="${change.className}" title="Frente a los mismos meses disponibles del año anterior">${esc(change.text)} interanual</small>` : ""}</div>
    </li>`;
  }).join("");
}

function searchButton(): string {
  return `<button type="button" class="airport-search-toggle" id="airport-search-toggle" aria-label="Buscar aeropuerto por código o ciudad" aria-expanded="false" aria-controls="airport-search-box">
    <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="m15.5 15.5 5 5"></path></svg>
  </button>`;
}

function searchBox(): string {
  return `<div class="airport-search-box" id="airport-search-box" hidden>
    <label class="sr-only" for="airport-search-input">Código o ciudad</label>
    <input id="airport-search-input" type="search" autocomplete="off" placeholder="Código o ciudad">
    <div class="airport-search-results" id="airport-search-results" role="listbox" aria-label="Aeropuertos encontrados"></div>
  </div>`;
}

function render(title: string, subtitle: string, routes: Route[], airportSelected: boolean): void {
  const host = $("airport-tooltip")!;
  host.innerHTML = `<div class="airport-title-row"><div><h3>${esc(title)}</h3><p class="airport-meta">${esc(subtitle)}</p></div>${searchButton()}</div>
    ${searchBox()}
    ${airportSelected ? '<button type="button" class="route-overview-back" id="route-overview-back">← Toda la red</button>' : ""}
    ${routes.length ? `<ol class="executive-route-list">${routeRows(routes)}</ol>` : '<p class="airport-tooltip-empty">No hay rutas con volumen atribuible en esta selección.</p>'}
    ${sourceFooterHtml(routes)}`;
  bindAirportSearchControls();
  $("route-overview-back")?.addEventListener("click", () => {
    state.pinnedAirport = null;
    state.selectedMarket = null;
    window.dispatchEvent(new Event("flight-route-overview"));
  });
}

export function renderRouteOverview(routes: Route[]): void {
  const scope = state.networkMode === "domestic" ? "red nacional" : "red internacional";
  const label = state.showAllRoutes ? "Todas las rutas" : "Rutas destacadas";
  const period = state.network?.period_label || "";
  render(label, `${scope} · ${period} · ordenadas por pasajeros disponibles${state.networkMode === "international" ? " · variación vs. mismos meses disponibles" : ""}`, routes, false);
}

export function renderAirportTooltip(airport: string, incident: Route[], _isPinned?: boolean): void {
  const city = state.network?.airports.find((item) => item.iata === airport)?.city || "Aeropuerto";
  render(`${airport} · ${city}`, `${incident.length} ${incident.length === 1 ? "ruta visible" : "rutas visibles"} · ${state.network?.period_label || ""}`, incident, true);
}
