import { beforeEach, expect, it, vi } from "vitest";
import type { Network } from "../../types/domain";

const plotly = vi.hoisted(() => ({ react: vi.fn(), restyle: vi.fn() }));
vi.mock("../../lib/plotly", () => ({ default: plotly }));
vi.mock("./network", () => ({ visibleRoutes: () => [], routeChangePercent: () => null, routeValue: () => 0 }));
vi.mock("./table", () => ({ renderAirportTooltip: vi.fn(), renderRouteOverview: vi.fn() }));

import { renderFlowMap } from "./map";
import { state } from "./state";

beforeEach(() => {
  plotly.react.mockReset();
  state.network = null;
  state.flowMapRendered = false;
});

it("does not draw a map while the first network is still loading", () => {
  expect(() => renderFlowMap()).not.toThrow();
  expect(plotly.react).not.toHaveBeenCalled();
  expect(state.flowMapRendered).toBe(false);
});

it("still reports malformed geometry once a network exists", () => {
  state.network = { routes: [], airports: [] } as unknown as Network;
  expect(() => renderFlowMap()).toThrow("La red de vuelos no contiene la geometría del mapa");
  expect(plotly.react).not.toHaveBeenCalled();
});
