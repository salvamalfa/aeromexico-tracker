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
