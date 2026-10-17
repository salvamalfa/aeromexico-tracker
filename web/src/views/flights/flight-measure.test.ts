import { describe, expect, it } from "vitest";
import type { Route } from "../../types/domain";
import { flightBreakdown, flightKind, flightTotals } from "./flight-measure";

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
    expect(flightBreakdown(route)).toBe("30 observados · 15 estimados · 8 programados");
  });
  it("does not classify an explicit observed zero as missing", () => {
    const zero = { ...route, departures: 0, flight_components: [{ ...route.flight_components![0]!, departures: 0 }] };
    expect(flightKind(zero)).toBe("observed");
    expect(flightTotals(zero)).toEqual({ observed: 0 });
  });
});
