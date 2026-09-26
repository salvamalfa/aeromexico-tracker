// Route detail panel: the domestic (flights-only) table, the international
// (full metrics) table, and the airport tooltip wrapper around both.
// Ported from src/dashboard/assets/flights.js.

import { $, deltaDisplay, esc, finite, formatRouteMetric, integer } from "./dom";
import { DOMESTIC_MONTH_NAMES, ESTIMATE_INFO_TITLE, state } from "./state";
import { coverageDotHtml, scheduledIconHtml, sourceFooterHtml } from "./coverage";
import { bindAirportSearchControls } from "./search";
import { routeTitle } from "./network";
import type { AnyRecord, Route, RouteDirection } from "../../types/domain";

const routePalette = [
  "#e31c23", "#0066cc", "#00875a", "#8b5cf6", "#d97706", "#0891b2",
  "#c026d3", "#4d7c0f", "#db2777", "#7c3aed", "#0f766e", "#b45309",
];

export function airportRouteColor(index: number): string {
  return routePalette[index] || `hsl(${Math.round((index * 137.508 + 18) % 360)} 68% 40%)`;
}

export function renderRouteDetailPlaceholder(): void {
  $("airport-tooltip")!.innerHTML = `
    <div class="airport-tooltip-empty">
      <strong>Detalle de rutas</strong>
      <span>Selecciona un punto amarillo para comparar pasajeros, asientos, vuelos y ocupación por sentido.</span>
    </div>`;
}

const METRIC_NAMES: Record<string, string> = {
  passengers: "Pasajeros", seats: "Asientos", departures: "Vuelos", load_factor: "Ocupación",
};

export function routeMetricChangeChip(route: Route, key: string): string {
  if (route.passengers_estimated) return "";
  const previous = (route.previous || {}) as AnyRecord;
  const previousValue =
    key === "load_factor"
      ? finite(previous.passengers) && finite(previous.seats) && (previous.seats as number) > 0
        ? (previous.passengers as number) / (previous.seats as number)
        : null
      : previous[key];
  const change = deltaDisplay((route as unknown as AnyRecord)[key], previousValue, key === "load_factor");
  const label = change.text === "No disponible" ? "N/D" : change.text;
  return `<span class="route-change-chip ${change.className}" title="${METRIC_NAMES[key]} frente a los mismos meses del año anterior" aria-label="${esc(change.text)} frente a los mismos meses del año anterior">${esc(label)}</span>`;
}

function bindExpandToggles(): void {
  $("airport-tooltip")!.querySelectorAll(".route-expand-toggle").forEach((toggle) => {
    toggle.addEventListener("click", () => {
      const controls = toggle.getAttribute("aria-controls");
      const detail = controls ? document.getElementById(controls) : null;
      const expanded = toggle.getAttribute("aria-expanded") === "true";
      toggle.setAttribute("aria-expanded", String(!expanded));
      toggle.classList.toggle("is-open", !expanded);
      if (detail) detail.hidden = expanded;
    });
  });
}

function renderDomesticRouteTable(title: string, subtitle: string, tableRoutes: Route[], subtitleHtml: string | null): void {
  $("airport-tooltip")!.innerHTML = `
    <div class="airport-title-row">
      <h3>${esc(title)}</h3>
      <button type="button" class="airport-search-toggle" id="airport-search-toggle" aria-label="Buscar aeropuerto por código o ciudad" aria-expanded="false" aria-controls="airport-search-box">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="m15.5 15.5 5 5"></path></svg>
      </button>
    </div>
    <div class="airport-search-box" id="airport-search-box" hidden>
      <label class="sr-only" for="airport-search-input">Código o ciudad</label>
      <input id="airport-search-input" type="search" autocomplete="off" placeholder="Código o ciudad">
      <div class="airport-search-results" id="airport-search-results" role="listbox" aria-label="Aeropuertos encontrados"></div>
    </div>
    <p class="airport-meta">${subtitleHtml || esc(subtitle)}</p>
    <div class="airport-table-wrap"><table class="airport-route-table domestic-route-table"><thead><tr><th>Ruta</th><th>Vuelos</th></tr></thead>
      <tbody>${tableRoutes.map((route, index) => `<tr class="route-summary-row" style="--route-color:${airportRouteColor(index)}">
        <td>${(route.directions ?? []).length ? `<button type="button" class="route-expand-toggle" aria-expanded="false" aria-controls="route-directions-${index}"><span class="route-expand-icon" aria-hidden="true">&gt;</span><strong class="route-table-name">${esc(routeTitle(route))}</strong>${coverageDotHtml(route)}${scheduledIconHtml(route)}</button>` : `<strong class="route-table-name">${esc(routeTitle(route))}</strong>${coverageDotHtml(route)}${scheduledIconHtml(route)}`}</td>
        <td class="route-table-value"><strong>${finite(route.departures) ? integer.format(route.departures) : "Sin desglose propio"}</strong></td>
      </tr>${(route.directions ?? []).length ? `<tr class="route-direction-detail" id="route-directions-${index}" style="--route-color:${airportRouteColor(index)}" hidden><td colspan="2"><div class="domestic-direction-list">${(route.directions ?? []).map((direction) => `<div><span>${esc(direction.origin_iata)} → ${esc(direction.destination_iata)}</span><strong>${integer.format(direction.departures ?? 0)}</strong></div>`).join("")}</div></td></tr>` : ""}`).join("")}</tbody></table></div>
    ${sourceFooterHtml(tableRoutes)}`;
  bindExpandToggles();
  bindAirportSearchControls();
}

function metricCell(route: Route, key: string): string {
  const record = route as unknown as AnyRecord;
  if (key === "passengers" && route.passengers_estimated) {
    const low = finite(route.passengers_low) ? route.passengers_low : route.passengers!;
    const high = finite(route.passengers_high) ? route.passengers_high : route.passengers!;
    const title = `Estimación; rango de sensibilidad ${integer.format(low)}–${integer.format(high)} pasajeros`;
    return `<td class="route-table-value"><span class="route-table-total route-estimate-total" title="${esc(title)}"><strong>${integer.format(route.passengers!)}</strong><small>${integer.format(low)}–${integer.format(high)}</small></span></td>`;
  }
  if (route.capacity_estimated && ["seats", "departures", "load_factor"].includes(key)) {
    if (key === "load_factor" && !finite(route.load_factor)) {
      const title =
        route.load_factor_status === "inconsistent_inputs"
          ? "No se muestra: pasajeros y capacidad estimados producen una ocupación superior a 100%"
          : "No disponible";
      return `<td class="route-table-value"><span class="route-table-total" title="${esc(title)}"><strong>N/D</strong></span></td>`;
    }
    const low = key === "seats" ? route.seats_low : key === "load_factor" ? route.load_factor_low : null;
    const high = key === "seats" ? route.seats_high : key === "load_factor" ? route.load_factor_high : null;
    const range = finite(low) && finite(high) ? `<small>${formatRouteMetric(key, low)}–${formatRouteMetric(key, high)}</small>` : "";
    const title =
      key === "departures"
        ? "Estimación mensual basada en siete días distribuidos y ponderados por día de la semana"
        : key === "seats"
          ? "Capacidad estimada con el modelo de aeronave y la configuración de Aeroméxico"
          : "Pasajeros estimados divididos entre asientos estimados";
    return `<td class="route-table-value"><span class="route-table-total route-estimate-total" title="${esc(title)}"><strong>${formatRouteMetric(key, record[key])}</strong>${range}</span></td>`;
  }
  const chip = routeMetricChangeChip(route, key);
  return `<td class="route-table-value"><span class="route-table-total"><strong>${formatRouteMetric(key, record[key])}</strong>${chip}</span></td>`;
}

interface RouteDirectionSlot {
  origin: string;
  destination: string;
  direction?: RouteDirection;
}

function routeDirections(route: Route): RouteDirectionSlot[] {
  const endpoints = [route.origin.iata, route.destination.iata];
  return endpoints.map((origin, index) => {
    const destination = endpoints[1 - index]!;
    const direction = (route.directions || []).find(
      (item) => item.origin_iata === origin && item.destination_iata === destination
    );
    return { origin, destination, direction };
  });
}

function directionValue(direction: RouteDirection | undefined, key: string, route: Route): string {
  if (key === "load_factor" && route.source_label && !route.source_label.includes("BTS")) return "<span>N/D</span>";
  if (!direction) return `<em>No disponible</em>`;
  const record = direction as unknown as AnyRecord;
  const value =
    key === "load_factor" && finite(direction.seats) && direction.seats! > 0
      ? direction.passengers! / direction.seats!
      : record[key];
  return `<span>${formatRouteMetric(key, value)}</span>`;
}

// "Grupo Aeroméxico" se declara una sola vez por caja de detalle, no en
// cada línea de sentido/mes: repetirlo ahí no añade información, ya lo
// dice arriba la nota de alcance y, aquí, este encabezado.
const carrierHeaderHtml = (): string => `<p class="route-estimate-carrier">Grupo Aeroméxico</p>`;

function estimateDirectionLine(item: RouteDirection): string {
  const low = finite(item.passengers_low) ? item.passengers_low! : item.passengers!;
  const high = finite(item.passengers_high) ? item.passengers_high! : item.passengers!;
  const borrowed = item.support_observed_in_period
    ? ""
    : `<small class="route-support-borrowed" title="Soporte de ruta observado en ${esc(item.support_source_periods)}; no es un vuelo observado del mes mostrado">soporte ${esc(item.support_source_periods)}</small>`;
  const seats = item.capacity_estimated ? formatRouteMetric("seats", item.seats) : "N/D";
  const departures = item.capacity_estimated ? formatRouteMetric("departures", item.departures) : "N/D";
  const loadFactor = item.capacity_estimated && finite(item.load_factor) ? formatRouteMetric("load_factor", item.load_factor) : "N/D";
  return `
  <div class="route-direction-line route-estimate-line">
    <span class="route-direction-name">${esc(item.origin_iata)} → ${esc(item.destination_iata)}${borrowed}</span>
    <span title="Rango de sensibilidad ${integer.format(low)}–${integer.format(high)}">${integer.format(item.passengers!)}<small>${integer.format(low)}–${integer.format(high)}</small></span>
    <span>${seats}</span><span>${departures}</span><span>${loadFactor}</span>
  </div>`;
}

// Agrupa por mes en vez de repetir "Grupo Aeroméxico" y el nombre del
// mes en cada una de las líneas de ida/vuelta; el mes queda como un
// rótulo sutil una sola vez por grupo, con un separador ligero entre
// meses.
function estimateDetails(route: Route): string {
  const items = route.monthly || [];
  const byMonth = new Map<string, RouteDirection[]>();
  for (const item of items) {
    const periodId = item.period_id!;
    if (!byMonth.has(periodId)) byMonth.set(periodId, []);
    byMonth.get(periodId)!.push(item);
  }
  const monthIds = [...byMonth.keys()].sort();
  const spansMonths = monthIds.length > 1;
  const body = monthIds
    .map((periodId) => {
      const lines = byMonth.get(periodId)!.map(estimateDirectionLine).join("");
      if (!spansMonths) return lines;
      const monthName = DOMESTIC_MONTH_NAMES[Number(periodId.slice(5, 7)) - 1] || periodId;
      return `<div class="route-estimate-month"><p class="route-estimate-month-label">${esc(monthName)}</p>${lines}</div>`;
    })
    .join("");
  return carrierHeaderHtml() + body;
}

function directionDetails(route: Route): string {
  return route.passengers_estimated && (route.monthly || []).length
    ? estimateDetails(route)
    : carrierHeaderHtml() +
        routeDirections(route)
          .map(
            ({ origin, destination, direction }) => `
    <div class="route-direction-line">
      <span class="route-direction-name">${esc(origin)} → ${esc(destination)}</span>
      ${directionValue(direction, "passengers", route)}
      ${directionValue(direction, "seats", route)}
      ${directionValue(direction, "departures", route)}
      ${directionValue(direction, "load_factor", route)}
    </div>`
          )
          .join("");
}

export function renderRouteTable(title: string, subtitle: string, tableRoutes: Route[], subtitleHtml: string | null = null): void {
  if (state.network?.mode === "scheduled_domestic") {
    renderDomesticRouteTable(title, subtitle, tableRoutes, subtitleHtml);
    return;
  }
  $("airport-tooltip")!.innerHTML = `
    <div class="airport-title-row">
      <h3>${esc(title)}</h3>
      <button type="button" class="airport-search-toggle" id="airport-search-toggle" aria-label="Buscar aeropuerto por código o ciudad" aria-expanded="false" aria-controls="airport-search-box">
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"></circle><path d="m15.5 15.5 5 5"></path></svg>
      </button>
    </div>
    <div class="airport-search-box" id="airport-search-box" hidden>
      <label class="sr-only" for="airport-search-input">Código de aeropuerto o ciudad</label>
      <input id="airport-search-input" type="search" autocomplete="off" placeholder="Código o ciudad">
      <div class="airport-search-results" id="airport-search-results" role="listbox" aria-label="Aeropuertos encontrados"></div>
    </div>
    <p class="airport-meta">${subtitleHtml || esc(subtitle)}</p>
    <div class="airport-table-wrap">
      <table class="airport-route-table">
        <thead><tr><th>Ruta</th><th class="${state.network?.mode === "estimated_domestic" ? "th-with-badge" : ""}">${state.network?.mode === "estimated_domestic" ? `Pasajeros<span class="estimate-info-badge" title="${esc(ESTIMATE_INFO_TITLE)}" aria-label="${esc(ESTIMATE_INFO_TITLE)}" role="img"><svg viewBox="0 0 10 10" aria-hidden="true"><circle cx="5" cy="2.6" r="1.15"></circle><rect x="4.1" y="4.35" width="1.8" height="4.35" rx="0.9"></rect></svg></span>` : "Pasajeros"}</th><th>Asientos</th><th>Vuelos</th><th>Ocupación</th></tr></thead>
        <tbody>${tableRoutes.map((route, index) => `<tr class="route-summary-row" style="--route-color:${airportRouteColor(index)}">
          <td><button type="button" class="route-expand-toggle" aria-expanded="false" aria-controls="route-directions-${index}"><span class="route-expand-icon" aria-hidden="true">&gt;</span><strong class="route-table-name">${esc(routeTitle(route))}</strong>${coverageDotHtml(route)}${scheduledIconHtml(route)}</button></td>
          ${metricCell(route, "passengers")}
          ${metricCell(route, "seats")}
          ${metricCell(route, "departures")}
          ${metricCell(route, "load_factor")}
        </tr><tr class="route-direction-detail" id="route-directions-${index}" style="--route-color:${airportRouteColor(index)}" hidden><td colspan="5">${directionDetails(route)}</td></tr>`).join("")}</tbody>
      </table>
    </div>
    ${sourceFooterHtml(tableRoutes)}`;
  bindExpandToggles();
  bindAirportSearchControls();
}

// isPinned is accepted (not read) to keep the same call signature as the
// original renderAirportTooltip(airport, incident, isPinned).
export function renderAirportTooltip(airport: string, incident: Route[], _isPinned?: boolean): void {
  const airportData = state.network?.airports.find((item) => item.iata === airport);
  const routeCount = `${incident.length} ${incident.length === 1 ? "ruta" : "rutas"}`;
  const metaHtml = `${esc(state.network?.period_label ?? "")} · ${esc(routeCount)} · Selecciona el destino para ver el detalle.`;
  renderRouteTable(`${airport} · ${airportData?.city || "Aeropuerto"}`, "", incident, metaHtml);
}
