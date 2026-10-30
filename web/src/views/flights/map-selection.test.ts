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
    flight_type_code: "S", traffic_code: "I", components: [{
      operator_icao: "AMX", commercial_designator_as_reported: "AMX", origin_iata: "MEX",
      destination_iata: "GDL", period_id: "2026M07", operations: 347,
      source_hash: "a".repeat(64), source_locator: "record:0",
    }],
  };
  const merged = mergeCarrierNetworks([network("VOLARIS"), am]).routes[0]!;
  expect(merged.departures).toBe(8);
  expect(merged.recorded_movements!.count).toBe(347);
  const duplicate = network("VIVA_AEROBUS");
  duplicate.routes[0]!.recorded_movements = am.routes[0]!.recorded_movements;
  expect(() => mergeCarrierNetworks([am, duplicate])).toThrow(/Movimientos.*duplicados/);
});

// Native b77f81b0 source cells already checked by the scoped July/history producer.
type Cell = readonly [string, string, number, number, number];
const q2Hash = "b77f81b0acae11f94de6f028acb1a56a243105da8ddaabf63f5d26790dc6594c";
const vivaCells: Cell[] = [["BOG", "GDL", 4, 11, 9], ["BOG", "GDL", 6, 15, 56],
  ["GDL", "BOG", 4, 11, 1], ["GDL", "BOG", 6, 15, 47]];
const volarisCells: Cell[] = [["BOG", "GDL", 4, 8, 10], ["BOG", "GDL", 5, 10, 34], ["BOG", "GDL", 6, 9, 57],
  ["GDL", "BOG", 4, 8, 2], ["GDL", "BOG", 5, 10, 27], ["GDL", "BOG", 6, 9, 48]];
const amCells: Cell[] = [["BOG", "MEX", 4, 90, 11], ["BOG", "MEX", 5, 93, 35], ["BOG", "MEX", 6, 93, 59],
  ["MEX", "BOG", 4, 89, 3], ["MEX", "BOG", 5, 93, 28], ["MEX", "BOG", 6, 94, 49]];
function movementNetwork(carrier: string, operator: string, cells: Cell[]): PeriodNetworkDocument {
  const result = network(carrier), route = result.routes[0]!;
  const endpoints = [cells[0]![0], cells[0]![1]].sort();
  route.market_key = endpoints.join("<>");
  route.origin = { ...route.origin, iata: endpoints[0]! };
  route.destination = { ...route.destination, iata: endpoints[1]! };
  route.departures = null; route.flight_components = []; route.directions = [];
  route.operation_status = "recorded_movements_provisional";
  route.recorded_movements = {
    count: cells.reduce((sum, cell) => sum + cell[3], 0), source_label: "Aerocivil", definition: "No salidas",
    observed_months: [...new Set(cells.map((cell) => `2026M0${cell[2]}`))].sort(),
    provisional: true, official_classification_confirmed: false, agent_eligible: false,
    flight_type_code: "S", traffic_code: "I", components: cells.map(([origin_iata, destination_iata, month, operations, locator]) => ({
      operator_icao: operator, commercial_designator_as_reported: operator, origin_iata, destination_iata,
      period_id: `2026M0${month}`, operations, source_hash: q2Hash, source_locator: `record:${locator}`,
    })),
  };
  return result;
}
it("combines real Viva and Volaris cells in one market without converting movements to flights", () => {
  const inputs = [movementNetwork("VIVA_AEROBUS", "VIV", vivaCells), movementNetwork("VOLARIS", "VOI", volarisCells)];
  const before = JSON.stringify(inputs);
  const merged = mergeCarrierNetworks(inputs).routes[0]!;
  expect(merged.recorded_movements!.count).toBe(106);
  expect(merged.recorded_movements!.components).toHaveLength(10);
  expect(merged.recorded_movements!.observed_months).toEqual(["2026M04", "2026M05", "2026M06"]);
  expect(merged.recorded_movements!.official_classification_confirmed).toBe(false);
  expect(merged.departures).toBeNull(); expect(merged.flight_components).toEqual([]);
  expect(merged.operation_status).toBe("recorded_movements_provisional");
  expect(JSON.stringify(inputs)).toBe(before);
  expect(mergeCarrierNetworks([...inputs].reverse()).routes[0]!.recorded_movements).toEqual(merged.recorded_movements);
});
it("keeps three selected carriers and distinct markets while merging the shared evidence", () => {
  const merged = mergeCarrierNetworks([movementNetwork("AEROMEXICO", "AMX", amCells),
    movementNetwork("VIVA_AEROBUS", "VIV", vivaCells), movementNetwork("VOLARIS", "VOI", volarisCells)]);
  expect(merged.routes.find((r) => r.market_key === "BOG<>GDL")!.recorded_movements!.count).toBe(106);
  expect(merged.routes.find((r) => r.market_key === "BOG<>MEX")!.recorded_movements!.count).toBe(552);
  expect(merged.routes.every((r) => r.departures === null)).toBe(true);
});
it("preserves explicit zero movements without inventing missing flight counts", () => {
  const route = mergeCarrierNetworks([movementNetwork("VIVA_AEROBUS", "VIV", [["BOG", "GDL", 4, 0, 9]])]).routes[0]!;
  expect(route.recorded_movements!.count).toBe(0); expect(route.departures).toBeNull();
});
it.each(["grain", "vintage", "evidence"])("rejects duplicate or aliased native observations: %s", (damage) => {
  const a = movementNetwork("VIVA_AEROBUS", "VIV", vivaCells);
  const b = movementNetwork("VOLARIS", "VOI", vivaCells);
  if (damage !== "evidence") {
    b.routes[0]!.recorded_movements!.components.forEach((c) => { c.operator_icao = "VIV"; c.commercial_designator_as_reported = "VIV"; });
    if (damage === "vintage") b.routes[0]!.recorded_movements!.components.forEach((c) => { c.source_hash = "f".repeat(64); });
  }
  expect(() => mergeCarrierNetworks([a, b])).toThrow(/duplicados|superpuestas/);
});
it.each(["count", "months", "definition", "missing", "hash"])("rejects an unreconciled or incompatible movement payload: %s", (damage) => {
  const a = movementNetwork("VIVA_AEROBUS", "VIV", vivaCells), b = movementNetwork("VOLARIS", "VOI", volarisCells);
  const measure = b.routes[0]!.recorded_movements!;
  if (damage === "count") measure.count += 1;
  else if (damage === "months") measure.observed_months = ["2026M07"];
  else if (damage === "definition") measure.definition = "Vuelos regulares oficiales";
  else if (damage === "missing") measure.components[0]!.operations = NaN;
  else measure.components[0]!.source_hash = "not-an-original-sha";
  expect(() => mergeCarrierNetworks([a, b])).toThrow(/Movimientos/);
});
