// Network volume summary line above the route table. Ported from
// src/dashboard/assets/flights.js::renderNetworkVolume.

import { $, esc, finite, integer, sensitivityRange } from "./dom";
import { state } from "./state";
import { REGIONS } from "./regions";
import { SCHEDULED_STATUSES } from "./coverage";
import type { Route } from "../../types/domain";

// Suma un extremo del rango de sensibilidad sobre las rutas contadas en el
// total de pasajeros. Si a cualquiera de esas rutas le falta ese extremo, el
// agregado completo queda sin rango (null) en vez de sustituir el faltante
// por cero: eso fabricaría un rango basado en cero que la fuente no respalda.
function sumSensitivityBound(routes: Route[], key: "passengers_low" | "passengers_high"): number | null {
  let total = 0;
  let counted = false;
  for (const route of routes) {
    if (!finite(route.passengers)) continue;
    counted = true;
    const value = route[key];
    if (!finite(value)) return null;
    total += value;
  }
  return counted ? total : null;
}

export function renderNetworkVolume(): void {
  const host = $("network-volume");
  if (!host) return;
  const shown: Route[] = state.routes || [];
  // Vuelos estimados de AeroDataBox (Grupo Aeroméxico) no son vuelos
  // operados observados de Aerovías: no entran a ese conteo.
  // Programados (slots AICM, anuncio fechado de OMA) e inferidos de mercado
  // AFAC tampoco son vuelos observados: van en líneas aparte, nunca sumados.
  const flightKind = (route: Route): "observed" | "scheduled" | "inferred" | "estimated" => {
    const status = route.operation_status ?? "";
    if (status === "estimated_from_afac_margins_and_aerodatabox_seed") return "estimated";
    if (SCHEDULED_STATUSES.includes(status)) return "scheduled";
    if (status === "carrier_inferred_market_observed") return "inferred";
    return "observed";
  };
  const departuresOf = (kind: ReturnType<typeof flightKind>) => {
    const routes = shown.filter((route) => flightKind(route) === kind && finite(route.departures));
    return { routes: routes.length, total: routes.reduce((sum, route) => sum + (route.departures ?? 0), 0) };
  };
  const flights = departuresOf("observed").total;
  const scheduled = departuresOf("scheduled");
  const inferred = departuresOf("inferred");
  const presenceOnly = state.presenceOnlyRouteCount || 0;
  const passengers = shown.reduce((sum, route) => sum + (finite(route.passengers) ? route.passengers : 0), 0);
  const passengersLow = sumSensitivityBound(shown, "passengers_low");
  const passengersHigh = sumSensitivityBound(shown, "passengers_high");
  const noBreakdown = shown.filter((route) => !finite(route.departures)).length;
  host.hidden = shown.length === 0;
  if (host.hidden) {
    host.innerHTML = "";
    return;
  }
  const scope =
    state.networkMode === "domestic"
      ? "en la red nacional"
      : state.selectedRegion
        ? `hacia ${REGIONS.find((region) => region.id === state.selectedRegion)?.label || ""}`
        : "en la red internacional";
  const routesWord = (count: number) => `${count} ${count === 1 ? "ruta" : "rutas"}`;
  const presenceLine = presenceOnly
    ? `<span class="network-estimate-note">${routesWord(presenceOnly)} con presencia documentada de Aeroméxico sin volumen atribuible (N/D), no ${presenceOnly === 1 ? "dibujada" : "dibujadas"} en el mapa ni en la tabla</span>`
    : "";
  if (state.network?.mode === "estimated_domestic") {
    const repaired = shown.some((route) => route.support_repair_applied);
    const range = sensitivityRange(passengersLow, passengersHigh);
    const rangeText = range
      ? ` · sensibilidad ${integer.format(range.low)}–${integer.format(range.high)}`
      : " · rango de sensibilidad no disponible";
    host.innerHTML = `<strong>${integer.format(passengers)}</strong><span>pasajeros estimados de Grupo Aeroméxico ${esc(scope)} · ${esc(state.network.period_label)}${rangeText}${repaired ? " · soporte de rutas completado con meses cercanos" : ""}</span>${presenceLine}`;
    return;
  }
  // Las fuentes internacionales (BTS T-100, ANAC, Aerocivil, CAA, Aena)
  // solo reportan al operador Aerovías de México (AMX). Aeroméxico Connect
  // no aparece en ninguna de ellas para estos periodos, así que esta cifra
  // nunca se presenta como Grupo Aeroméxico.
  // Los pasajeros estimados (AFAC + AeroDataBox) suman Aerovías y Connect y
  // cubren solo rutas sin pasajeros observados: se reportan en una línea
  // aparte y nunca se suman a los vuelos observados de Aerovías.
  const estimated = shown.filter((route) => route.passengers_estimated && finite(route.passengers));
  const estimatedPassengers = estimated.reduce((sum, route) => sum + (route.passengers ?? 0), 0);
  const estimatedLine = estimated.length
    ? `<span class="network-estimate-note">${integer.format(estimatedPassengers)} pasajeros estimados de Aerovías de México y Aeroméxico Connect en ${estimated.length} ${estimated.length === 1 ? "ruta" : "rutas"} sin pasajeros observados (AFAC + AeroDataBox)</span>`
    : "";
  const scheduledLine = scheduled.routes
    ? `<span class="network-estimate-note">${integer.format(scheduled.total)} vuelos programados en ${routesWord(scheduled.routes)} (slots del AICM o anuncio fechado de OMA; la fuente no confirma que se realizaran), no incluidos arriba</span>`
    : "";
  const inferredLine = inferred.routes
    ? `<span class="network-estimate-note">${integer.format(inferred.total)} vuelos de mercado AFAC atribuidos por exclusividad en ${routesWord(inferred.routes)}, no incluidos arriba</span>`
    : "";
  host.innerHTML = `<strong>${integer.format(flights)}</strong><span>vuelos operados por Aerovías de México (no incluye Aeroméxico Connect) ${esc(scope)} · ${esc(state.network?.period_label ?? "")}${noBreakdown ? ` · ${routesWord(noBreakdown)} sin desglose propio` : ""}</span>${estimatedLine}${scheduledLine}${inferredLine}${presenceLine}`;
}
