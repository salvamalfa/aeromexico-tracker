// Network mode/period orchestration: switches between domestic and
// international, fetches whatever period file is needed, and re-renders
// the map, region/month switches, volume line and route detail panel.
// Ported from src/dashboard/assets/flights.js::renderNetworkPeriod.

import { $, finite } from "./dom.js";
import {
  DEFAULT_AIRPORT, domesticAvailableForQuarter, ensureDomesticMonths, ensureDomesticQuarter,
  ensureInternational, monthsInQuarter, state,
} from "./state.js";
import { aggregateDomesticMonths, renderMonthSwitch } from "./domestic.js";
import { regionRoutes, renderRegionSwitch } from "./regions.js";
import { renderNetworkVolume } from "./volume.js";
import { renderAirportTooltip, renderRouteDetailPlaceholder } from "./table.js";
import { renderFlowMap, routesForAirport } from "./map.js";

export function routeValue(route) {
  const key = state.network?.mode === "scheduled_domestic" ? "departures" : state.importance;
  return finite(route[key]) ? route[key] : 0;
}

export function orderedRoutes() {
  return [...state.routes].sort((a, b) => routeValue(b) - routeValue(a) || a.market_key.localeCompare(b.market_key));
}

export function routeTitle(route) {
  return `${route.origin.iata} ↔ ${route.destination.iata}`;
}

function domesticPeriodNetwork(periodId) {
  return aggregateDomesticMonths([...state.selectedDomesticMonths]) || state.domesticNetworks.get(periodId);
}

function internationalPeriodNetwork(periodId) {
  return state.internationalNetworks.get(periodId) || { world_geometry: state.worldGeometry, routes: [], airports: [] };
}

export async function renderNetworkPeriod(periodId) {
  await ensureDomesticMonths(monthsInQuarter(state.domesticMonthsQuarterId));
  const domesticAvailable = domesticAvailableForQuarter(periodId);
  if (state.networkMode === "domestic" && !domesticAvailable) state.networkMode = "international";
  if (state.networkMode === "domestic") await ensureDomesticQuarter(periodId);
  else await ensureInternational(periodId);

  const periodNetwork = state.networkMode === "domestic"
    ? domesticPeriodNetwork(periodId)
    : internationalPeriodNetwork(periodId);
  state.network = { ...periodNetwork, world_geometry: state.worldGeometry };
  if (state.networkMode !== "international") state.selectedRegion = null;
  // Sin vuelos propios no hay registro que mostrar: son rutas donde la fuente
  // solo confirma presencia de Aeromexico, sin volumen atribuible.
  const quantified = (state.network.routes || []).filter((route) =>
    state.network.mode === "estimated_domestic"
      ? finite(route.passengers)
      : finite(route.departures) || (route.passengers_estimated && finite(route.passengers))
  );
  state.network.routes = quantified;
  state.routes = regionRoutes(quantified);
  if (state.selectedRegion) {
    const shownAirports = new Set(state.routes.flatMap((route) => [route.origin.iata, route.destination.iata]));
    state.network.airports = (state.network.airports || []).filter((airport) => shownAirports.has(airport.iata));
  }
  // Nacional/Internacional es una elección mutuamente excluyente (role="radio"):
  // siempre hay exactamente una vista activa y ambos botones permanecen
  // clicables para poder alternar en cualquier sentido, cuantas veces sea.
  $("network-mode-domestic").disabled = !domesticAvailable;
  $("network-mode-domestic").setAttribute("aria-pressed", String(state.networkMode === "domestic"));
  $("network-mode-domestic").setAttribute("aria-checked", String(state.networkMode === "domestic"));
  $("network-mode-international").setAttribute("aria-pressed", String(state.networkMode === "international"));
  $("network-mode-international").setAttribute("aria-checked", String(state.networkMode === "international"));
  $("network-title").textContent = state.networkMode === "domestic" ? "Rutas nacionales" : "Rutas internacionales";
  const scopeNote = $("network-scope-note");
  if (scopeNote) {
    // La etiqueta de alcance nunca dice "Grupo Aeroméxico" salvo cuando el
    // dato realmente combina Aerovías de México y Aeroméxico Connect
    // (nacional). Internacional solo tiene evidencia retenida de Aerovías
    // de México como operador; decirlo explícitamente evita presentar una
    // cifra más angosta como si fuera consolidada.
    scopeNote.textContent = state.networkMode === "domestic"
      ? "Grupo Aeroméxico · combina Aerovías de México y Aeroméxico Connect"
      : "Aerovías de México (operador reportante) · no incluye Aeroméxico Connect";
  }
  renderMonthSwitch();
  renderRegionSwitch();
  renderNetworkVolume();
  // Con una region elegida, MEX puede quedar fuera del recorte: se abre el
  // aeropuerto de la region con mas rutas para que el detalle nunca salga vacio.
  const regionFallback = () => {
    const counts = new Map();
    state.routes.forEach((route) => [route.origin.iata, route.destination.iata]
      .filter((iata) => (state.network.airports || []).some((airport) => airport.iata === iata))
      .forEach((iata) => counts.set(iata, (counts.get(iata) || 0) + 1)));
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] || null;
  };
  let focusAirportIata = DEFAULT_AIRPORT;
  let defaultIncident = routesForAirport(focusAirportIata);
  if (!defaultIncident.length) {
    focusAirportIata = regionFallback();
    defaultIncident = focusAirportIata ? routesForAirport(focusAirportIata) : [];
  }
  state.pinnedAirport = defaultIncident.length ? focusAirportIata : null;
  state.hoveredAirport = state.pinnedAirport;
  state.hoveredAirportAt = 0;
  state.selectedMarket = defaultIncident[0]?.market_key || null;
  if (state.pinnedAirport) renderAirportTooltip(state.pinnedAirport, defaultIncident, true);
  else renderRouteDetailPlaceholder();
  if (state.flowMapRendered) renderFlowMap();
}
