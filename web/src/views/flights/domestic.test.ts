import { beforeEach, describe, expect, it } from "vitest";
import { aggregateDomesticMonths, domesticPeriodLabel } from "./domestic";
import { state } from "./state";
import type { Airport, PeriodNetworkDocument } from "../../types/domain";

const MEX: Airport = { iata: "MEX", city: "Ciudad de México", lat: 19.4, lon: -99.1 };
const CUN: Airport = { iata: "CUN", city: "Cancún", lat: 21.0, lon: -86.8 };

function monthNetwork(
  passengers: number,
  seats: number | null,
  departures: number | null,
  bounds?: { low: number | null; high: number | null }
): PeriodNetworkDocument {
  return {
    mode: "scheduled_domestic",
    period_label: "mes",
    airports: [MEX, CUN],
    routes: [
      {
        market_key: "MEX-CUN",
        origin: MEX,
        destination: CUN,
        passengers,
        passengers_low: bounds ? bounds.low : undefined,
        passengers_high: bounds ? bounds.high : undefined,
        seats: seats ?? undefined,
        departures: departures ?? undefined,
        capacity_estimated: seats !== null && departures !== null,
        source_label: "AFAC",
      },
    ],
  };
}

describe("domesticPeriodLabel", () => {
  beforeEach(() => {
    state.availablePeriods = { domestic: [], domestic_monthly: ["2026-04", "2026-05", "2026-06"], international: [] };
  });

  it("describes a single selected month out of a fully-covered quarter", () => {
    expect(domesticPeriodLabel(["2026-04"], "2026Q2")).toBe("abril 2026 · 1 mes seleccionado");
  });

  it("describes a full quarter of selected months", () => {
    expect(domesticPeriodLabel(["2026-04", "2026-05", "2026-06"], "2026Q2")).toBe(
      "abril–junio 2026 · 3 meses seleccionados"
    );
  });

  it("describes no months with data", () => {
    expect(domesticPeriodLabel([], "2026Q2")).toBe("Sin meses con datos · 0 meses seleccionados");
  });

  it("flags partial calendar coverage when the quarter itself is missing a month", () => {
    state.availablePeriods = { domestic: [], domestic_monthly: ["2026-04", "2026-05"], international: [] };
    expect(domesticPeriodLabel(["2026-04", "2026-05"], "2026Q2")).toBe(
      "abril–mayo 2026 · 2 meses seleccionados · cobertura parcial: 2 de 3 meses"
    );
  });
});

describe("aggregateDomesticMonths official scheduling", () => {
  beforeEach(() => {
    state.availablePeriods = { domestic: [], domestic_monthly: ["2026M04", "2026M05", "2026M06"], international: [] };
    state.domesticMonthsQuarterId = "2026Q2";
    state.domesticMonthlyNetworks = new Map();
  });
  it("keeps scheduling counts without manufacturing passenger or capacity values", () => {
    for (const [id, count] of [["2026M04", 30], ["2026M05", 40], ["2026M06", 50]] as const) {
      const network = monthNetwork(0, null, count);
      network.routes[0]!.passengers = null;
      network.routes[0]!.operation_status = "assigned_slot_not_flown";
      state.domesticMonthlyNetworks.set(id, network);
    }
    const network = aggregateDomesticMonths(["2026M04", "2026M05", "2026M06"])!;
    expect(network.routes[0]!.departures).toBe(120);
    expect(network.routes[0]!.passengers).toBeNull();
    expect(network.routes[0]!.seats).toBeNull();
    expect(network.routes[0]!.load_factor).toBeNull();
    expect(network.mode).toBe("scheduled_domestic");
    expect(network.observed_months).toEqual([]);
  });
  it("keeps a seasonal route's known movements and discloses its partial months", () => {
    const april = monthNetwork(0, null, 30); april.routes[0]!.passengers = null;
    const may = monthNetwork(0, null, 40); may.routes[0]!.passengers = null;
    const june = monthNetwork(0, null, 0); june.routes = [];
    state.domesticMonthlyNetworks.set("2026M04", april);
    state.domesticMonthlyNetworks.set("2026M05", may);
    state.domesticMonthlyNetworks.set("2026M06", june);
    const route = aggregateDomesticMonths(["2026M04", "2026M05", "2026M06"])!.routes[0]!;
    expect(route.departures).toBe(70);
    expect(route.months_covered).toBe(2);
    expect(route.months_selected).toBe(3);
    expect(route.passengers).toBeNull();
    expect(route.coverage_note).toContain("04, 05");
    expect(route.coverage_note).not.toContain("06");
  });
  it("withholds an aggregate when a selected month has not been loaded", () => {
    state.domesticMonthlyNetworks.set("2026M04", monthNetwork(0, null, 30));
    expect(aggregateDomesticMonths(["2026M04", "2026M05"])).toBeNull();
  });
});
