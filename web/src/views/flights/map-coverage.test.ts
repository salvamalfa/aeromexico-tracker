import { readFileSync } from "node:fs";
import { beforeEach, expect, it } from "vitest";
import type { MapCoverage, QuarterRecord } from "../../types/domain";
import { coverageRatio, renderMapCoverage } from "./map-coverage";
import { state } from "./state";

const accepted = JSON.parse(readFileSync("../config/flights/2026Q2-accepted.json", "utf8"));
const data: MapCoverage = { source: "AFAC · VLOSREG", source_url: "https://example.invalid/afac", source_sha256: "a".repeat(64),
  rows: accepted.expected.filter((r: { scope: string }) => r.scope !== "combined").map((r: Record<string, unknown>) => ({
    entity: r.entity, scope: r.scope, period_id: r.period_id,
    observed_regular: r.strict_observed_regular_flights ?? 0, estimated: r.estimated_flights ?? 0, official_regular: r.official_regular_flights,
  })),
};
beforeEach(() => {
  state.mapCoverage = structuredClone(data); state.mapEntity = "INDUSTRY";
  state.mapPeriodId = "2026Q2"; state.periodIndex = 0; state.quarters = [{ period_id: "2026Q2" } as QuarterRecord];
  state.availablePeriods = { domestic: [], domestic_monthly: ["2026M04", "2026M05", "2026M06"], international: ["2026Q2", "2026M04", "2026M05", "2026M06"] };
  state.selectedDomesticMonths = new Set(["2026M04", "2026M05", "2026M06"]);
  state.networkMode = "domestic"; state.domesticLayer = "estimated";
  document.body.innerHTML = '<p id="flight-map-coverage"></p><p id="flight-map-coverage-info"></p>';
});
it.each([
  [["AEROMEXICO"], 43484, 46716], [["VIVA_AEROBUS"], 39838, 45308], [["VOLARIS"], 45752, 46304],
  [["AEROMEXICO", "VIVA_AEROBUS"], 83322, 92024], [["AEROMEXICO", "VOLARIS"], 89236, 93020],
  [["VIVA_AEROBUS", "VOLARIS"], 85590, 91612], [["INDUSTRY"], 129074, 138328],
] as const)("uses exact ratio of sums for %j", (keys, represented, official) => {
  const result = coverageRatio(data, [...keys], ["2026Q2"])!;
  expect(result.represented).toBe(represented); expect(result.official).toBe(official);
  expect(result.percent).toBe(100 * represented / official);
});
it("deduplicates Industry plus one of its operators", () => {
  expect(coverageRatio(data, ["INDUSTRY", "AEROMEXICO", "AEROMEXICO"], ["2026Q2"]))
    .toEqual(coverageRatio(data, ["INDUSTRY"], ["2026Q2"]));
});
it("month sums equal the full quarter", () => {
  for (const entity of ["AEROMEXICO", "VIVA_AEROBUS", "VOLARIS", "INDUSTRY"]) {
    expect(coverageRatio(data, [entity], ["2026M04", "2026M05", "2026M06"]))
      .toEqual(coverageRatio(data, [entity], ["2026Q2"]));
  }
});
it("does not cap an estimate at an invented 100 percent", () => {
  const r = coverageRatio(data, ["AEROMEXICO"], ["2026M04"])!;
  expect(r.represented).toBe(15953); expect(r.official).toBe(15807); expect(r.percent).toBeGreaterThan(100);
});
it("missing period, scope, denominator and zero total denominator are unavailable", () => {
  expect(coverageRatio(data, ["INDUSTRY"], ["2025Q4"])).toBeNull();
  const incomplete = structuredClone(data); incomplete.rows.pop();
  expect(coverageRatio(incomplete, ["INDUSTRY"], ["2026Q2"])).toBeNull();
  for (const official_regular of [null, 0]) {
    expect(coverageRatio({ ...data, rows: data.rows.map((r) => ({ ...r, official_regular })) }, ["AEROMEXICO"], ["2026Q2"])).toBeNull();
  }
});
it("scope, geography and top12 crops keep the explicitly total-network card", () => {
  renderMapCoverage(); const before = document.getElementById("flight-map-coverage")!.textContent;
  state.networkMode = "international"; state.selectedRegion = "Europe"; state.routeView = "all"; state.routes = [];
  renderMapCoverage(); expect(document.getElementById("flight-map-coverage")!.textContent).toBe(before);
  expect(document.getElementById("flight-map-coverage-info")!.textContent).toMatch(/Nacional \+ internacional.*observados regulares \+ estimados.*Todas las rutas/);
});
it("filters months, and programming or absent data is unavailable", () => {
  state.mapEntity = "AEROMEXICO"; state.selectedDomesticMonths = new Set(["2026M04"]); renderMapCoverage();
  expect(document.getElementById("flight-map-coverage")!.dataset.represented).toBe("15953");
  state.domesticLayer = "official"; renderMapCoverage();
  expect(document.getElementById("flight-map-coverage")!.textContent).toBe("No disponible");
  state.domesticLayer = "estimated"; state.mapCoverage = null; renderMapCoverage();
  expect(document.getElementById("flight-map-coverage")!.textContent).toBe("No disponible");
});

it("rejects overlapping quarter/month calendars instead of counting twice", () => {
  expect(coverageRatio(data, ["AEROMEXICO"], ["2026Q2", "2026M04"])).toBeNull();
});
