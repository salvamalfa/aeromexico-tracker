import { beforeEach, describe, expect, it } from "vitest";
import { renderNetworkVolume } from "./volume";
import { state } from "./state";
import type { Route } from "../../types/domain";

const route = (departures: number | null, operation_status: string, extra = {}): Route => ({
  market_key: "CUN<>MEX", origin: { iata: "MEX" }, destination: { iata: "CUN" },
  passengers: 987654, seats: 999999, load_factor: .98, departures, operation_status, ...extra,
} as unknown as Route);

describe("flight-only map totals", () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="network-volume"></div>';
    state.presenceOnlyRouteCount = 0;
    state.routes = [];
  });
  it("retains historical estimates but never displays route passengers or occupancy", () => {
    state.routes = [route(100, "estimated_from_afac_margins_and_temporal_support")];
    renderNetworkVolume();
    const html = document.getElementById("network-volume")!.innerHTML;
    expect(html).toContain("Vuelos estimados");
    expect(html).toContain("<strong>100</strong>");
    expect(html).not.toMatch(/Pasajeros|Ocupación|987,654|98%/);
  });
  it("never adds observations, schedules, estimates and attributed market totals together", () => {
    state.routes = [route(1000,"operated_observed"), route(300,"assigned_slot_not_flown"),
      route(20,"scheduled_from_dated_release"), route(40,"estimated_from_sample"),
      route(50,"carrier_inferred_market_observed")];
    renderNetworkVolume();
    const html = document.getElementById("network-volume")!.innerHTML;
    for (const value of ["1,000","320","40","50"]) expect(html).toContain(`<strong>${value}</strong>`);
    expect(html).not.toContain("1,410");
    expect(html).toContain("Vuelos atribuidos");
  });
  it("seat enrichment never changes official flight classification", () => {
    state.routes = [route(25,"operated_observed", {capacity_estimated:true})];
    renderNetworkVolume();
    const html = document.getElementById("network-volume")!.innerHTML;
    expect(html).toContain("Vuelos observados");
    expect(html).not.toContain("Vuelos estimados");
  });
  it("a BTS fleet reference never turns model frequencies into observed flights", () => {
    state.routes = [route(25,"estimated_from_sample", {source_label:"AeroDataBox + BTS T-100 fleet gauge"})];
    renderNetworkVolume();
    const html = document.getElementById("network-volume")!.innerHTML;
    expect(html).toContain("Vuelos estimados");
    expect(html).not.toContain("Vuelos observados");
  });
  it("keeps unknown flights as N/D and discloses routes without a value", () => {
    state.presenceOnlyRouteCount = 8;
    renderNetworkVolume();
    const host = document.getElementById("network-volume")!;
    expect(host.hidden).toBe(false);
    expect(host.innerHTML).toContain("<strong>N/D</strong>");
    expect(host.innerHTML).not.toContain("<strong>0</strong>");
  });
  it("hides the empty summary", () => {
    renderNetworkVolume();
    expect(document.getElementById("network-volume")!.hidden).toBe(true);
  });
});
