import { beforeEach, expect, it } from "vitest";
import { state, monthsInQuarter } from "./state";
import { currentMapPeriod, mapPeriodLabel, mapPeriodOptions, mountMapPeriodControl, renderMapPeriodControl } from "./map-periods";

beforeEach(() => {
  state.mapPeriodId = null;
  state.periodIndex = 0;
  state.quarters = [{ period_id: "2026Q2" } as typeof state.quarters[number]];
  state.networkMode = "domestic";
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
