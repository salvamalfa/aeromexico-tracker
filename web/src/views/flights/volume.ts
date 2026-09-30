// Quarterly segment passengers and route-evidence flights/occupancy.

import { $, esc, finite, integer } from "./dom";
import { state } from "./state";
import { SCHEDULED_STATUSES } from "./coverage";
import type { Route } from "../../types/domain";
import { entityState } from "../executive/entities";
import { ENTITY_LABELS, type EntityKey } from "../shell/carriers";

// Dashboard v2: for Industria/Volaris/Viva the quarter's AFAC segment total
// comes from market.json (same source as the mix chart); Grupo Aeroméxico
// keeps its historical monthly series.
function entitySegmentPassengers(periodId: string): number | null {
  const quarter = entityState.market?.quarters.find((item) => item.period_id === periodId);
  if (!quarter) return null;
  const segment = quarter.segments[state.networkMode === "domestic" ? "domestic" : "international"];
  const item = state.mapEntity === "INDUSTRY" ? segment.industry : segment.carriers[state.mapEntity];
  return item?.passengers ?? null;
}

function segmentPassengers(periodId: string): number | null {
  if (state.mapEntity !== "AEROMEXICO") return entitySegmentPassengers(periodId);
  const quarter = Number(periodId.slice(-1));
  const year = Number(periodId.slice(0, 4));
  if (!year || quarter < 1 || quarter > 4 || !state.monthlyPassengers) return null;
  const months = state.monthlyPassengers.records.filter((point) => {
    const date = new Date(`${point.date}T00:00:00Z`);
    return date.getUTCFullYear() === year && Math.floor(date.getUTCMonth() / 3) + 1 === quarter;
  });
  if (months.length !== 3) return null;
  return months.reduce((sum, point) => sum + (state.networkMode === "domestic" ? point.domestic : point.international), 0);
}

function miniCard(label: string, value: string, note: string, title: string): string {
  return `<div class="network-mini-kpi" title="${esc(title)}"><small>${esc(label)}</small><strong>${esc(value)}</strong><span>${esc(note)}</span></div>`;
}

export function renderNetworkVolume(): void {
  const host = $("network-volume");
  if (!host) return;
  // The cards describe the full selected national/international network. A
  // region or highlighted-route choice only filters the map and route list.
  const routes: Route[] = state.network?.routes || state.routes || [];
  const periodId = state.quarters[state.periodIndex]?.period_id ?? "";
  const period = state.quarters[state.periodIndex]?.period_label || state.network?.period_label || "";
  const passengers = segmentPassengers(periodId);
  host.hidden = !routes.length && !state.presenceOnlyRouteCount && passengers === null;
  if (host.hidden) {
    host.innerHTML = "";
    return;
  }

  const domestic = state.networkMode === "domestic";
  const flightRoutes = routes.filter((route) =>
    finite(route.departures) && (domestic ? route.capacity_estimated :
      !route.passengers_estimated && !SCHEDULED_STATUSES.includes(route.operation_status ?? "") &&
      route.operation_status !== "carrier_inferred_market_observed")
  );
  const flights = flightRoutes.reduce((sum, route) => sum + route.departures!, 0);
  // Occupancy is passenger-weighted through seats, using only routes with
  // matching passenger/capacity evidence. It is not an average of percentages.
  const occupancyRoutes = routes.filter((route) =>
    finite(route.passengers) && finite(route.seats) && route.seats > 0 &&
    finite(route.load_factor) && route.load_factor >= 0 && route.load_factor <= 1 &&
    (domestic ? route.capacity_estimated : !route.passengers_estimated &&
      !SCHEDULED_STATUSES.includes(route.operation_status ?? "") &&
      route.operation_status !== "carrier_inferred_market_observed")
  );
  const occupied = occupancyRoutes.reduce((sum, route) => sum + route.passengers!, 0);
  const seats = occupancyRoutes.reduce((sum, route) => sum + route.seats!, 0);
  const occupancy = seats > 0 ? `${(occupied / seats * 100).toFixed(1)}%` : "N/D";
  const networkLabel = domestic ? "nacional" : "internacional";
  host.innerHTML = `<div class="network-mini-heading"><span>Red ${networkLabel}</span><span>${esc(period)}</span></div>
    <div class="network-mini-kpi-grid">
      ${miniCard("Pasajeros", passengers === null ? "N/D" : integer.format(passengers), `AFAC · ${state.mapEntity === "AEROMEXICO" ? "Grupo" : ENTITY_LABELS[state.mapEntity as EntityKey] ?? state.mapEntity}`, `Total trimestral ${networkLabel} de AFAC; coincide con Mezcla nacional e internacional. El detalle por ruta tiene otra cobertura.`)}
      ${miniCard("Vuelos", flightRoutes.length ? integer.format(flights) : "N/D", `${domestic ? "est." : "obs."} · ${flightRoutes.length}/${routes.length} rutas`, `${domestic ? "Estimación" : state.mapEntity === "AEROMEXICO" ? "Vuelos observados de Aerovías de México" : "Vuelos observados por BTS T-100"} en ${flightRoutes.length} rutas con dato; no representa necesariamente toda la red.`)}
      ${miniCard("Ocupación", occupancy, `${domestic ? "est." : "obs."} · ${occupancyRoutes.length}/${routes.length} rutas`, `Pasajeros ÷ asientos en ${occupancyRoutes.length} rutas con ambos datos compatibles. No es la ocupación de toda la red.`)}
    </div>`;
}
