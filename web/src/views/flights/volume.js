// Network volume summary line above the route table. Ported from
// src/dashboard/assets/flights.js::renderNetworkVolume.

import { $, esc, finite, integer } from "./dom.js";
import { state } from "./state.js";
import { REGIONS } from "./regions.js";

export function renderNetworkVolume() {
  const host = $("network-volume");
  if (!host) return;
  const shown = state.routes || [];
  // Vuelos estimados de AeroDataBox (Grupo Aeroméxico) no son vuelos
  // operados observados de Aerovías: no entran a ese conteo.
  const observedFlights = (route) => route.operation_status !== "estimated_from_afac_margins_and_aerodatabox_seed";
  const flights = shown.reduce((sum, route) => sum + (observedFlights(route) && finite(route.departures) ? route.departures : 0), 0);
  const passengers = shown.reduce((sum, route) => sum + (finite(route.passengers) ? route.passengers : 0), 0);
  const passengersLow = shown.reduce((sum, route) => sum + (finite(route.passengers_low) ? route.passengers_low : 0), 0);
  const passengersHigh = shown.reduce((sum, route) => sum + (finite(route.passengers_high) ? route.passengers_high : 0), 0);
  const noBreakdown = shown.filter((route) => !finite(route.departures)).length;
  host.hidden = shown.length === 0;
  if (host.hidden) { host.innerHTML = ""; return; }
  const scope = state.networkMode === "domestic"
    ? "en la red nacional"
    : state.selectedRegion
      ? `hacia ${REGIONS.find((region) => region.id === state.selectedRegion)?.label || ""}`
      : "en la red internacional";
  if (state.network.mode === "estimated_domestic") {
    const repaired = shown.some((route) => route.support_repair_applied);
    host.innerHTML = `<strong>${integer.format(passengers)}</strong><span>pasajeros estimados de Grupo Aeroméxico ${esc(scope)} · ${esc(state.network.period_label)} · sensibilidad ${integer.format(passengersLow)}–${integer.format(passengersHigh)}${repaired ? " · soporte de rutas completado con meses cercanos" : ""}</span>`;
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
  const estimatedPassengers = estimated.reduce((sum, route) => sum + route.passengers, 0);
  const estimatedLine = estimated.length
    ? `<span class="network-estimate-note">${integer.format(estimatedPassengers)} pasajeros estimados de Aerovías de México y Aeroméxico Connect en ${estimated.length} ${estimated.length === 1 ? "ruta" : "rutas"} sin pasajeros observados (AFAC + AeroDataBox)</span>`
    : "";
  host.innerHTML = `<strong>${integer.format(flights)}</strong><span>vuelos operados por Aerovías de México (no incluye Aeroméxico Connect) ${esc(scope)} · ${esc(state.network.period_label)}${noBreakdown ? ` · ${noBreakdown} ${noBreakdown === 1 ? "ruta" : "rutas"} sin desglose propio` : ""}</span>${estimatedLine}`;
}
