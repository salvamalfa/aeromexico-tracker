import { readFileSync } from "node:fs";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { OfficialRoutesDocument } from "../../types/official-routes";
import { initPeriods } from "../../state/period";
import { setFareAveragesForTest, type FareAverage } from "./fare-averages";
import { renderRouteList } from "./official-map";
import { officialState } from "./official-routes";
vi.mock("./official-map-chart", () => ({ drawOfficialMap: vi.fn(async () => {}) }));
const wire = JSON.parse(readFileSync("../tests/fixtures/official-routes.example.json", "utf8")) as OfficialRoutesDocument;
const route = wire.networks[0]!.routes[0]!;
const quote = (provider: FareAverage["provider"]): FareAverage => ({
  provider, period_id: "2026Q4", origin: "MEX", destination: "MTY", origin_map_id: route.origin.id, destination_map_id: route.destination.id,
  fare: "Main", conditions: "Un adulto", horizon_months: 1, stay_days: 7, trip_type: "round_trip", observations: 1, paired_cash_points: 0,
  query_date_start: "2026-11-10", query_date_end: "2026-11-10", points_applicability: provider === "VOLARIS" ? "not_applicable" : "applicable", group_id: provider,
  metrics: { cash_final_mxn: { mean: 1234.5, n: 1 }, points: { mean: provider === "VOLARIS" ? null : 15000, n: provider === "VOLARIS" ? 0 : 1 },
    redemption_cash_mxn: { mean: null, n: 0 }, redemption_taxes_mxn: { mean: null, n: 0 } },
});
beforeEach(() => {
  document.body.innerHTML = readFileSync("index.html", "utf8");
  initPeriods(["2026Q3", "2026Q4"], "2026Q3");
  Object.assign(officialState, { period: "2026Q3", routes: [route], network: wire.networks[0], scope: "national", view: "volume", selectedNode: null, selectedRoute: null, carriers: ["VOLARIS"] });
  setFareAveragesForTest({ schema_version: "fare_averages_v1", periods: ["2026Q4"], groups: [quote("AMR"), quote("DOTERS"), quote("VOLARIS")] });
});
afterEach(() => { setFareAveragesForTest(null); document.body.replaceChildren(); });
it("keeps both price headers and missing-quarter cells visible before any route is expanded", () => {
  renderRouteList();
  expect([...document.querySelectorAll(".official-list-columns > span")].map(cell => cell.textContent)).toEqual(["Vuelos", "Aeroméxico", "Viva", "Volaris"]);
  const button = document.querySelector("[data-official-route]")!;
  expect(button.getAttribute("aria-expanded")).toBe("false");
  expect([...button.querySelectorAll("[data-fare-provider]")].map(cell => cell.textContent)).toEqual(["$N/DPTS N/D", "$N/DPTS N/D", "$N/DNo aplica"]);
  expect([...button.querySelectorAll("[data-fare-provider]")].every(cell => cell.children.length === 2)).toBe(true);
  expect(document.querySelector(".official-route-detail")).toBeNull();
  expect(button.textContent).not.toContain("1,234.50");
});
it("uses only the visible US carrier filter and restores all national provider subvalues", () => {
  officialState.period = "2026Q4"; officialState.scope = "us"; renderRouteList();
  const text = () => document.querySelector("[data-official-route]")!.textContent!;
  expect(document.querySelectorAll(".official-fare-excluded")).toHaveLength(2); expect(text()).toContain("No aplica");
  expect(text()).toContain("Fuera de filtro");
  officialState.scope = "national"; renderRouteList();
  expect(document.querySelectorAll(".official-fare-excluded")).toHaveLength(0);
  expect(document.querySelectorAll("[data-fare-provider]")).toHaveLength(3);
  expect(text()).toContain("$1,234.50");
  officialState.scope = "international"; renderRouteList(); expect(document.querySelectorAll(".official-fare-excluded")).toHaveLength(0);
});
