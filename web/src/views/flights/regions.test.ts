import { describe, expect, it } from "vitest";
import { airportRegion, isMexican, normalizeSelectedRegion, renderRegionSwitch, routeRegion } from "./regions";
import { state } from "./state";
import type { Airport, Route } from "../../types/domain";

const airport = (iata: string, lat: number, lon: number): Airport => ({ iata, city: iata, lat, lon });

describe("isMexican", () => {
  it("classifies an airport inside the Mexican bounding box", () => {
    expect(isMexican(airport("MEX", 19.4, -99.1))).toBe(true);
  });
  it("classifies an airport outside the bounding box as not Mexican", () => {
    expect(isMexican(airport("JFK", 40.6, -73.8))).toBe(false);
  });
});

describe("airportRegion", () => {
  it("maps a listed airport to its region", () => {
    expect(airportRegion("MAD")).toBe("europa");
    expect(airportRegion("GRU")).toBe("sudamerica");
    expect(airportRegion("NRT")).toBe("asia");
  });
  it("defaults unlisted airports to norteamerica", () => {
    expect(airportRegion("JFK")).toBe("norteamerica");
  });
});

describe("routeRegion", () => {
  it("classifies by the non-Mexican endpoint when origin is Mexican", () => {
    const route = { origin: airport("MEX", 19.4, -99.1), destination: airport("MAD", 40.5, -3.6) } as Route;
    expect(routeRegion(route)).toBe("europa");
  });
  it("classifies by the non-Mexican endpoint when destination is Mexican", () => {
    const route = { origin: airport("GRU", -23.4, -46.5), destination: airport("MEX", 19.4, -99.1) } as Route;
    expect(routeRegion(route)).toBe("sudamerica");
  });
});

describe("normalizeSelectedRegion", () => {
  const toMadrid = { origin: airport("MEX", 19.4, -99.1), destination: airport("MAD", 40.5, -3.6) } as Route;
  const toNewYork = { origin: airport("MEX", 19.4, -99.1), destination: airport("JFK", 40.6, -73.8) } as Route;

  it("clears a region that has no routes in the new period", () => {
    state.selectedRegion = "europa";
    normalizeSelectedRegion([toNewYork]);
    expect(state.selectedRegion).toBeNull();
  });
  it("keeps a region that still has routes", () => {
    state.selectedRegion = "europa";
    normalizeSelectedRegion([toNewYork, toMadrid]);
    expect(state.selectedRegion).toBe("europa");
  });
  it("keeps a region whose only routes are presence-only when judged on all routes", () => {
    const presenceOnly = { ...toMadrid, departures: null, operation_status: "carrier_route_present_volume_unresolved" } as unknown as Route;
    state.selectedRegion = "europa";
    normalizeSelectedRegion([toNewYork, presenceOnly]);
    expect(state.selectedRegion).toBe("europa");
  });
});

describe("renderRegionSwitch", () => {
  it("offers a region whose only routes are presence-only", () => {
    document.body.innerHTML = `<div id="network-region-switch"></div>`;
    const toNewYork = { origin: airport("MEX", 19.4, -99.1), destination: airport("JFK", 40.6, -73.8), departures: 10 } as unknown as Route;
    const presenceToMadrid = { origin: airport("MTY", 25.8, -100.1), destination: airport("MAD", 40.5, -3.6), departures: null } as unknown as Route;
    state.networkMode = "international";
    state.selectedRegion = null;
    state.networkAllRoutes = [toNewYork, presenceToMadrid];
    state.network = { mode: "international", routes: [toNewYork] } as unknown as typeof state.network;
    renderRegionSwitch();
    expect(document.querySelector('[data-region="europa"]')).not.toBeNull();
  });
});
