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
