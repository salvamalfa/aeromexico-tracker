// Network mode/period orchestration: switches between domestic and
// international, fetches whatever period file is needed, and re-renders
// the map, region/month switches, volume line and route detail panel.
// Ported from src/dashboard/assets/flights.js::renderNetworkPeriod.

import { ENTITY_LABELS, type EntityKey } from "../shell/carriers";
import { $, finite } from "./dom";
import {
  domesticAvailableForQuarter, ensureDomesticMonths, ensureDomesticQuarter,
  ensureInternational, monthsInQuarter, state,
  DOMESTIC_MONTH_NAMES,
} from "./state";
import { aggregateDomesticMonths } from "./domestic";
import { normalizeSelectedRegion, regionRoutes, renderRegionSwitch } from "./regions";
import { renderNetworkVolume } from "./volume";
import { flightKind } from "./flight-measure";
import { renderRouteOverview } from "./table";
import { renderFlowMap } from "./map";
import { currentMapPeriod, mapPeriodLabel, renderMapPeriodControl } from "./map-periods";
import { calendarQuarter, officialDomesticNetwork } from "./map-layers";
import type { Network, PeriodNetworkDocument, Route } from "../../types/domain";

export function routeValue(route: Route): number {
  return finite(route.departures) ? route.departures : 0;
}

export function orderedRoutes(): Route[] {
  return [...state.routes].sort((a, b) => routeValue(b) - routeValue(a) || a.market_key.localeCompare(b.market_key));
}

// The international payload's `previous` field is the same available months
// one year earlier. A small-market floor keeps near-zero bases from dominating
// a percentage ranking; it never changes the underlying route totals.
export function routeChangePercent(route: Route): number | null {
  const current = route.departures;
  const previous = route.previous?.departures;
  if (state.networkMode !== "international" || flightKind(route) !== "observed" ||
      !finite(current) || !finite(previous) || previous <= 0 ||
      Math.max(current, previous) < 50) return null;
  return (current / previous - 1) * 100;
}

function changingRoutes(): Route[] {
  const comparable = state.routes.filter((route) => routeChangePercent(route) !== null);
  const rising = comparable.filter((route) => routeChangePercent(route)! > 0)
    .sort((a, b) => routeChangePercent(b)! - routeChangePercent(a)!).slice(0, 6);
  const falling = comparable.filter((route) => routeChangePercent(route)! < 0)
    .sort((a, b) => routeChangePercent(a)! - routeChangePercent(b)!).slice(0, 6);
  return [...rising, ...falling];
}

export function visibleRoutes(): Route[] {
  const routes = orderedRoutes();
  if (state.routeView === "all") return routes;
  if (state.routeView === "change") return changingRoutes();
  return routes.slice(0, 12);
}

export function renderRouteMode(): void {
  const canShowChange = changingRoutes().length > 0;
  if (state.routeView === "change" && !canShowChange) state.routeView = "volume";
  const visible = visibleRoutes();
  const all = orderedRoutes();

  const presence = state.presenceOnlyRouteCount > 0
    ? ` · ${state.presenceOnlyRouteCount} sin volumen atribuible` : "";
  const periodId = currentMapPeriod();
  const previousLabel = periodId
    ? mapPeriodLabel(`${Number(periodId.slice(0, 4)) - 1}${periodId.slice(4)}`) : "el año anterior";
  $("map-route-title")!.textContent = state.routeView === "change"
    ? "Rutas con mayores cambios" : "Rutas con vuelos en el histórico";
  $("map-route-summary")!.textContent = state.routeView === "change"
    ? `${visible.filter((route) => routeChangePercent(route)! > 0).length} aumentos · ${visible.filter((route) => routeChangePercent(route)! < 0).length} caídas vs. ${previousLabel} · mismos meses disponibles`
    : `${visible.length} de ${all.length} rutas con cifra de vuelos${presence}`;
  for (const [id, view] of [["map-routes-featured", "volume"], ["map-routes-change", "change"], ["map-routes-all", "all"]] as const) {
    $(id)!.setAttribute("aria-pressed", String(state.routeView === view));
  }
  const changeButton = $("map-routes-change") as HTMLButtonElement;
  changeButton.disabled = !canShowChange;
  changeButton.title = canShowChange
    ? "Cambio de vuelos observados frente a los mismos meses del año anterior; mínimo 50 vuelos en uno de los periodos"
    : "Sin comparación de vuelos observados con cobertura equivalente";
  renderRouteOverview(visible);
}

export function cityLabel(name: string): string {
  return ({
    "Mexico City": "CDMX",
    "Ciudad de México": "CDMX",
    "Los Angeles": "Los Ángeles",
    "New York": "Nueva York",
  })[name] || name;
}

export function routeTitle(route: Route): string {
  if (route.directions?.length === 1) {
    const direction = route.directions[0]!;
    const [origin, destination] = direction.origin_iata === route.origin.iata
      ? [route.origin, route.destination] : [route.destination, route.origin];
    return `${cityLabel(origin.city || origin.iata)} → ${cityLabel(destination.city || destination.iata)}`;
  }
  return `${cityLabel(route.origin.city || route.origin.iata)} ↔ ${cityLabel(route.destination.city || route.destination.iata)}`;
}

function domesticPeriodNetwork(periodId: string): PeriodNetworkDocument {
  if (state.mapEntity === "AEROMEXICO" && state.domesticLayer === "official") return officialDomesticNetwork(periodId);
  return aggregateDomesticMonths([...state.selectedDomesticMonths]) ?? state.domesticNetworks.get(periodId) ?? {
    mode: "scheduled_domestic", period_label: state.byPeriod.get(periodId)?.period_label ?? periodId,
    expected_months: [], observed_months: [], routes: [], airports: [],
  };
}

function internationalPeriodNetwork(periodId: string): PeriodNetworkDocument {
  return (
    state.internationalNetworks.get(periodId) ?? {
      mode: "international",
      period_label: "",
      routes: [],
      airports: [],
    }
  );
}

// Dashboard v2 (fase 3): what the map shows for each entity.
function entityScopeNote(entity: string, domestic: boolean): string {
  const label = entity === "VOLARIS" ? "Volaris México (Y4/VOI; excluye Q6 y N3)"
    : entity === "VIVA_AEROBUS" ? "Viva (Aeroenlaces)"
    : entity === "INDUSTRY" ? "Industria: Aeroméxico, Volaris México y Viva"
    : domestic ? "Grupo Aeroméxico (Aerovías + Connect)" : ENTITY_LABELS[entity as EntityKey] ?? entity;
  if (domestic && entity === "AEROMEXICO" && state.domesticLayer === "official") {
    return "Aeroméxico · programación AICM y atribuciones AFAC separadas; no confirman vuelos realizados";
  }
  if (domestic) return `${label} · histórico conservado · frecuencias estimadas identificadas por ruta; no acreditan vuelos realizados`;
  const roles = entity === "AEROMEXICO" ? " · observados: Aerovías; programación: marca AM; estimados: Grupo" : "";
  return `${label}${roles} · histórico conservado · vuelos observados, programación y estimaciones separados · cobertura parcial por fuente`;

}

let networkRenderRequest = 0;

export async function renderNetworkPeriod(periodId: string): Promise<void> {
  periodId = currentMapPeriod() || periodId;
  if (state.domesticMonthsQuarterId !== periodId) {
    state.domesticMonthsQuarterId = periodId;
    state.selectedDomesticMonths = new Set(monthsInQuarter(periodId));
  }
  // Re-evaluate month support after entity changes, including July whose
  // financial quarter has not been published.
  state.selectedDomesticMonths = new Set([...state.selectedDomesticMonths].filter((id) => monthsInQuarter(periodId).includes(id)));
  if (!state.selectedDomesticMonths.size) state.selectedDomesticMonths = new Set(monthsInQuarter(periodId));
  const request = ++networkRenderRequest;
  const entity = state.mapEntity;
  await ensureDomesticMonths(monthsInQuarter(state.domesticMonthsQuarterId));
  if (request !== networkRenderRequest || entity !== state.mapEntity) return;
  const domesticAvailable = domesticAvailableForQuarter(periodId);
  if (state.networkMode === "domestic") await ensureDomesticQuarter(calendarQuarter(periodId));
  else await ensureInternational(periodId);
  if (request !== networkRenderRequest || entity !== state.mapEntity) return;

  const periodNetwork =
    state.networkMode === "domestic" ? domesticPeriodNetwork(periodId) : internationalPeriodNetwork(periodId);
  state.network = { ...(periodNetwork as PeriodNetworkDocument), world_geometry: state.worldGeometry ?? undefined } as Network;
  if (state.networkMode !== "international") state.selectedRegion = null;
  // Sin vuelos propios no hay registro que mostrar: son rutas donde la fuente
  // solo confirma presencia de Aeromexico, sin volumen atribuible.
  const quantified = (state.network.routes || []).filter((route) => finite(route.departures));
  // Una región elegida en otro periodo puede no existir en este (p. ej.
  // Europa antes de 2T26): sin normalizar, el mapa y la tabla quedarían
  // vacíos y el botón activo ni siquiera se mostraría.
  // Se evalúa contra todas las rutas: una región solo con rutas de presencia
  // sigue existiendo y debe poder mostrar su nota N/D.
  state.networkAllRoutes = state.network.routes || [];
  normalizeSelectedRegion(state.networkAllRoutes);
  state.presenceOnlyRouteCount = regionRoutes(state.networkAllRoutes).length - regionRoutes(quantified).length;
  state.network.routes = quantified;
  state.routes = regionRoutes(quantified);
  if (state.selectedRegion) {
    const shownAirports = new Set(state.routes.flatMap((route) => [route.origin.iata, route.destination.iata]));
    state.network.airports = (state.network.airports || []).filter((airport) => shownAirports.has(airport.iata));
  }
  // Nacional/Internacional es una elección mutuamente excluyente (role="radio"):
  // siempre hay exactamente una vista activa y ambos botones permanecen
  // clicables para poder alternar en cualquier sentido, cuantas veces sea.
  const domesticButton = $("network-mode-domestic") as HTMLButtonElement;
  const internationalButton = $("network-mode-international") as HTMLButtonElement;
  domesticButton.disabled = false;
  domesticButton.title = domesticAvailable ? "Histórico nacional disponible; tipo de cifra indicado por ruta" : "Sin número de vuelos por ruta para este periodo";
  domesticButton.setAttribute("aria-pressed", String(state.networkMode === "domestic"));
  domesticButton.setAttribute("aria-checked", String(state.networkMode === "domestic"));
  internationalButton.setAttribute("aria-pressed", String(state.networkMode === "international"));
  internationalButton.setAttribute("aria-checked", String(state.networkMode === "international"));
  $("network-title")!.textContent = state.networkMode === "domestic" ? "Rutas nacionales" : "Rutas internacionales";
  renderMapPeriodControl();
  const scopeNote = $("network-scope-note");
  if (scopeNote) {
    const sourceMonths = Object.entries(periodNetwork.coverage_by_source ?? {}).map(([source, months]) => {
      const name = source.includes("AeroDataBox") ? "Estimación histórica" : source.split("·").at(-1)!.trim();
      const dates = [...new Set(months.map((month) => DOMESTIC_MONTH_NAMES[Number(month.slice(5)) - 1]))];
      return dates.length ? `${name}: ${dates.join(", ")}` : "";
    }).filter(Boolean).join(" · ");
    // La etiqueta de alcance nunca dice "Grupo Aeroméxico" salvo cuando el
    // dato realmente combina Aerovías de México y Aeroméxico Connect
    // (nacional). Internacional solo tiene evidencia retenida de Aerovías
    // de México como operador; decirlo explícitamente evita presentar una
    // cifra más angosta como si fuera consolidada.
    scopeNote.textContent = entityScopeNote(state.mapEntity, state.networkMode === "domestic")
      + ` · ${periodNetwork.period_label || mapPeriodLabel(periodId)}`
      + (sourceMonths ? ` · ${sourceMonths}` : "")
      + (periodNetwork.eligibility_reason?.startsWith("Mapa parcial:")
        ? ` · ${periodNetwork.eligibility_reason.split(". ")[0]}` : "");
  }
  renderRegionSwitch();
  renderNetworkVolume();
  state.pinnedAirport = null;
  state.hoveredAirport = null;
  state.hoveredAirportAt = 0;
  state.selectedMarket = null;
  renderRouteMode();
  if (state.flowMapRendered) renderFlowMap();
}
