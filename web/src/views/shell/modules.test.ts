import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { applyModuleSettings } from "./modules";

it("toggles registered modules while preserving other cards and ignoring malformed settings", () => {
  document.body.innerHTML = '<section id="map" data-dashboard-module="routeMap" hidden></section><section id="market"></section>';
  const map = document.getElementById("map")!;
  applyModuleSettings({ routeMap: true, market: false });
  expect(map.hidden).toBe(false);
  expect(document.getElementById("market")!.hidden).toBe(false);
  applyModuleSettings({ routeMap: "false" });
  expect(map.hidden).toBe(false);
  applyModuleSettings({ routeMap: false });
  expect(map.hidden).toBe(true);
});

it("exposes a separate switch on every KPI and chart in the dashboard", () => {
  document.body.innerHTML = readFileSync("index.html", "utf8");
  const cards = Array.from(document.querySelectorAll(".kpi-card, .flight-kpi, .chart[role=img]"));
  const keys = cards.map(card => card.closest<HTMLElement>("[data-dashboard-module]")?.dataset.dashboardModule);
  expect(keys.every(Boolean)).toBe(true);
  expect(new Set(keys).size).toBe(keys.length);
  for (const key of keys) {
    applyModuleSettings({ [key!]: false });
    expect(document.querySelector<HTMLElement>(`[data-dashboard-module="${key}"]`)!.hidden).toBe(true);
    applyModuleSettings({ [key!]: true });
  }
});
