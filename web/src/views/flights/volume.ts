// Network volume summary line above the route table. Ported from
// src/dashboard/assets/flights.js::renderNetworkVolume.

import { $, esc, finite, integer, sensitivityRange } from "./dom";
import { state } from "./state";
import { REGIONS } from "./regions";
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
  const observedFlights = (route: Route) => route.operation_status !== "estimated_from_afac_margins_and_aerodatabox_seed";
  const flights = shown.reduce((sum, route) => sum + (observedFlights(route) && finite(route.departures) ? route.departures : 0), 0);
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
  if (state.network?.mode === "estimated_domestic") {
    const repaired = shown.some((route) => route.support_repair_applied);
    const range = sensitivityRange(passengersLow, passengersHigh);
    const rangeText = range
      ? ` · sensibilidad ${integer.format(range.low)}–${integer.format(range.high)}`
      : " · rango de sensibilidad no disponible";
    host.innerHTML = `<strong>${integer.format(passengers)}</strong><span>pasajeros estimados de Grupo Aeroméxico ${esc(scope)} · ${esc(state.network.period_label)}${rangeText}${repaired ? " · soporte de rutas completado con meses cercanos" : ""}</span>`;
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
  host.innerHTML = `<strong>${integer.format(flights)}</strong><span>vuelos operados por Aerovías de México (no incluye Aeroméxico Connect) ${esc(scope)} · ${esc(state.network?.period_label ?? "")}${noBreakdown ? ` · ${noBreakdown} ${noBreakdown === 1 ? "ruta" : "rutas"} sin desglose propio` : ""}</span>${estimatedLine}`;
}
