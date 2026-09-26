// International region grouping and the region switch UI. Ported from
// src/dashboard/assets/flights.js (REGION_MEMBERS, REGIONS, airportRegion,
// isMexican, routeRegion, regionRoutes, renderRegionSwitch).

import { $, esc } from "./dom";
import { state } from "./state";
import { renderNetworkPeriod } from "./network";
import type { Airport, Route } from "../../types/domain";

const REGION_MEMBERS: Record<string, string[]> = {
  asia: ["ICN", "NRT"],
  europa: ["AMS", "BCN", "CDG", "FCO", "LHR", "MAD"],
  sudamerica: ["BOG", "CLO", "CTG", "EZE", "GRU", "LIM", "MDE", "SCL", "UIO"],
};

export interface RegionDefinition {
  id: string;
  label: string;
  lat: [number, number];
  lon: [number, number];
  dtick: number;
}

export const REGIONS: RegionDefinition[] = [
  { id: "norteamerica", label: "Norteamérica", lat: [8, 62], lon: [-170, -52], dtick: 15 },
  { id: "sudamerica", label: "Sudamérica", lat: [-56, 16], lon: [-84, -33], dtick: 15 },
  { id: "europa", label: "Europa", lat: [34, 60], lon: [-12, 22], dtick: 10 },
  { id: "asia", label: "Asia", lat: [24, 44], lon: [122, 142], dtick: 5 },
];

export function airportRegion(iata: string): string {
  for (const [id, members] of Object.entries(REGION_MEMBERS)) if (members.includes(iata)) return id;
  return "norteamerica";
}

export function isMexican(airport: Airport): boolean {
  return airport.lat >= 14 && airport.lat <= 33 && airport.lon >= -118 && airport.lon <= -86;
}

export function routeRegion(route: Route): string {
  if (isMexican(route.origin)) return airportRegion(route.destination.iata);
  if (isMexican(route.destination)) return airportRegion(route.origin.iata);
  return airportRegion(route.destination.iata);
}

export function regionRoutes(allRoutes: Route[]): Route[] {
  if (state.networkMode !== "international" || !state.selectedRegion) return allRoutes;
  return allRoutes.filter((route) => routeRegion(route) === state.selectedRegion);
}

export function renderRegionSwitch(): void {
  const host = $("network-region-switch");
  if (!host) return;
  host.hidden = state.networkMode !== "international";
  if (host.hidden) {
    host.innerHTML = "";
    return;
  }
  const routes = state.network?.routes ?? [];
  const available = REGIONS.filter((region) => routes.some((route) => routeRegion(route) === region.id));
  host.innerHTML = available
    .map(
      (region) =>
        `<button type="button" data-region="${region.id}" aria-pressed="${String(state.selectedRegion === region.id)}">${esc(region.label)}</button>`
    )
    .join("");
  host.querySelectorAll("button").forEach((button) =>
    button.addEventListener("click", async () => {
      const id = (button as HTMLElement).dataset.region ?? null;
      state.selectedRegion = state.selectedRegion === id ? null : id;
      await renderNetworkPeriod(state.quarters[state.periodIndex]!.period_id);
    })
  );
}
