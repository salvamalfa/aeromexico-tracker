import { beforeEach, expect, it } from "vitest";
import type { Route } from "../../types/domain";
import { orderedRoutes, routeChangePercent, routeValue } from "./network";
import { state } from "./state";

const route = (market_key: string, passengers: number, departures: number, operation_status = "operated_observed"): Route => ({
  market_key, passengers, departures, operation_status, origin: { iata: "MEX" }, destination: { iata: market_key },
} as unknown as Route);

beforeEach(() => {
  state.importance = "passengers"; // Even a stale saved choice cannot restore passenger sizing.
  state.networkMode = "international";
});

it("orders and sizes the map by flights regardless of passenger volume", () => {
  state.routes = [route("MEX<>A", 1_000_000, 2), route("MEX<>B", 10, 30)];
  expect(orderedRoutes().map(r => r.market_key)).toEqual(["MEX<>B", "MEX<>A"]);
  expect(routeValue(state.routes[0]!)).toBe(2);
});

it("changes are flight changes and do not compare schedules with performed operations", () => {
  const observed = {...route("MEX<>A", 99999, 100), previous: {passengers: 1, departures: 80}};
  expect(routeChangePercent(observed)).toBe(25);
  expect(routeChangePercent({...observed, operation_status: "assigned_slot_not_flown"})).toBeNull();
  expect(routeChangePercent({...observed, operation_status: "estimated_from_sample"})).toBeNull();
});
