import { expect, it } from "vitest";
import type { FlightComponent, PeriodNetworkDocument } from "../../types/domain";
import { mergeCarrierNetworks } from "./map-selection";
import { coverageIndicator } from "./coverage";
const component = { carrier_key: "VOLARIS", origin_iata: "MEX", destination_iata: "GDL", period_id: "2026M04", kind: "estimated", departures: 4, source_label: "retained", source_hashes: [] } satisfies FlightComponent;
function network(carrier: string, partial = false): PeriodNetworkDocument {
  const c: FlightComponent = { ...component, carrier_key: carrier };
  const a = { iata: "MEX", city: "CDMX", lat: 1, lon: 2 }, b = { ...a, iata: "GDL" };
  return { mode: "estimated", period_label: "2026Q2", airports: [a, b], routes: [{
    market_key: "GDL<>MEX", origin: a, destination: b, departures: 4,
    operation_status: `estimated_from_frozen_history${partial ? "_partial_frequencies" : ""}`,
    flight_components: [c], directions: [{ origin_iata: "MEX", destination_iata: "GDL", departures: 4 }],
  }] };
}
it("sums distinct operator counts/directions, preserving missing values", () => {
  const r = mergeCarrierNetworks([network("AEROMEXICO"), network("VOLARIS")]).routes[0]!;
  expect(r.departures).toBe(8); expect(r.directions![0]!.departures).toBe(8);
  const empty = network("VOLARIS"); empty.routes[0]!.departures = null;
  expect(mergeCarrierNetworks([empty]).routes[0]!.departures).toBeNull();
});
it("rejects duplicate operator cells and observed/estimate overlaps", () => {
  expect(() => mergeCarrierNetworks([network("VOLARIS"), network("VOLARIS")])).toThrow(/duplicado/);
  const observed = network("VOLARIS"); observed.routes[0]!.flight_components![0]!.kind = "observed";
  expect(() => mergeCarrierNetworks([network("VOLARIS"), observed])).toThrow(/duplicado/);
});
it("keeps partial-frequency warnings even when three months are known", () => {
  const partial = network("VOLARIS", true);
  partial.routes[0]!.flight_components = [4, 5, 6].map((m) => ({ ...component, period_id: `2026M0${m}` }));
  const r = mergeCarrierNetworks([partial, network("AEROMEXICO")]).routes[0]!;
  expect(r.operation_status).toContain("partial_frequencies"); expect(coverageIndicator(r, 3)!.variant).toBe("is-partial");
});
it("preserves movement evidence even when Aeromexico is selected second; never adds it to flights", () => {
  const am = network("AEROMEXICO");
  am.routes[0]!.recorded_movements = {
    count: 347, source_label: "Aerocivil", observed_months: ["2026M07"], definition: "No salidas",
    provisional: true, official_classification_confirmed: false, agent_eligible: false,
    flight_type_code: "S", traffic_code: "I", components: [],
  };
  const merged = mergeCarrierNetworks([network("VOLARIS"), am]).routes[0]!;
  expect(merged.departures).toBe(8);
  expect(merged.recorded_movements!.count).toBe(347);
  const duplicate = network("VIVA_AEROBUS");
  duplicate.routes[0]!.recorded_movements = am.routes[0]!.recorded_movements;
  expect(() => mergeCarrierNetworks([am, duplicate])).toThrow(/Movimientos.*duplicados/);
});
