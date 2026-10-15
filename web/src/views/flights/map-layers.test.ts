import { expect, it } from "vitest";
import { state } from "./state";
import { calendarQuarter, officialDomesticNetwork } from "./map-layers";
import type { PeriodNetworkDocument } from "../../types/domain";

it("keeps assigned movements separate and slices only known month/directions", () => {
  const mex = { iata: "MEX", city: "CDMX", lat: 19, lon: -99 };
  const agu = { iata: "AGU", city: "Aguascalientes", lat: 21, lon: -102 };
  state.domesticNetworks = new Map([["2026Q2", { mode: "scheduled_domestic", period_label: "2T26",
    airports: [mex, agu], expected_months: ["2026M04", "2026M05", "2026M06"], observed_months: ["2026M04", "2026M05"],
    routes: [{ market_key: "AGU<>MEX", origin: mex, destination: agu, departures: 30,
      operation_status: "assigned_slot_not_flown", source_label: "AICM",
      monthly: [{ period_id: "2026M04", origin_iata: "MEX", destination_iata: "AGU", departures: 10 },
        { period_id: "2026M05", origin_iata: "AGU", destination_iata: "MEX", departures: 20 }] }],
  } as PeriodNetworkDocument]]);
  expect(calendarQuarter("2026M04")).toBe("2026Q2");
  const april = officialDomesticNetwork("2026M04");
  expect(april.routes[0]!.departures).toBe(10);
  expect(april.routes[0]!.operation_status).toBe("assigned_slot_not_flown");
  expect(april.routes[0]!.directions).toHaveLength(1);
  expect(officialDomesticNetwork("2026M06").routes).toEqual([]);
  expect(officialDomesticNetwork("2026M07").routes).toEqual([]);
  expect(officialDomesticNetwork("2026Q2").routes[0]!.departures).toBe(30);
});
