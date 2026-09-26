import { beforeEach, describe, expect, it } from "vitest";
import { aggregateDomesticMonths, domesticPeriodLabel } from "./domestic";
import { state } from "./state";
import type { Airport, PeriodNetworkDocument } from "../../types/domain";

const MEX: Airport = { iata: "MEX", city: "Ciudad de México", lat: 19.4, lon: -99.1 };
const CUN: Airport = { iata: "CUN", city: "Cancún", lat: 21.0, lon: -86.8 };

function monthNetwork(passengers: number, seats: number | null, departures: number | null): PeriodNetworkDocument {
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

describe("aggregateDomesticMonths", () => {
  beforeEach(() => {
    state.availablePeriods = { domestic: [], domestic_monthly: ["2026-04", "2026-05", "2026-06"], international: [] };
    state.domesticMonthsQuarterId = "2026Q2";
    state.domesticMonthlyNetworks = new Map();
  });

  it("returns null when no requested month has been fetched yet", () => {
    expect(aggregateDomesticMonths(["2026-04"])).toBeNull();
  });

  it("sums passengers, seats and departures across months (never averages percentages)", () => {
    state.domesticMonthlyNetworks.set("2026-04", monthNetwork(100_000, 120_000, 800));
    state.domesticMonthlyNetworks.set("2026-05", monthNetwork(110_000, 130_000, 820));
    state.domesticMonthlyNetworks.set("2026-06", monthNetwork(120_000, 140_000, 840));

    const network = aggregateDomesticMonths(["2026-04", "2026-05", "2026-06"])!;
    const route = network.routes[0]!;
    expect(route.passengers).toBe(330_000);
    expect(route.seats).toBe(390_000);
    expect(route.departures).toBe(2460);
    // Ocupación con los totales, no con el promedio de razones mensuales.
    expect(route.load_factor).toBeCloseTo(330_000 / 390_000, 10);
    expect(route.capacity_estimated).toBe(true);
  });

  it("withholds the occupancy range when capacity coverage is incomplete across months", () => {
    state.domesticMonthlyNetworks.set("2026-04", monthNetwork(100_000, 120_000, 800));
    state.domesticMonthlyNetworks.set("2026-05", monthNetwork(110_000, null, null));

    const network = aggregateDomesticMonths(["2026-04", "2026-05"])!;
    const route = network.routes[0]!;
    expect(route.passengers).toBe(210_000);
    expect(route.load_factor).toBeNull();
    expect(route.load_factor_status).toBe("capacity_incomplete");
    expect(route.capacity_estimated).toBe(false);
  });

  it("never shows an implausible occupancy above 100%", () => {
    state.domesticMonthlyNetworks.set("2026-04", monthNetwork(200_000, 100_000, 800));

    const network = aggregateDomesticMonths(["2026-04"])!;
    const route = network.routes[0]!;
    expect(route.load_factor).toBeNull();
    expect(route.load_factor_status).toBe("inconsistent_inputs");
  });
});
