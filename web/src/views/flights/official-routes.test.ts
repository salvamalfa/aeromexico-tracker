import { readFileSync } from "node:fs";
import { beforeEach, expect, it } from "vitest";
import type { OfficialNetwork, OfficialRoutesDocument } from "../../types/official-routes";
import { geographicRoutes, MAP_CARRIERS, officialState, parseMapSelection, routeHasGeometry,
  previousComparisonMonths, searchOfficialPoints, selectOfficialNetwork, syncMapUrl, visibleOfficialRoutes } from "./official-routes";
import { officialArc, officialMapTraces } from "./official-map-chart";
import { vi } from "vitest";
vi.mock("../../lib/plotly", () => ({ default: {} }));
const wire = JSON.parse(readFileSync("../tests/fixtures/official-routes.example.json", "utf8")) as OfficialRoutesDocument;

beforeEach(() => { officialState.routes = []; officialState.view = "volume"; window.history.replaceState(null, "", "/"); });
it("preserves financial filters and maps legacy sel_map only to the three supported BTS groups", () => {
  expect(parseMapSelection(new URLSearchParams("sel_map=AEROMEXICO,VOLARIS&map_scope=national"))).toEqual({ scope: "national", region: null, carriers: ["AEROMEXICO", "VOLARIS"] });
  expect(parseMapSelection(new URLSearchParams("sel_map=INDUSTRY,VOLARIS" )).carriers).toEqual(MAP_CARRIERS);
  expect(parseMapSelection(new URLSearchParams("map_scope=bad&map_region=norteamerica&map_carriers=DELTA"))).toEqual({ scope: "national", region: null, carriers: MAP_CARRIERS });
  Object.assign(officialState, parseMapSelection(new URLSearchParams("map_scope=us&map_carriers=VIVA_AEROBUS&sel_map=AEROMEXICO")));
  window.history.replaceState(null, "", "/?sel_flight-kpis=VOLARIS&sel_mix=VIVA_AEROBUS&sel_map=AEROMEXICO"); syncMapUrl();
  const params = new URLSearchParams(window.location.search);
  expect(params.get("sel_flight-kpis")).toBe("VOLARIS"); expect(params.get("sel_mix")).toBe("VIVA_AEROBUS");
  expect(params.get("map_carriers")).toBe("VIVA_AEROBUS"); expect(params.get("sel_map")).toBe("AEROMEXICO");
});
it("requires the exact quarter and carrier combination, with no nearest-period or all-carrier fallback", () => {
  expect(selectOfficialNetwork(wire, "2026Q2", "national", MAP_CARRIERS)).toBeNull();
  const us: OfficialNetwork = { ...wire.networks[0]!, scope: "us", grain: "airport_pair", carrier_keys: ["VOLARIS"] };
  const doc = { ...wire, networks: [...wire.networks, us] };
  expect(selectOfficialNetwork(doc, "2026Q3", "us", ["VOLARIS"])).toBe(us);
  expect(selectOfficialNetwork(doc, "2026Q3", "us", ["VOLARIS", "AEROMEXICO"])).toBeNull();
  expect(selectOfficialNetwork(doc, "2026Q3", "national", ["VOLARIS"])?.carrier_keys).toEqual([]);
});
it("keeps an empty international region empty and includes cities without coordinates in totals/search/list", () => {
  const original = wire.networks[0]!.routes[0]!;
  const missing = { ...original, origin: { ...original.origin, id: "UNKNOWN", label: "Sin coordenadas", lat: null, lon: null }, region: "canada" as const };
  const network: OfficialNetwork = { ...wire.networks[0]!, scope: "international", routes: [missing] };
  expect(geographicRoutes(network, "europe")).toEqual([]);
  officialState.routes = geographicRoutes(network, "canada");
  expect(routeHasGeometry(missing)).toBe(false); expect(visibleOfficialRoutes()).toEqual([missing]);
  expect(searchOfficialPoints("sin coordenadas")[0]?.point.id).toBe("UNKNOWN");
  expect(officialState.routes.reduce((sum, route) => sum + route.departures, 0)).toBe(6);
});
it("searches routes outside the top 12 and bounds render traces for large all-route selections", () => {
  const original = wire.networks[0]!.routes[0]!;
  officialState.routes = Array.from({ length: 900 }, (_, i) => ({ ...original, route_key: `route-${i}`, departures: 1000-i,
    destination: { ...original.destination, id: `point-${i}`, label: i === 899 ? "Ciudad pequeña" : `Ciudad ${i}` } }));
  expect(visibleOfficialRoutes()).toHaveLength(12);
  expect(searchOfficialPoints("Ciudad pequeña")[0]?.point.id).toBe("point-899");
  expect(officialMapTraces(officialState.routes, null, null).length).toBeLessThanOrEqual(10);
  officialState.view = "all"; expect(visibleOfficialRoutes()).toHaveLength(900);
});
it("splits arcs at the antimeridian instead of drawing a line across the world", () => {
  const original = wire.networks[0]!.routes[0]!;
  const route = { ...original, origin: { ...original.origin, lat: 30, lon: -117 }, destination: { ...original.destination, lat: 35, lon: 139 } };
  expect(officialArc(route).lon).toContain(null);
});
it("retains an explicit reported zero in the list but draws no zero-flight arc or airport marker", () => {
  const route = { ...wire.networks[0]!.routes[0]!, departures:0 };
  officialState.routes = [route];
  expect(visibleOfficialRoutes()).toEqual([route]);
  const traces = officialMapTraces([route], null, null);
  expect(traces).toHaveLength(2); // empty highlight + empty markers, no volume bucket
  expect((traces[1] as unknown as { lat:number[] }).lat).toEqual([]);
});
it("labels the YoY base as last year, while retaining the current-year comparable support on the wire", () => {
  const route = { ...wire.networks[0]!.routes[0]!, comparison: { previous_departures:3, yoy_pct:100, comparison_months:["2026M07", "2026M08"], reason:null } };
  expect(previousComparisonMonths(route)).toEqual(["2025M07", "2025M08"]);
  expect(route.comparison.comparison_months).toEqual(["2026M07", "2026M08"]);
  const trace = officialMapTraces([route], null, null)[0] as unknown as { text:string[] };
  expect(trace.text[0]).toContain("julio 2025, agosto 2025"); expect(trace.text[0]).not.toContain("frente a julio 2026");
});
