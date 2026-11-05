import type { MapCarrier, MapRegion, MapScope, OfficialNetwork, OfficialPoint, OfficialRoute, OfficialRoutesDocument } from "../../types/official-routes";

export const MAP_CARRIERS: MapCarrier[] = ["AEROMEXICO", "VOLARIS", "VIVA_AEROBUS"];
export const MAP_CARRIER_LABELS: Record<MapCarrier, string> = { AEROMEXICO: "Grupo Aeroméxico", VOLARIS: "Volaris", VIVA_AEROBUS: "Viva" };
export const MAP_REGIONS: Record<MapRegion, string> = { canada: "Canadá", central_america_caribbean: "Centroamérica", south_america: "Sudamérica", europe: "Europa", asia: "Asia" };
export const MAP_SCOPES: Record<MapScope, string> = { national: "Nacional", us: "EE. UU.", international: "Internacional" };
export const officialState = {
  scope: "national" as MapScope, region: null as MapRegion | null,
  carriers: [...MAP_CARRIERS], view: "volume" as "volume" | "change" | "all",
  document: null as OfficialRoutesDocument | null, network: null as OfficialNetwork | null,
  routes: [] as OfficialRoute[], selectedNode: null as string | null, selectedRoute: null as string | null,
  period: "", loading: false, error: "",
};

export function parseMapSelection(params: URLSearchParams): { scope: MapScope; region: MapRegion | null; carriers: MapCarrier[] } {
  const scope = params.get("map_scope");
  const region = params.get("map_region");
  const raw = params.get("map_carriers") ?? params.get("sel_map");
  const carriers = raw?.split(",").includes("INDUSTRY") ? [...MAP_CARRIERS]
    : MAP_CARRIERS.filter(key => raw?.split(",").includes(key));
  return { scope: scope && Object.hasOwn(MAP_SCOPES, scope) ? scope as MapScope : "national",
    region: region && Object.hasOwn(MAP_REGIONS, region) ? region as MapRegion : null,
    carriers: carriers.length ? carriers : [...MAP_CARRIERS] };
}

export function syncMapUrl(): void {
  const url = new URL(window.location.href);
  url.searchParams.set("map_scope", officialState.scope);
  if (officialState.region) url.searchParams.set("map_region", officialState.region); else url.searchParams.delete("map_region");
  url.searchParams.set("map_carriers", officialState.carriers.join(","));
  window.history.replaceState(null, "", url);
}

export function selectOfficialNetwork(doc: OfficialRoutesDocument, period: string, scope: MapScope, carriers: MapCarrier[]): OfficialNetwork | null {
  const wanted = MAP_CARRIERS.filter(key => carriers.includes(key)).join("+");
  return doc.networks.find(network => network.period_id === period && network.scope === scope &&
    (scope !== "us" || MAP_CARRIERS.filter(key => network.carrier_keys.includes(key)).join("+") === wanted)) ?? null;
}

export function geographicRoutes(network: OfficialNetwork | null, region: MapRegion | null): OfficialRoute[] {
  return network?.routes.filter(route => network.scope !== "international" || !region || route.region === region) ?? [];
}

export function orderedOfficialRoutes(routes = officialState.routes): OfficialRoute[] {
  return [...routes].sort((a, b) => b.departures - a.departures || a.route_key.localeCompare(b.route_key));
}

export function visibleOfficialRoutes(): OfficialRoute[] {
  if (officialState.view === "all") return orderedOfficialRoutes();
  if (officialState.view === "change") {
    const changing = officialState.routes.filter(route => route.comparison.yoy_pct !== null);
    return [...changing.filter(route => route.comparison.yoy_pct! > 0).sort((a, b) => b.comparison.yoy_pct! - a.comparison.yoy_pct!).slice(0, 6),
      ...changing.filter(route => route.comparison.yoy_pct! < 0).sort((a, b) => a.comparison.yoy_pct! - b.comparison.yoy_pct!).slice(0, 6)];
  }
  return orderedOfficialRoutes().slice(0, 12);
}

export function hasGeometry(point: OfficialPoint): point is OfficialPoint & { lat: number; lon: number } {
  return Number.isFinite(point.lat) && Number.isFinite(point.lon) && point.lat !== null && point.lon !== null;
}

export function routeHasGeometry(route: OfficialRoute): boolean { return hasGeometry(route.origin) && hasGeometry(route.destination); }
export function officialRouteTitle(route: OfficialRoute): string {
  const label = (point: OfficialPoint) => point.point_kind === "airport" && point.iata ? point.iata : point.label;
  return `${label(route.origin)} ↔ ${label(route.destination)}`;
}
export function incidentOfficialRoutes(node: string): OfficialRoute[] {
  return orderedOfficialRoutes().filter(route => route.origin.id === node || route.destination.id === node);
}

export function searchOfficialPoints(query: string): Array<{ point: OfficialPoint; count: number }> {
  const normalize = (s: string) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("es-MX");
  const needle = normalize(query.trim());
  if (!needle) return [];
  const points = new Map<string, { point: OfficialPoint; count: number }>();
  for (const route of officialState.routes) for (const point of [route.origin, route.destination]) {
    const entry = points.get(point.id) ?? { point, count: 0 }; entry.count++; points.set(point.id, entry);
  }
  return [...points.values()].filter(({ point }) => normalize(`${point.label} ${point.iata ?? ""}`).includes(needle))
    .sort((a, b) => Number(normalize(b.point.iata ?? "") === needle) - Number(normalize(a.point.iata ?? "") === needle) || b.count - a.count || a.point.id.localeCompare(b.point.id)).slice(0, 8);
}

let pending: Promise<OfficialRoutesDocument> | undefined;
export async function loadOfficialRoutes(dataRoot: string): Promise<OfficialRoutesDocument> {
  if (officialState.document) return officialState.document;
  if (!pending) pending = fetch(`${dataRoot}/official-routes.json`).then(async response => {
    if (!response.ok) throw new Error(`Datos oficiales no disponibles (HTTP ${response.status})`);
    const doc = await response.json() as OfficialRoutesDocument;
    if (doc.schema_version !== "official_route_network_v1" || !Array.isArray(doc.networks)) throw new Error("Contrato de rutas oficiales incompatible");
    officialState.document = doc; return doc;
  }).finally(() => { pending = undefined; });
  return pending;
}
