import type { Data } from "plotly.js";
import Plotly, { type PlotlyHTMLElement } from "../../lib/plotly";
import type { OfficialPoint, OfficialRoute } from "../../types/official-routes";
import { state as flights } from "./state";
import { esc, integer } from "./dom";
import { mapPeriodLabel } from "./map-periods";
import { hasGeometry, officialRouteTitle, officialState, previousComparisonMonths, routeHasGeometry, visibleOfficialRoutes } from "./official-routes";

const arcs = new Map<string, { lat: Array<number | null>; lon: Array<number | null> }>();
/** Great-circle geometry is cached independently of quarter and volume. */
export function officialArc(route: OfficialRoute): { lat: Array<number | null>; lon: Array<number | null> } {
  const a = route.origin, b = route.destination;
  if (!hasGeometry(a) || !hasGeometry(b)) return { lat: [], lon: [] };
  const key = `${a.id}:${a.lat}:${a.lon}|${b.id}:${b.lat}:${b.lon}`;
  const cached = arcs.get(key); if (cached) return cached;
  const xyz = (p: OfficialPoint & { lat: number; lon: number }) => {
    const lat = p.lat * Math.PI / 180, lon = p.lon * Math.PI / 180;
    return [Math.cos(lat) * Math.cos(lon), Math.cos(lat) * Math.sin(lon), Math.sin(lat)];
  };
  const x = xyz(a), y = xyz(b), omega = Math.acos(Math.max(-1, Math.min(1, x.reduce((sum, v, i) => sum + v * y[i]!, 0))));
  const sin = Math.sin(omega), result = { lat: [] as Array<number | null>, lon: [] as Array<number | null> };
  let previous = a.lon;
  for (let i = 0; i <= 24; i++) {
    const t = i / 24, first = Math.abs(sin) < 1e-8 ? 1 - t : Math.sin((1 - t) * omega) / sin;
    const second = Math.abs(sin) < 1e-8 ? t : Math.sin(t * omega) / sin;
    const v = x.map((n, j) => first * n + second * y[j]!);
    const length = Math.hypot(...v);
    const lon = Math.atan2(v[1]!, v[0]!) * 180 / Math.PI;
    if (Math.abs(lon - previous) > 180) { result.lat.push(null); result.lon.push(null); }
    result.lat.push(Math.asin(v[2]! / length) * 180 / Math.PI); result.lon.push(lon); previous = lon;
  }
  arcs.set(key, result); return result;
}

/** Bounded traces: eight volume buckets, focus, markers and the local basemap. */
export function officialMapTraces(routes: OfficialRoute[], selectedRoute: string | null, selectedNode: string | null): Data[] {
  const drawable = routes.filter(route => route.departures > 0 && routeHasGeometry(route)), max = Math.max(1, ...drawable.map(route => route.departures));
  const buckets = new Map<number, { lat: Array<number | null>; lon: Array<number | null>; customdata: string[]; text: string[] }>();
  const focus: OfficialRoute[] = [];
  for (const route of drawable) {
    const bucket = Math.min(7, Math.floor(7 * Math.sqrt(route.departures / max)));
    const line = buckets.get(bucket) ?? { lat: [], lon: [], customdata: [], text: [] };
    const arc = officialArc(route);
    line.lat.push(...arc.lat, null); line.lon.push(...arc.lon, null); line.customdata.push(...arc.lat.map(() => route.route_key), "");
    const comparison = route.comparison.yoy_pct === null ? route.comparison.reason ?? "Sin comparación disponible"
      : `${route.comparison.yoy_pct >= 0 ? "+" : ""}${route.comparison.yoy_pct.toFixed(1)} % frente a ${previousComparisonMonths(route).map(mapPeriodLabel).join(", ")}`;
    const label = `${esc(officialRouteTitle(route))}<br>${integer.format(route.departures)} vuelos · ambos sentidos<br>${esc(route.monthly.map(m => mapPeriodLabel(m.period_id)).join(", "))}<br>${esc(comparison)}`;
    line.text.push(...arc.lat.map(() => label), "");
    buckets.set(bucket, line);
    if (route.route_key === selectedRoute || (selectedNode && [route.origin.id, route.destination.id].includes(selectedNode))) focus.push(route);
  }
  const traces: Data[] = [...buckets].sort(([a], [b]) => a - b).map(([bucket, line]) => ({
    type: "scattergeo", mode: "lines", ...line, line: { color: "#003087", width: 1 + bucket * .45 },
    opacity: selectedNode || selectedRoute ? .25 : .62, hovertemplate: "%{text}<extra></extra>", showlegend: false,
  } as Data));
  const highlighted = { lat: [] as Array<number | null>, lon: [] as Array<number | null> };
  for (const route of focus) { const arc = officialArc(route); highlighted.lat.push(...arc.lat, null); highlighted.lon.push(...arc.lon, null); }
  traces.push({ type: "scattergeo", mode: "lines", ...highlighted, line: { color: "#c82236", width: 3.5 }, hoverinfo: "skip", showlegend: false } as Data);
  const nodes = [...new Map(drawable.flatMap(route => [route.origin, route.destination]).map(point => [point.id, point])).values()];
  traces.push({ type: "scattergeo", mode: "markers", lat: nodes.map(p => p.lat), lon: nodes.map(p => p.lon),
    customdata: nodes.map(p => p.id), text: nodes.map(p => {
      const incident = routes.filter(r => r.origin.id === p.id || r.destination.id === p.id);
      return `${esc(p.label)}${p.iata ? ` · ${esc(p.iata)}` : ""}<br>${integer.format(incident.reduce((sum, r) => sum + r.departures, 0))} vuelos en ${incident.length} rutas mostradas<br>Toca para ver todas sus rutas`;
    }),
    marker: { size: nodes.map(p => p.id === selectedNode ? 9 : 6), color: nodes.map(p => p.id === selectedNode ? "#c82236" : "#c99400"), line: { color: "#003087", width: .7 } },
    hovertemplate: "%{text}<extra></extra>", showlegend: false } as Data);
  return traces;
}

let chartRequest = 0;
let drawing = Promise.resolve();
export function drawOfficialMap(onNode: (id: string) => void, onRoute: (id: string) => void): Promise<void> {
  const request = ++chartRequest;
  // A failed draw remains visible to its caller; a later user action can still render a new selection.
  drawing = drawing.catch(() => undefined).then(() => request === chartRequest ? draw(request, onNode, onRoute) : undefined);
  return drawing;
}
async function draw(request: number, onNode: (id: string) => void, onRoute: (id: string) => void): Promise<void> {
  const element = document.getElementById("route-flow-map") as PlotlyHTMLElement | null;
  if (!element) return;
  const world = flights.worldGeometry;
  if (!world?.geojson) return;
  const global = window as unknown as { PlotlyGeoAssets?: { topojson: Record<string, unknown> } };
  const topology = world.topojson as { objects?: Record<string, unknown> } | undefined;
  if (topology?.objects?.land) { global.PlotlyGeoAssets ??= { topojson: {} }; global.PlotlyGeoAssets.topojson.world_110m = topology; }
  const visible = visibleOfficialRoutes();
  // A search/focus always displays all incident routes, even outside the top 12.
  const routes = officialState.selectedNode ? officialState.routes.filter(route => [route.origin.id, route.destination.id].includes(officialState.selectedNode!)) : visible;
  const traces = officialMapTraces(routes, officialState.selectedRoute, officialState.selectedNode);
  traces.unshift({ type: "choropleth", geojson: world.geojson, featureidkey: "id", locations: world.geojson.features.map(f => f.id),
    z: world.geojson.features.map(() => 0), colorscale: [[0, "#e4edf8"], [1, "#e4edf8"]],
    marker: { line: { color: "#b9c8d9", width: .45 } }, showscale: false, hoverinfo: "skip" } as Data);
  const points = officialState.routes.flatMap(route => [route.origin, route.destination]).filter(hasGeometry);
  let lat: [number, number] = [13, 34], lon: [number, number] = [-119, -86];
  if (officialState.scope !== "national") {
    lat = points.length ? [Math.max(-80, Math.min(...points.map(p => p.lat)) - 7), Math.min(85, Math.max(...points.map(p => p.lat)) + 7)] : [-60, 80];
    lon = points.length ? [Math.max(-180, Math.min(...points.map(p => p.lon)) - 10), Math.min(180, Math.max(...points.map(p => p.lon)) + 10)] : [-180, 180];
  }
  // Expand the view to the actual canvas aspect; avoid letterboxing and stale desktop widths on touch devices.
  const width = element.clientWidth || 700, height = element.clientHeight || 420, ratio = width / height;
  const latSpan = lat[1] - lat[0], lonSpan = lon[1] - lon[0];
  if (lonSpan / latSpan < ratio) {
    const middle = (lon[0] + lon[1]) / 2, span = Math.min(360, latSpan * ratio);
    lon = [Math.max(-180, middle - span / 2), Math.min(180, middle + span / 2)];
  } else {
    const middle = (lat[0] + lat[1]) / 2, span = Math.min(170, lonSpan / ratio);
    lat = [Math.max(-85, middle - span / 2), Math.min(85, middle + span / 2)];
  }
  await Plotly.react(element, traces, { width, height, margin: { l: 0, r: 0, t: 0, b: 0 },
    paper_bgcolor: "rgba(0,0,0,0)", showlegend: false, dragmode: false,
    geo: { projection: { type: "equirectangular" }, bgcolor: "rgba(0,0,0,0)", showframe: true, framecolor: "#9fb2c8", showcoastlines: false,
      showcountries: false, showland: false, showocean: true, oceancolor: "#fff",
      lataxis: { range: lat, showgrid: true, gridcolor: "#e7edf4", dtick: officialState.scope === "national" ? 5 : 15 },
      lonaxis: { range: lon, showgrid: true, gridcolor: "#e7edf4", dtick: officialState.scope === "national" ? 5 : 30 } },
  }, { displayModeBar: false, responsive: true, scrollZoom: false });
  if (request !== chartRequest) return;
  element.dataset.mapStatus = officialState.loading ? "loading" : "ready";
  element.dataset.mapPeriod = officialState.period;
  element.dataset.mapScope = officialState.scope;
  element.dataset.mapRegion = officialState.region ?? "";
  element.dataset.mapView = officialState.view;
  element.dataset.mapCarriers = officialState.carriers.join(",");
  element.dataset.mapSelectedNode = officialState.selectedNode ?? "";
  element.removeAllListeners("plotly_click");
  element.on("plotly_click", event => {
    const point = event.points?.[0];
    const id = String((point as unknown as { customdata?: string } | undefined)?.customdata ?? "");
    if (!id) return;
    if (point?.curveNumber === traces.length - 1) onNode(id); else onRoute(id);
  });
  element.setAttribute("aria-label", `Mapa ${officialState.scope}: ${routes.filter(route => route.departures > 0 && routeHasGeometry(route)).length} rutas con vuelos y ubicación. El detalle completo está en la lista de rutas reportadas.`);
  const selected = officialState.routes.find(r => r.route_key === officialState.selectedRoute);
  element.title = selected ? officialRouteTitle(selected) : "";
}
