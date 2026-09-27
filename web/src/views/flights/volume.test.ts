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

describe("renderNetworkVolume (estimated_domestic aggregate range)", () => {
  beforeEach(() => {
    document.body.innerHTML = `<div id="network-volume"></div>`;
    state.networkMode = "domestic";
    state.network = { mode: "estimated_domestic", period_label: "abril 2026" } as unknown as typeof state.network;
  });

  it("shows the summed sensitivity range when every shown route has one", () => {
    state.routes = [
      domesticRoute({ passengers: 100_000, passengers_low: 90_000, passengers_high: 110_000 }),
      domesticRoute({ passengers: 50_000, passengers_low: 45_000, passengers_high: 55_000 }),
    ];
    renderNetworkVolume();
    const html = document.getElementById("network-volume")!.innerHTML;
    expect(html).toContain("135,000–165,000");
  });

  it("withholds the aggregate range (never fabricates a zero-based one) when any shown route lacks a bound", () => {
    state.routes = [
      domesticRoute({ passengers: 100_000, passengers_low: 90_000, passengers_high: 110_000 }),
      // A repaired route whose Gold record carries no scenario identity.
      domesticRoute({ passengers: 50_000, passengers_low: null, passengers_high: null }),
    ];
    renderNetworkVolume();
    const html = document.getElementById("network-volume")!.innerHTML;
    expect(html).not.toContain("90,000");
    expect(html).not.toContain("–110,000");
    expect(html).toContain("rango de sensibilidad no disponible");
  });
});

describe("renderNetworkVolume (observed vs scheduled vs inferred flights)", () => {
  beforeEach(() => {
    document.body.innerHTML = `<div id="network-volume"></div>`;
    state.networkMode = "international";
    state.selectedRegion = null;
    state.presenceOnlyRouteCount = 0;
    state.network = { mode: "international", period_label: "2T26" } as unknown as typeof state.network;
  });

  it("counts only observed flights in the headline and lists scheduled and inferred apart", () => {
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
    expect(html).toContain("320 vuelos programados en 2 rutas");
    expect(html).toContain("50 vuelos de mercado AFAC atribuidos por exclusividad en 1 ruta");
  });

  it("discloses presence-only routes instead of silently dropping them", () => {
    state.presenceOnlyRouteCount = 9;
    state.routes = [domesticRoute({ passengers_estimated: false, departures: 10, operation_status: "operated_observed" })];
    renderNetworkVolume();
    const html = document.getElementById("network-volume")!.innerHTML;
    expect(html).toContain("9 rutas con presencia documentada de Aeroméxico sin volumen atribuible (N/D)");
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

  it("renders the presence-only disclosure even when no route is quantified", () => {
    state.presenceOnlyRouteCount = 8;
    state.routes = [];
    renderNetworkVolume();
    const host = document.getElementById("network-volume")!;
    expect(host.hidden).toBe(false);
    expect(host.innerHTML).toContain("8 rutas con presencia documentada");
    expect(host.innerHTML).toContain("<strong>N/D</strong>");
  });

  it("stays hidden when there is nothing to report", () => {
    state.presenceOnlyRouteCount = 0;
    state.routes = [];
    renderNetworkVolume();
    expect(document.getElementById("network-volume")!.hidden).toBe(true);
  });
});
