import { renderMapChartSource } from "./chart-sources";
// Network mode/period orchestration: switches between domestic and
// international, fetches whatever period file is needed, and re-renders
// the map, region/month switches, volume line and route detail panel.
// Ported from src/dashboard/assets/flights.js::renderNetworkPeriod.

import { $, finite } from "./dom";
import {
  domesticAvailableForQuarter, ensureDomesticMonths, ensureDomesticQuarter,
  ensureInternational, monthsInQuarter, state,
} from "./state";
import { aggregateDomesticMonths } from "./domestic";
import { normalizeSelectedRegion, regionRoutes, renderRegionSwitch } from "./regions";
import { routeEvidenceView, routeDataMonths } from "./evidence-view";
import { renderMapCoverage } from "./map-coverage";
import { renderNetworkVolume } from "./volume";
import { flightKind } from "./flight-measure";
import { renderRouteOverview } from "./table";
import { renderFlowMap } from "./map";
import { currentMapPeriod, mapPeriodLabel, renderMapPeriodControl } from "./map-periods";
import { calendarQuarter, officialDomesticNetwork } from "./map-layers";
import type { Network, PeriodNetworkDocument, Route } from "../../types/domain";
import { coverageText, expectedMonths } from "../../state/coverage";

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

  for (const [id, view] of [["map-routes-featured", "volume"], ["map-routes-change", "change"], ["map-routes-all", "all"]] as const) {
    $(id)!.setAttribute("aria-pressed", String(state.routeView === view));
  }
  const changeButton = $("map-routes-change") as HTMLButtonElement;
  changeButton.disabled = !canShowChange;
  changeButton.title = canShowChange
    ? "Cambio de vuelos observados frente a los mismos meses del año anterior; mínimo 50 vuelos en uno de los periodos"
    : "Sin comparación de vuelos observados con cobertura equivalente";
  renderMapCoverage(visible.length);
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

export function routeTitle(route: Route, airportCodes = false): string {
  const label = (airport: Route["origin"]): string => airportCodes ? airport.iata : cityLabel(airport.city || airport.iata);
  if (route.directions?.length === 1) {
    const direction = route.directions[0]!;
    const [origin, destination] = direction.origin_iata === route.origin.iata
      ? [route.origin, route.destination] : [route.destination, route.origin];
    return `${label(origin)} → ${label(destination)}`;
  }
  return `${label(route.origin)} ↔ ${label(route.destination)}`;
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

let networkRenderRequest = 0;

export async function renderNetworkPeriod(periodId: string): Promise<boolean> {
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
  if (request !== networkRenderRequest || entity !== state.mapEntity) return false;
  const domesticAvailable = domesticAvailableForQuarter(periodId);
  if (state.networkMode === "domestic") await ensureDomesticQuarter(calendarQuarter(periodId));
  else await ensureInternational(periodId);
  if (request !== networkRenderRequest || entity !== state.mapEntity) return false;

  const periodNetwork = { ...(state.networkMode === "domestic" ? domesticPeriodNetwork(periodId) : internationalPeriodNetwork(periodId)) };
  const observed = periodNetwork.observed_months ?? (state.networkMode === "domestic" && periodNetwork.routes.length ? [...state.selectedDomesticMonths] : []);
  const expected = expectedMonths(periodId);
  periodNetwork.expected_months = expected;
  periodNetwork.observed_months = observed.filter(month => expected.includes(month));
  periodNetwork.period_label = `${mapPeriodLabel(periodId)} · ${coverageText(periodId, observed).split(" · ")[1]}`;
  state.network = { ...(periodNetwork as PeriodNetworkDocument), world_geometry: state.worldGeometry ?? undefined } as Network;
  if (state.networkMode !== "international") state.selectedRegion = null;
  // Preserve the source network for region availability; filter the visible
  // evidence before map totals, rankings, search and airport tooltips consume it.
  state.networkAllRoutes = state.network.routes || [];
  normalizeSelectedRegion(state.networkAllRoutes);
  const view = routeEvidenceView(state.networkAllRoutes,state.networkMode,state.selectedRegion);
  state.evidenceView = view.evidenceView;
  state.excludedNorthAmericaFlights = view.excluded;
  state.observedNorthAmericaMonths = view.observedMonths;
  state.hasNorthAmericaObservations = view.hasNorthAmericaObservations;
  const quantified = view.routes.filter(route => finite(route.departures) || finite(route.recorded_movements?.count));
  state.presenceOnlyRouteCount = regionRoutes(view.routes).length - regionRoutes(quantified).length;
  state.network.routes = quantified;
  state.routes = regionRoutes(quantified);
  const datedMonths=routeDataMonths(state.routes,periodNetwork.coverage_by_source??{});
  if(datedMonths.length)state.network.observed_months=datedMonths.filter(month=>expected.includes(month));
  else if(!state.routes.length)state.network.observed_months=[];
  const shownAirports = new Set(state.routes.flatMap(route => [route.origin.iata,route.destination.iata]));
  state.network.airports = (state.network.airports || []).filter(airport => shownAirports.has(airport.iata));
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
  const networkTitle = $("network-title")!;
  const networkLabel = state.networkMode === "domestic" ? "Rutas nacionales" : "Rutas internacionales";
  const titleText = [...networkTitle.childNodes].find(node => node.nodeType === Node.TEXT_NODE);
  if (titleText) titleText.textContent = networkLabel;
  else networkTitle.prepend(document.createTextNode(networkLabel));
  renderMapChartSource(state.routes);
  renderMapPeriodControl();
  renderRegionSwitch();
  renderNetworkVolume();
  state.pinnedAirport = null;
  state.hoveredAirport = null;
  state.hoveredAirportAt = 0;
  state.selectedMarket = null;
  renderRouteMode();
  if (state.flowMapRendered) renderFlowMap();
  return true;
}
