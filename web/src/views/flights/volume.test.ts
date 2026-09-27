import { beforeEach, describe, expect, it } from "vitest";
import { renderNetworkVolume } from "./volume";
import { state } from "./state";
import type { Route } from "../../types/domain";

function domesticRoute(overrides: Partial<Route>): Route {
  return {
    market_key: "MEX-CUN",
    origin: { iata: "MEX", city: "Ciudad de México", lat: 19.4, lon: -99.1 },
    destination: { iata: "CUN", city: "Cancún", lat: 21.0, lon: -86.8 },
    passengers: 100_000,
    passengers_estimated: true,
    ...overrides,
  } as unknown as Route;
}

describe("renderNetworkVolume (quarterly network indicators)", () => {
  beforeEach(() => {
    document.body.innerHTML = `<div id="network-volume"></div>`;
    state.networkMode = "domestic";
    state.network = { mode: "estimated_domestic", period_label: "abril 2026" } as unknown as typeof state.network;
    state.quarters = [{ period_id: "2026Q2", period_label: "2T26" }] as typeof state.quarters;
    state.periodIndex = 0;
    state.monthlyPassengers = { records: [
      { date: "2026-04-01", domestic: 50_000, international: 20_000, total_segment_sum: 70_000 },
      { date: "2026-05-01", domestic: 50_000, international: 20_000, total_segment_sum: 70_000 },
      { date: "2026-06-01", domestic: 50_000, international: 20_000, total_segment_sum: 70_000 },
    ] };
  });

  it("shows the sum as estimated passengers with the selected quarter", () => {
    state.routes = [
      domesticRoute({ passengers: 100_000, passengers_low: 90_000, passengers_high: 110_000 }),
      domesticRoute({ passengers: 50_000, passengers_low: 45_000, passengers_high: 55_000 }),
    ];
    renderNetworkVolume();
    const html = document.getElementById("network-volume")!.innerHTML;
    expect(html).toContain("PASAJEROS");
    expect(html).toContain("<strong>150,000</strong>");
    expect(html).toContain("RED NACIONAL");
    expect(html).toContain("AFAC · Grupo");
  });

  it("does not add method text to the compact total", () => {
    state.routes = [
      domesticRoute({ passengers: 100_000, passengers_low: 90_000, passengers_high: 110_000 }),
      // A repaired route whose Gold record carries no scenario identity.
      domesticRoute({ passengers: 50_000, passengers_low: null, passengers_high: null }),
    ];
    renderNetworkVolume();
    const html = document.getElementById("network-volume")!.innerHTML;
    expect(html).not.toContain("Alcance y método");
    expect(html).not.toContain("meses seleccionados");
  });
});

describe("renderNetworkVolume (observed vs scheduled vs inferred flights)", () => {
  beforeEach(() => {
    document.body.innerHTML = `<div id="network-volume"></div>`;
    state.networkMode = "international";
    state.selectedRegion = null;
    state.presenceOnlyRouteCount = 0;
    state.network = { mode: "international", period_label: "2T26" } as unknown as typeof state.network;
    state.quarters = [{ period_id: "2026Q2", period_label: "2T26" }] as typeof state.quarters;
    state.periodIndex = 0;
    state.monthlyPassengers = { records: [
      { date: "2026-04-01", domestic: 50_000, international: 20_000, total_segment_sum: 70_000 },
      { date: "2026-05-01", domestic: 50_000, international: 20_000, total_segment_sum: 70_000 },
      { date: "2026-06-01", domestic: 50_000, international: 20_000, total_segment_sum: 70_000 },
    ] };
  });

  it("counts only observed flights in the headline", () => {
    state.routes = [
      domesticRoute({ passengers_estimated: false, departures: 1_000, operation_status: "operated_observed" }),
      domesticRoute({ passengers_estimated: false, departures: 300, operation_status: "assigned_slot_not_flown" }),
      domesticRoute({ passengers_estimated: false, departures: 20, operation_status: "scheduled_from_dated_release" }),
      domesticRoute({ passengers_estimated: false, departures: 50, operation_status: "carrier_inferred_market_observed" }),
    ];
    renderNetworkVolume();
    const html = document.getElementById("network-volume")!.innerHTML;
    expect(html).toContain("<strong>1,000</strong>");
    expect(html).not.toContain("1,370");
    expect(html).toContain("VUELOS");
    expect(html).toContain("obs. · 1/4 rutas");
  });

  it("does not add presence-only routes to the observed total", () => {
    state.presenceOnlyRouteCount = 9;
    state.routes = [domesticRoute({ passengers_estimated: false, departures: 10, operation_status: "operated_observed" })];
    renderNetworkVolume();
    const html = document.getElementById("network-volume")!.innerHTML;
    expect(html).toContain("<strong>10</strong>");
  });

  it("shows N/D, not zero, when no shown route has observed flights", () => {
    state.routes = [
      domesticRoute({ passengers_estimated: false, departures: 300, operation_status: "assigned_slot_not_flown" }),
      domesticRoute({ passengers_estimated: false, departures: 50, operation_status: "carrier_inferred_market_observed" }),
    ];
    renderNetworkVolume();
    const host = document.getElementById("network-volume")!;
    expect(host.innerHTML).toContain("<strong>N/D</strong>");
    expect(host.innerHTML).not.toContain("<strong>0</strong>");
  });

  it("shows N/D when only presence-only routes are documented", () => {
    state.presenceOnlyRouteCount = 8;
    state.routes = [];
    renderNetworkVolume();
    const host = document.getElementById("network-volume")!;
    expect(host.hidden).toBe(false);
    expect(host.innerHTML).toContain("<strong>N/D</strong>");
  });

  it("stays hidden when there is nothing to report", () => {
    state.presenceOnlyRouteCount = 0;
    state.routes = [];
    state.monthlyPassengers = null;
    renderNetworkVolume();
    expect(document.getElementById("network-volume")!.hidden).toBe(true);
  });
});
