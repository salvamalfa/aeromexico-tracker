import { beforeEach, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { initPeriods } from "../../state/period";
import { state, monthsInQuarter } from "./state";
import { currentMapPeriod, mapPeriodLabel, mountMapPeriodControl, renderMapPeriodControl } from "./map-periods";

beforeEach(() => {
  initPeriods(["2015Q1", "2026Q2", "2026Q3"], "2026Q2");
  state.mapPeriodId = null;
  state.networkMode = "domestic"; state.mapEntity = "AEROMEXICO"; state.domesticLayer = "estimated";
  document.body.innerHTML = readFileSync("index.html", "utf8");
});

it("uses only the global quarter, including when legacy map state contains a month", () => {
  state.mapPeriodId = "2015M01";
  expect(currentMapPeriod()).toBe("2026Q2"); expect(state.mapPeriodId).toBeNull();
  initPeriods(["2026Q2", "2026Q3"], "2026Q3");
  expect(currentMapPeriod()).toBe("2026Q3");
  expect(mapPeriodLabel("2015M01")).toBe("enero 2015");
  expect(monthsInQuarter(currentMapPeriod()).every(id => id.startsWith("2026M"))).toBe(true);
});

it("places the network switch inside the map toolbar and mounts no period selector", () => {
  mountMapPeriodControl(() => {}); mountMapPeriodControl(() => {});
  expect(document.querySelector("#map-period")).toBeNull();
  expect(document.querySelector("#map-route-title")).toBeNull();
  expect(document.querySelector("#network-scope-note")).toBeNull();
  expect(document.querySelector(".map-route-toolbar .network-mode-switch")).not.toBeNull();
  expect(document.querySelectorAll("#map-domestic-layer")).toHaveLength(1);
});

it("keeps the source layer usable without changing the global quarter", () => {
  let changes = 0; mountMapPeriodControl(() => changes++);
  const layer = document.querySelector<HTMLSelectElement>("#map-domestic-layer")!;
  layer.value = "official"; layer.dispatchEvent(new Event("change"));
  expect(state.domesticLayer).toBe("official"); expect(currentMapPeriod()).toBe("2026Q2"); expect(changes).toBe(1);
  state.networkMode = "international"; renderMapPeriodControl(); expect(layer.parentElement!.hidden).toBe(true);
  state.networkMode = "domestic"; renderMapPeriodControl(); expect(layer.parentElement!.hidden).toBe(false);
  state.mapEntity = "VOLARIS"; renderMapPeriodControl(); expect(layer.parentElement!.hidden).toBe(true);
});
