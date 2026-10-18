import { describe, expect, it } from "vitest";
import type { Route } from "../../types/domain";
import { flightBreakdown, flightKind, flightTotals, flightScheduleNote } from "./flight-measure";

const route = {
  market_key: "JFK<>MEX", origin: { iata: "MEX", city: "MEX", lat: 1, lon: 1 }, destination: { iata: "JFK", city: "JFK", lat: 2, lon: 2 },
  departures: 45, operation_status: "mixed_observed_estimated_cells", source_label: "BTS T-100 + AeroDataBox",
  flight_components: [
    { carrier_key: "AEROMEXICO", origin_iata: "MEX", destination_iata: "JFK", period_id: "2026M04", kind: "observed", departures: 30, source_label: "BTS T-100", source_hashes: [] },
    { carrier_key: "AEROMEXICO_CONNECT", origin_iata: "MEX", destination_iata: "JFK", period_id: "2026M06", kind: "estimated", departures: 15, source_label: "AeroDataBox", source_hashes: [] },
    { carrier_key: "AEROMEXICO_GROUP", origin_iata: "JFK", destination_iata: "MEX", period_id: "2026M06", kind: "scheduled", departures: 8, source_label: "AICM", source_hashes: [] },
  ],
} as Route;

describe("flight cell presentation", () => {
  it("keeps observed, estimated and scheduled totals separate in mixed markets", () => {
    expect(flightKind(route)).toBe("mixed");
    expect(flightTotals(route)).toEqual({ observed: 30, estimated: 15, scheduled: 8 });
    expect(flightBreakdown(route)).toBe("30 observados · 15 estimados");
    expect(flightScheduleNote(route)).toBe("8 programados (fuera del total)");
  });
  it("does not classify an explicit observed zero as missing", () => {
    const zero = { ...route, departures: 0, flight_components: [{ ...route.flight_components![0]!, departures: 0 }] };
    expect(flightKind(zero)).toBe("observed");
    expect(flightTotals(zero)).toEqual({ observed: 0 });
  });
});

describe("schedule headline boundary", () => {
  it("retains scheduled-only routes as the headline measure", () => {
    const scheduled = { ...route, departures: 8, flight_components: [route.flight_components![2]!] };
    expect(flightBreakdown(scheduled)).toBe("8 programados");
    expect(flightScheduleNote(scheduled)).toBe("");
  });
  it("does not treat an observed zero as absence of performed information", () => {
    const zero = { ...route, departures: 0, flight_components: [{ ...route.flight_components![0]!, departures: 0 }, route.flight_components![2]!] };
    expect(flightBreakdown(zero)).toBe("0 observados");
    expect(flightScheduleNote(zero)).toBe("8 programados (fuera del total)");
  });
  it("does not invent a schedule note for legacy observed routes", () => {
    const legacy = { ...route, departures: 143, flight_components: undefined, operation_status: "observed_flights" };
    expect(flightBreakdown(legacy)).toBe("143 observados");
    expect(flightScheduleNote(legacy)).toBe("");
  });
  it("explains the actual June LAX-MEX 143 headline separately from its 147 schedules", () => {
    const actual = { ...route, departures: 143, flight_components: [
      { ...route.flight_components![0]!, departures: 143 },
      { ...route.flight_components![2]!, departures: 147 },
    ] };
    expect(flightTotals(actual)).toEqual({ observed: 143, scheduled: 147 });
    expect(flightBreakdown(actual)).toBe("143 observados");
    expect(flightScheduleNote(actual)).toBe("147 programados (fuera del total)");
  });
});
