// International region grouping and the region switch UI. Ported from
// src/dashboard/assets/flights.js (REGION_MEMBERS, REGIONS, airportRegion,
// isMexican, routeRegion, regionRoutes, renderRegionSwitch).

import { $, esc } from "./dom.js";
import { state } from "./state.js";
import { renderNetworkPeriod } from "./network.js";

const REGION_MEMBERS = {
  asia: ["ICN", "NRT"],
  europa: ["AMS", "BCN", "CDG", "FCO", "LHR", "MAD"],
  sudamerica: ["BOG", "CLO", "CTG", "EZE", "GRU", "LIM", "MDE", "SCL", "UIO"],
};

export const REGIONS = [
  { id: "norteamerica", label: "Norteamérica", lat: [8, 62], lon: [-170, -52], dtick: 15 },
  { id: "sudamerica", label: "Sudamérica", lat: [-56, 16], lon: [-84, -33], dtick: 15 },
  { id: "europa", label: "Europa", lat: [34, 60], lon: [-12, 22], dtick: 10 },
  { id: "asia", label: "Asia", lat: [24, 44], lon: [122, 142], dtick: 5 },
];

export function airportRegion(iata) {
  for (const [id, members] of Object.entries(REGION_MEMBERS)) if (members.includes(iata)) return id;
  return "norteamerica";
}

export function isMexican(airport) {
  return airport.lat >= 14 && airport.lat <= 33 && airport.lon >= -118 && airport.lon <= -86;
}

export function routeRegion(route) {
  if (isMexican(route.origin)) return airportRegion(route.destination.iata);
  if (isMexican(route.destination)) return airportRegion(route.origin.iata);
  return airportRegion(route.destination.iata);
}

export function regionRoutes(allRoutes) {
  if (state.networkMode !== "international" || !state.selectedRegion) return allRoutes;
  return allRoutes.filter((route) => routeRegion(route) === state.selectedRegion);
}

export function renderRegionSwitch() {
  const host = $("network-region-switch");
  if (!host) return;
  host.hidden = state.networkMode !== "international";
  if (host.hidden) { host.innerHTML = ""; return; }
  const available = REGIONS.filter((region) => (state.network.routes || []).some((route) => routeRegion(route) === region.id));
  host.innerHTML = available.map((region) => `<button type="button" data-region="${region.id}" aria-pressed="${String(state.selectedRegion === region.id)}">${esc(region.label)}</button>`).join("");
  host.querySelectorAll("button").forEach((button) => button.addEventListener("click", async () => {
    const id = button.dataset.region;
    state.selectedRegion = state.selectedRegion === id ? null : id;
    await renderNetworkPeriod(state.quarters[state.periodIndex].period_id);
  }));
}
