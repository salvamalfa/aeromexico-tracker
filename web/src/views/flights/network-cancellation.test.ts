import { beforeEach, expect, it, vi } from "vitest";
import type { QuarterRecord } from "../../types/domain";

const loaders = vi.hoisted(() => ({ months: vi.fn(), quarter: vi.fn(), international: vi.fn() }));
vi.mock("./state", async (original) => ({
  ...await original<typeof import("./state")>(),
  ensureDomesticMonths: loaders.months,
  ensureDomesticQuarter: loaders.quarter,
  ensureInternational: loaders.international,
}));
vi.mock("./map", () => ({ renderFlowMap: vi.fn() }));
vi.mock("./table", () => ({ renderRouteOverview: vi.fn() }));
vi.mock("./volume", () => ({ renderNetworkVolume: vi.fn() }));

import { renderNetworkPeriod } from "./network";
import { setMapEntity, state } from "./state";

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => { resolve = done; });
  return { promise, resolve };
}

beforeEach(() => {
  loaders.months.mockReset();
  loaders.quarter.mockResolvedValue(undefined);
  loaders.international.mockResolvedValue(undefined);
  state.network = null;
  state.flowMapRendered = false;
  state.mapEntity = "AEROMEXICO";
  state.networkMode = "domestic";
  state.routeView = "volume";
  state.mapPeriodId = "2026Q2";
  state.periodIndex = 0;
  state.quarters = [{ period_id: "2026Q2" } as QuarterRecord];
  state.baseAvailablePeriods = null;
  state.availablePeriods = {
    domestic: [], domestic_monthly: ["2026M04"], international: ["2026Q2"],
    entities: { VOLARIS: { label: "Volaris", domestic_monthly: ["2026M04"], international: ["2026Q2"] } },
  };
  state.domesticMonthlyNetworks.clear();
  state.domesticNetworks.clear();
  state.internationalNetworks.clear();
  state.routes = [];
  document.body.innerHTML = ["network-mode-domestic", "network-mode-international", "network-title",
    "map-route-title", "map-route-summary", "map-routes-featured", "map-routes-change", "map-routes-all"]
    .map((id) => `<button id="${id}"></button>`).join("");
});

it("returns false for an obsolete carrier request while the replacement is still loading", async () => {
  const first = deferred();
  const replacement = deferred();
  loaders.months.mockReturnValueOnce(first.promise).mockReturnValueOnce(replacement.promise);
  const obsoleteRender = renderNetworkPeriod("2026Q2");
  expect(setMapEntity("VOLARIS")).toBe(true);
  const currentRender = renderNetworkPeriod("2026Q2");
  first.resolve();
  await expect(obsoleteRender).resolves.toBe(false);
  expect(state.network).toBeNull();
  expect(loaders.quarter).not.toHaveBeenCalled();
  replacement.resolve();
  await expect(currentRender).resolves.toBe(true);
  expect(state.network).not.toBeNull();
  expect(state.mapEntity).toBe("VOLARIS");
});

it("returns false when a scope request is superseded after its second load starts", async () => {
  const oldQuarter = deferred();
  loaders.months.mockResolvedValue(undefined);
  loaders.quarter.mockReturnValueOnce(oldQuarter.promise);
  const obsoleteRender = renderNetworkPeriod("2026Q2");
  await Promise.resolve();
  state.networkMode = "international";
  const currentRender = renderNetworkPeriod("2026Q2");
  await expect(currentRender).resolves.toBe(true);
  const installed = state.network;
  oldQuarter.resolve();
  await expect(obsoleteRender).resolves.toBe(false);
  expect(state.network).toBe(installed);
});
