import { beforeEach, expect, it } from "vitest";
import type { PeriodNetworkDocument } from "../../types/domain";
import { state, monthsInQuarter, setMapEntity } from "./state";
import { currentMapPeriod, mapPeriodLabel, mapPeriodOptions, mountMapPeriodControl, renderMapPeriodControl } from "./map-periods";

beforeEach(() => {
  state.mapPeriodId = null;
  state.periodIndex = 0;
  state.quarters = [{ period_id: "2026Q2" } as typeof state.quarters[number]];
  state.networkMode = "domestic";
  state.mapEntity = "AEROMEXICO";
  state.domesticLayer = "estimated";
  state.domesticNetworks.clear();
  state.baseAvailablePeriods = null;
  state.availablePeriods = { domestic: [], domestic_monthly: ["2026M03", "2026M04", "2026M05", "2026M06", "2026M07"], international: ["2015M01", "2026Q2", "2026M07"] };
  document.body.innerHTML = '<div class="network-mode-switch"></div>';
});

it("offers July and its partial quarter without extending financial quarters", () => {
  expect(mapPeriodOptions()).toContain("2026M07");
  expect(mapPeriodOptions()).toContain("2026Q3");
  state.mapPeriodId = "2026M07";
  expect(currentMapPeriod()).toBe("2026M07");
  expect(state.quarters.map((r) => r.period_id)).toEqual(["2026Q2"]);
  expect(monthsInQuarter("2026M07")).toEqual(["2026M07"]);
  expect(monthsInQuarter("2026Q3")).toEqual(["2026M07"]);
  expect(mapPeriodOptions()).not.toContain("2026M08");
});

it("offers every retained international month, including earlier history", () => {
  state.networkMode = "international";
  expect(mapPeriodOptions()).toEqual(["2015M01", "2026M07", "2026Q2"]);
  expect(mapPeriodLabel("2015M01")).toBe("enero 2015");
});

it("changes only the map and can return to the general quarter", () => {
  let changes = 0;
  mountMapPeriodControl(() => changes++);
  const select = document.querySelector<HTMLSelectElement>("#map-period")!;
  select.value = "2026M07";
  select.dispatchEvent(new Event("change"));
  expect(state.mapPeriodId).toBe("2026M07");
  expect(state.periodIndex).toBe(0);
  renderMapPeriodControl();
  expect(select.value).toBe("2026M07");
  select.value = "";
  select.dispatchEvent(new Event("change"));
  expect(currentMapPeriod()).toBe("2026Q2");
  expect(changes).toBe(2);
});

it("returns a historical international selection to the general quarter before fetching domestic data", () => {
  mountMapPeriodControl(() => {});
  state.networkMode = "international";
  state.mapPeriodId = "2015M01";
  expect(currentMapPeriod()).toBe("2015M01");
  state.networkMode = "domestic";
  expect(currentMapPeriod()).toBe("2026Q2");
  expect(state.mapPeriodId).toBeNull();
  renderMapPeriodControl();
  const select = document.querySelector<HTMLSelectElement>("#map-period")!;
  expect(select.value).toBe("");
  expect([...select.options].map((option) => option.value)).not.toContain("2015M01");
  expect(monthsInQuarter(currentMapPeriod())).toEqual(["2026M04", "2026M05", "2026M06"]);
  expect(state.periodIndex).toBe(0);
});

it("resets an unavailable period when the map entity changes", () => {
  state.networkMode = "international";
  state.mapPeriodId = "2015M01";
  state.availablePeriods.entities = {
    VOLARIS: { label: "Volaris", domestic_monthly: ["2026M04"], international: ["2026Q2"] },
  };
  expect(setMapEntity("VOLARIS")).toBe(true);
  expect(currentMapPeriod()).toBe("2026Q2");
  expect(state.mapPeriodId).toBeNull();
  expect(state.quarters.map((record) => record.period_id)).toEqual(["2026Q2"]);
});

it("preserves a valid historical period when the map entity changes", () => {
  state.networkMode = "international";
  state.mapPeriodId = "2015M01";
  state.availablePeriods.entities = {
    VOLARIS: { label: "Volaris", domestic_monthly: [], international: ["2015M01", "2026Q2"] },
  };
  expect(setMapEntity("VOLARIS")).toBe(true);
  expect(currentMapPeriod()).toBe("2015M01");
  expect(state.mapPeriodId).toBe("2015M01");
});

it("preserves July when it is valid in both scopes", () => {
  state.networkMode = "international";
  state.mapPeriodId = "2026M07";
  expect(currentMapPeriod()).toBe("2026M07");
  state.networkMode = "domestic";
  expect(currentMapPeriod()).toBe("2026M07");
  expect(state.mapPeriodId).toBe("2026M07");
});

it("falls back to a listed map period when the general quarter is unavailable", () => {
  mountMapPeriodControl(() => {});
  state.networkMode = "international";
  state.availablePeriods.international = ["2015M01", "2016M01"];
  state.mapPeriodId = "2026M07";
  expect(currentMapPeriod()).toBe("2016M01");
  renderMapPeriodControl();
  expect(document.querySelector<HTMLSelectElement>("#map-period")!.value).toBe("2016M01");
  expect(state.quarters[0]!.period_id).toBe("2026Q2");
});

it("clears an obsolete explicit selection when the new scope has no data", () => {
  state.mapPeriodId = "2015M01";
  state.availablePeriods = { domestic: [], domestic_monthly: [], international: [] };
  expect(currentMapPeriod()).toBe("2026Q2");
  expect(state.mapPeriodId).toBeNull();
  expect(mapPeriodOptions()).toEqual([]);
});

it("falls back from estimate-only July to the available official quarter", () => {
  state.availablePeriods.domestic = ["2026Q2"];
  state.domesticNetworks.set("2026Q2", { routes: [{ monthly: ["2026M04", "2026M05", "2026M06"].map(period_id => ({ period_id })) }] } as unknown as PeriodNetworkDocument);
  state.mapPeriodId = "2026M07";
  state.domesticLayer = "official";
  expect(mapPeriodOptions()).toEqual(["2026M04", "2026M05", "2026M06", "2026Q2"]);
  expect(currentMapPeriod()).toBe("2026Q2");
  expect(state.mapPeriodId).toBeNull();
  state.domesticLayer = "estimated";
  expect(mapPeriodOptions()).toContain("2026M07");
});

it("lists official months from dated official rows rather than estimate months", () => {
  state.availablePeriods.domestic = ["2026Q2"];
  state.domesticNetworks.set("2026Q2", { routes: [{ monthly: [{ period_id: "2026M06" }] }] } as unknown as PeriodNetworkDocument);
  state.domesticLayer = "official";
  expect(mapPeriodOptions()).toEqual(["2026M06", "2026Q2"]);
});

it("keeps other entities on their estimate periods even after the AM layer was official", () => {
  state.mapEntity = "VIVA_AEROBUS";
  state.domesticLayer = "official";
  expect(mapPeriodOptions()).toContain("2026M07");
});
