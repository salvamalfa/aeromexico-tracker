// Concise quarterly route ranking beside the map.

import { $, esc, finite, formatRouteMetric, integer } from "./dom";
import { state } from "./state";
import { coverageDotHtml, scheduledIconHtml, sourceFooterHtml, SCHEDULED_STATUSES } from "./coverage";
import { bindAirportSearchControls } from "./search";
import { routeChangePercent, routeTitle } from "./network";
import type { Route } from "../../types/domain";

function routeRows(routes: Route[]): string {
  let downStarted = false;
  return routes.map((route, index) => {
    const change = state.routeView === "change" ? routeChangePercent(route) : null;
    const isDown = change !== null && change < 0;
    const group = state.routeView !== "change" ? ""
      : index === 0 ? '<li class="executive-route-group">Aumentan</li>'
      : isDown && !downStarted ? '<li class="executive-route-group">Caen</li>' : "";
    if (isDown) downStarted = true;
    const flights = finite(route.departures) ? integer.format(route.departures) : "N/D";
    const flightKind = route.operation_status && SCHEDULED_STATUSES.includes(route.operation_status)
      ? "programados" : route.capacity_estimated ? "estimados" : "observados";
    const occupancy = finite(route.load_factor) ? formatRouteMetric("load_factor", route.load_factor) : "N/D";
    const sourceBadge = route.passengers_estimated && state.networkMode === "international"
      ? '<span class="route-evidence-badge">estim.</span>' : "";
    const changeText = change === null ? "" : `<small class="executive-route-trend ${change >= 0 ? "delta-up" : "delta-down"}">${change >= 0 ? "+" : ""}${change.toFixed(1)}% interanual</small>`;
    return `${group}<li class="executive-route-row">
      <span class="executive-route-rank">${index + 1}</span>
      <div class="executive-route-copy"><strong>${esc(routeTitle(route))}${coverageDotHtml(route)}${scheduledIconHtml(route)}${sourceBadge}</strong>${changeText}</div>
      <div class="executive-route-value" title="Pasajeros ${route.passengers_estimated ? "estimados" : "observados"}">${finite(route.passengers) ? integer.format(route.passengers) : "N/D"}</div>
      <div class="executive-route-value" title="Vuelos ${flightKind}">${flights}</div>
      <div class="executive-route-value">${esc(occupancy)}</div>
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

function render(title: string, routes: Route[], airportSelected: boolean): void {
  const host = $("airport-tooltip")!;
  host.innerHTML = `<div class="airport-title-row"><h3>${esc(title)}</h3>${searchButton()}</div>
    ${searchBox()}
    ${airportSelected ? '<button type="button" class="route-overview-back" id="route-overview-back">← Toda la red</button>' : ""}
    ${routes.length ? `<div class="executive-route-columns"><span>Ruta</span><span>Pasajeros</span><span>Vuelos</span><span>Ocupación</span></div><ol class="executive-route-list">${routeRows(routes)}</ol>` : '<p class="airport-tooltip-empty">No hay rutas con volumen atribuible en esta selección.</p>'}
    ${sourceFooterHtml(routes)}`;
  bindAirportSearchControls();
  $("route-overview-back")?.addEventListener("click", () => {
    state.pinnedAirport = null;
    state.selectedMarket = null;
    window.dispatchEvent(new Event("flight-route-overview"));
  });
}

export function renderRouteOverview(routes: Route[]): void {
  const label = state.routeView === "all" ? "Todas las rutas"
    : state.routeView === "change" ? "Mayores cambios" : "Rutas destacadas";
  render(label, routes, false);
}

export function renderAirportTooltip(airport: string, incident: Route[], _isPinned?: boolean): void {
  const city = state.network?.airports.find((item) => item.iata === airport)?.city || "Aeropuerto";
  render(`${airport} · ${city}`, incident, true);
}
