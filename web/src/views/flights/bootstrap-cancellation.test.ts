import { beforeEach, expect, it, vi } from "vitest";
import type { QuarterRecord } from "../../types/domain";

const mocks = vi.hoisted(() => ({
  renderMap: vi.fn(), renderNetwork: vi.fn(), pickerChanged: null as null | ((keys: string[]) => Promise<void>),
}));
vi.mock("../../lib/plotly", () => ({ default: { Plots: { resize: vi.fn() } } }));
vi.mock("../../state/period", () => ({ currentPeriodId: () => null, subscribe: vi.fn() }));
vi.mock("./state", async (original) => ({ ...await original<typeof import("./state")>(), loadQuarters: vi.fn() }));
vi.mock("./quarter", () => ({ renderQuarter: vi.fn() }));
vi.mock("./mix", () => ({ renderMix: vi.fn() }));
vi.mock("./network", () => ({ renderNetworkPeriod: mocks.renderNetwork, renderRouteMode: vi.fn() }));
vi.mock("./map", () => ({ renderFlowMap: mocks.renderMap, alignRouteDetailToGeo: vi.fn(),
  canvasSize: () => "", mapFittedCanvasSize: () => "" }));
vi.mock("../executive/state", () => ({ state: { entities: {} } }));
vi.mock("../shell/carriers", () => ({ mountPicker: (_host: HTMLElement, _config: unknown, callback: typeof mocks.pickerChanged) => {
  mocks.pickerChanged = callback;
  return ["INDUSTRY"];
} }));

import { mountFlights } from "./bootstrap";
import { state } from "./state";

beforeEach(() => {
  mocks.renderMap.mockReset();
  mocks.renderNetwork.mockReset();
  mocks.pickerChanged = null;
  state.network = null;
  state.periodIndex = 0;
  state.quarters = [{ period_id: "2026Q2" } as QuarterRecord];
  state.baseAvailablePeriods = null;
  state.availablePeriods = { domestic: [], domestic_monthly: [], international: [], entities: {
    INDUSTRY: { label: "Industria", domestic_monthly: [], international: [] },
    VOLARIS: { label: "Volaris", domestic_monthly: [], international: [] },
    VIVA_AEROBUS: { label: "Viva", domestic_monthly: [], international: [] },
  } };
  document.body.innerHTML = '<section id="panel-flights" hidden></section><div id="pick-map"></div>'
    + ["network-mode-domestic", "network-mode-international", "passenger-period", "map-routes-featured",
      "map-routes-change", "map-routes-all"].map((id) => `<button id="${id}"></button>`).join("");
});

it("does not draw after a cancelled picker callback while a newer carrier is loading", async () => {
  await mountFlights();
  let finishOld!: (installed: boolean) => void;
  let finishNew!: (installed: boolean) => void;
  mocks.renderNetwork.mockReturnValueOnce(new Promise<boolean>((resolve) => { finishOld = resolve; }))
    .mockReturnValueOnce(new Promise<boolean>((resolve) => { finishNew = resolve; }));
  const oldPicker = mocks.pickerChanged!(["VOLARIS"]);
  const newPicker = mocks.pickerChanged!(["VIVA_AEROBUS"]);
  finishOld(false);
  await oldPicker;
  expect(state.network).toBeNull();
  expect(mocks.renderMap).not.toHaveBeenCalled();
  finishNew(true);
  await newPicker;
  expect(mocks.renderMap).toHaveBeenCalledTimes(1);
});
